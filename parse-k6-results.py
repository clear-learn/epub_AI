#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
k6 summary.json 파일을 읽어서 원하는 형식의 JSON으로 변환
"""
import json
import sys
from pathlib import Path

def parse_k6_summary(summary_path):
    """summary.json을 파싱하여 원하는 형식으로 변환"""

    with open(summary_path, 'r') as f:
        data = json.load(f)

    metrics = data.get('metrics', {})

    # 필요한 메트릭 추출
    http_reqs = metrics.get('http_reqs', {}).get('values', {})
    http_req_duration = metrics.get('http_req_duration{expected_response:true}', {}).get('values', {})
    http_req_failed = metrics.get('http_req_failed{endpoint:tenant_only}', {}).get('values', {})
    dropped_iterations = metrics.get('dropped_iterations', {}).get('values', {})

    # 실패율 계산
    total_requests = http_reqs.get('count', 0)
    failed_rate = http_req_failed.get('rate', 0)

    # 결과 구성
    result = {
        "단계": "JSON 결과",
        "RPS": "N/A",
        "실효RPS": round(http_reqs.get('rate', 0), 2),
        "요청 수": total_requests,
        "실패율": f"{failed_rate * 100:.0f}%",
        "avg": f"{http_req_duration.get('avg', 0) / 1000:.2f}s",
        "p90": f"{http_req_duration.get('p(90)', 0) / 1000:.2f}s",
        "p95": f"{http_req_duration.get('p(95)', 0) / 1000:.2f}s",
        "최대": f"{http_req_duration.get('max', 0) / 1000:.2f}s",
        "Dropped": dropped_iterations.get('count', 0)
    }

    return result

def main():
    # summary.json 경로
    if len(sys.argv) > 1:
        summary_path = sys.argv[1]
    else:
        summary_path = "/Users/yimhaksoon/Downloads/summary.json"

    # 파일 존재 확인
    if not Path(summary_path).exists():
        print(f"❌ 파일을 찾을 수 없습니다: {summary_path}")
        sys.exit(1)

    # 파싱
    result = parse_k6_summary(summary_path)

    # JSON 출력
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 결과 파일로도 저장
    output_path = Path(summary_path).parent / "k6_result_formatted.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 결과 저장: {output_path}")

if __name__ == "__main__":
    main()