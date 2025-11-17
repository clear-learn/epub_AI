import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import exec from 'k6/execution';

// ───────────────────────────────────────────────────────────────────────────────
// Custom counters
const resp401 = new Counter('resp_401');
const resp403 = new Counter('resp_403');
const resp429 = new Counter('resp_429');
const resp4xx = new Counter('resp_4xx');
const resp5xx = new Counter('resp_5xx');
const netErr  = new Counter('network_errors');

const endToEnd      = new Trend('end_to_end');
const serverLatency = new Trend('server_latency');
const failRate      = new Rate('http_fail_rate');

// ───────────────────────────────────────────────────────────────────────────────
// Env / Input
const URL = __ENV.URL || 'http://localhost:18000/v1/epub/inspect';
const tenantsEnv = (__ENV.TENANTS || '').trim();
const TENANTS = tenantsEnv
  ? tenantsEnv.split(',').map((s) => s.trim()).filter(Boolean)
  : Array.from({ length: 50 }, (_, i) => `tenant-${String(i + 1).padStart(3, '0')}`);

// 책 프로파일(작은책 20만자, 큰책 60만자)
const BOOKS = {
  small: {
    name: 'small',
    s3_bucket: 'ai-data-research',
    s3_key: 'AI-EPUB-API/1143778_1722965_v2.epub', // 60만자
    itemId: '312392359',
  },
  big: {
    name: 'big',
    s3_bucket: 'ai-data-research',
    s3_key: 'AI-EPUB-API/639850_v2.epub',          // 20만자
    itemId: '42961314',
  },
};

// 믹스 비율 (기본: small 0.6, big 0.4)
const SMALL_WEIGHT = Math.max(0, Math.min(1, Number(__ENV.SMALL_WEIGHT || 0.6)));
const BIG_WEIGHT   = Math.max(0, Math.min(1, Number(__ENV.BIG_WEIGHT   || 0.4)));
const SUM_W = SMALL_WEIGHT + BIG_WEIGHT || 1;
const P_SMALL = SMALL_WEIGHT / SUM_W;

// 랜덤 선택
function pickBook() {
  return Math.random() < P_SMALL ? BOOKS.small : BOOKS.big;
}

// 공통 본문
const COMMON = { purpose: 'find_start_point' };

// ───────────────────────────────────────────────────────────────────────────────
// 소수 RPS(0.3~0.7) → 정수 target (timeUnit 확장)
const MIN_RPS   = Number(__ENV.MIN_RPS   || 1.4);
const MAX_RPS   = Number(__ENV.MAX_RPS   || 1.8);
const RPS_STEP  = Number(__ENV.RPS_STEP  || 0.2);
const STEP_MIN  = Number(__ENV.STEP_MIN  || 3);
const TU_S      = Number(__ENV.TU_S      || 10);
const WARMUP    = (__ENV.WARMUP ?? '1') !== '0';

function toTargetPerTU(rps) { return Math.max(0, Math.round(rps * TU_S)); }

const stages = [];
// 스탭 고정 하나만
for (let r = MIN_RPS; r <= MAX_RPS + 1e-9; r += RPS_STEP) {
  stages.push({ target: toTargetPerTU(r), duration: `${STEP_MIN}m` });
  break;
}
// 스탭 적용
// for (let r = MIN_RPS; r <= MAX_RPS + 1e-9; r += RPS_STEP) {
//   stages.push({ target: toTargetPerTU(r), duration: `${STEP_MIN}m` });
// }
// stages.push({ target: toTargetPerTU(MAX_RPS), duration: '5m' });

// ───────────────────────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    soak_rps: {
      executor: 'ramping-arrival-rate',
      startRate: toTargetPerTU(MIN_RPS),
      timeUnit: `${TU_S}s`,
      preAllocatedVUs: Number(__ENV.PRE_VUS || 20),
      maxVUs: Number(__ENV.MAX_VUS || 40),
      stages,
      tags: { endpoint: 'tenant_only' },
    },
  },
  thresholds: {
    'http_req_duration{endpoint:tenant_only}': ['p(95)<12000'],
    'http_req_failed{endpoint:tenant_only}':   ['rate<0.03'],
    'end_to_end{endpoint:tenant_only}':        ['p(95)<12000'],
    'server_latency{endpoint:tenant_only}':    ['p(95)<11000'],
    'resp_5xx': ['count<50'],
    'resp_429': ['rate<0.01'],
  },
  discardResponseBodies: false,
};

// ───────────────────────────────────────────────────────────────────────────────
// setup: 웜업 1회(작은책/큰책 각각 1회씩도 가능)
export function setup() {
  if (!WARMUP) return;
  const warmups = [BOOKS.small, BOOKS.big];
  for (const b of warmups) {
    const tenant = `warmup-${b.name}`;
    const reqBody = JSON.stringify({ ...COMMON, ...b, tenant_id: tenant });
    const params = {
      headers: { 'Content-Type': 'application/json' },
      timeout: __ENV.TIMEOUT || '130s',
      responseType: 'text',
      tags: { endpoint: 'warmup', tenant, book: b.name },
    };
    const t0 = Date.now();
    const res = http.post(URL, reqBody, params);
    const e2e = Date.now() - t0;
    endToEnd.add(e2e, { tenant, endpoint: 'warmup', book: b.name });
    if (res && res.timings && typeof res.timings.waiting === 'number') {
      serverLatency.add(res.timings.waiting, { tenant, endpoint: 'warmup', book: b.name });
    }
    if (!res || res.error || res.status < 200 || res.status >= 300) {
      console.error(`[WARMUP ${b.name}] failed:`, res && (res.error || res.status));
    } else {
      console.log(`[WARMUP ${b.name}] status=${res.status} e2e=${e2e}ms`);
    }
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// Helpers
let idx = 0;
function nextTenant() {
  const t = TENANTS[idx % TENANTS.length];
  idx += 1;
  return t;
}
function byteLength(input) {
  if (input == null) return 0;
  const str = String(input);
  return encodeURIComponent(str).replace(/%[0-9A-F]{2}/gi, 'x').length;
}
function truncate(text, maxBytes) {
  if (text == null) return '';
  const str = String(text);
  if (byteLength(str) <= maxBytes) return str;
  let out = '', used = 0;
  for (let i = 0; i < str.length; i++) {
    const ch = str[i]; const bl = byteLength(ch);
    if (used + bl > maxBytes) break;
    out += ch; used += bl;
  }
  const rest = byteLength(str) - used;
  return `${out} ... <truncated ${rest} bytes>`;
}
function thinkTime() {
  const ms = Number(__ENV.THINK_MS || 100);
  return ms / 1000;
}
function maybeSampleFailure(entry) {} // 생략 가능(원본 쓰던 로깅 있으면 가져오기)

// ───────────────────────────────────────────────────────────────────────────────
// VU logic
export default function () {
  const tenant = nextTenant();
  const book = pickBook(); // small / big 중 하나
  const reqBody = JSON.stringify({ ...COMMON, ...book, tenant_id: tenant });

  const params = {
    headers: { 'Content-Type': 'application/json' },
    timeout: __ENV.TIMEOUT || '130s',
    responseType: 'text',
    tags: { endpoint: 'tenant_only', tenant, book: book.name }, // ← 책 종류 태그
  };

  const t0 = Date.now();
  const res = http.post(URL, reqBody, params);
  const e2e = Date.now() - t0;

  endToEnd.add(e2e, { tenant, endpoint: 'tenant_only', book: book.name });

  if (res && res.timings && typeof res.timings.waiting === 'number') {
    serverLatency.add(res.timings.waiting, { tenant, endpoint: 'tenant_only', book: book.name });
  }

  if (res && res.error) {
    const code = String(res.error_code || 'UNKNOWN');
    netErr.add(1, { code, tenant });
    failRate.add(1, { tenant, book: book.name });
    sleep(thinkTime());
    return;
  }

  const ok = res && res.status >= 200 && res.status < 300;
  failRate.add(!ok, { tenant, book: book.name });

  if (!ok) {
    const preview = truncate((res && res.body) || '', 200);
    console.error(`[HTTP ${res && res.status}] tenant=${tenant} book=${book.name} body="${preview}"`);
  }

  check(res, { 'status 2xx': (r) => r && r.status >= 200 && r.status < 300 });

  sleep(thinkTime());
}

// ───────────────────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const getMetric = (name) => data?.metrics?.[name]?.values || {};
  const getP = (values, p) => {
    if (!values) return undefined;
    const key = `p(${p})`;
    return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : undefined;
  };

  const http = getMetric('http_req_duration');
  const e2e  = getMetric('end_to_end');
  const slat = getMetric('server_latency');
  const httpReqs = getMetric('http_reqs');
  const httpFailed = getMetric('http_req_failed{endpoint:tenant_only}');
  const dropped = getMetric('dropped_iterations');

  const quick = {
    totals: {
      vus_max: data.metrics.vus_max?.values?.value,
      iterations: data.metrics.iterations?.values?.count,
      http_reqs: data.metrics.http_reqs?.values?.count,
      http_req_failed_rate: data.metrics.http_req_failed?.values?.rate,
      custom_fail_rate: data.metrics.http_fail_rate?.values?.rate,
      p95_http_req_duration: getP(http, 95),
      p99_http_req_duration: getP(http, 99),
      p95_end_to_end: getP(e2e, 95),
      p95_server_latency: getP(slat, 95),
    },
    notes: 'book 태그(small/big)로 분리해서 p95 비교하세요.',
  };

  // 원하는 형식의 결과
  const formatted = {
    "단계": "JSON 결과",
    "RPS": "N/A",
    "실효RPS": parseFloat((httpReqs.rate || 0).toFixed(2)),
    "요청 수": httpReqs.count || 0,
    "실패율": `${Math.round((httpFailed.rate || 0) * 100)}%`,
    "avg": `${((http.avg || 0) / 1000).toFixed(2)}s`,
    "p90": `${((getP(http, 90) || 0) / 1000).toFixed(2)}s`,
    "p95": `${((getP(http, 95) || 0) / 1000).toFixed(2)}s`,
    "최대": `${((http.max || 0) / 1000).toFixed(2)}s`,
    "Dropped": dropped.count || 0
  };

  return {
    'result.json': JSON.stringify(formatted, null, 2),
  };
}
