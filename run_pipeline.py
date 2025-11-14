# -*- coding: utf-8 -*-
import asyncio
import json
import argparse
import os
import time
from datetime import datetime, timezone

# ── 외부/플랫폼
import aioboto3
from botocore.config import Config
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ── 도메인/인프라
from app.domain.models import UndrmInput, UndrmLog, LlmInput, DecideInput
from app.infrastructure.storage.s3_client import S3Client          # (변경) s3_client 핸들 주입 버전
from app.infrastructure.log.dynamodb_logger import DynamoDBLogger  # (변경) Table 핸들 주입 버전
from app.infrastructure.llm.openai_client import LlmClient
from app.infrastructure.drm.database_license_service import DatabaseLicenseService  # (변경) session_factory 주입
from app.dependencies import (
    get_undrm_adapter, get_ebook_analyzer, get_start_point_detector, get_epub_parser
)
from app.config import get_config

async def main():
    """
    메인 파이프라인 실행 스크립트.
    FastAPI Depends 없이 수동으로 의존성을 주입해 실행합니다.
    """
    # ── CLI 인자
    parser = argparse.ArgumentParser(description="EPUB 본문 시작점 탐지 파이프라인을 실행합니다.")
    parser.add_argument("--save-decrypted", action="store_true",
                        help="복호화된 EPUB 파일을 '.sample/output.epub'으로 저장합니다.")
    parser.add_argument("--output", type=str, default="./.sample/output.json",
                        help="최종 결과를 저장할 JSON 파일 이름.")
    args = parser.parse_args()

    undrm_adapter = get_undrm_adapter()

    # ── 옵션: 복호화된 샘플 파일만 생성하고 종료
    if args.save_decrypted:
        print("[INFO] 테스트용으로 복호화된 EPUB 파일을 생성합니다...")
        sample_dir = ".sample"
        epub_path = os.path.join(sample_dir, "364721831.EPUB")
        key_path = os.path.join(sample_dir, "key.txt")

        with open(epub_path, "rb") as f:
            encrypted_epub_bytes = f.read()
        with open(key_path, "r") as f:
            license_key = f.read().strip()

        undrm_input = UndrmInput(
            encrypted_epub=encrypted_epub_bytes,
            license_예key=license_key,
            grant_id="save-decrypted",
            tenant_id="test",
        )
        undrm_output = undrm_adapter.decrypt(undrm_input)

        output_path = os.path.join(".sample", "output.epub")
        with open(output_path, "wb") as f:
            f.write(undrm_output.decrypted_epub)
        print(f"[SUCCESS] 복호화된 EPUB 파일이 '{output_path}'에 저장되었습니다.")
        return

    # ───────────────────────────────────────────────────────────────────────────
    # 수동 lifespan: 공유 리소스(세션/클라이언트/엔진) 준비
    # ───────────────────────────────────────────────────────────────────────────
    print("[INFO] 본문 시작점 탐지 파이프라인을 시작합니다...")
    config = get_config()

    # aioboto3 세션
    if config.AWS_PROFILE_NAME:
        boto_session = aioboto3.Session(
            profile_name=config.AWS_PROFILE_NAME, region_name=config.AWS_REGION
        )
    else:
        boto_session = aioboto3.Session(region_name=config.AWS_REGION)

    # S3/DynamoDB 공통: botocore 설정
    s3_cfg = Config(
        region_name=config.AWS_REGION,
        max_pool_connections=int(getattr(config, "S3_MAX_POOL", 128)),
        retries={"mode": "adaptive", "max_attempts": int(getattr(config, "S3_MAX_ATTEMPTS", 8))},
        connect_timeout=int(getattr(config, "S3_CONNECT_TIMEOUT", 5)),
        read_timeout=int(getattr(config, "S3_READ_TIMEOUT", 120)),
        tcp_keepalive=True,
    )
    ddb_cfg = Config(
        region_name=config.AWS_REGION,
        max_pool_connections=int(getattr(config, "DDB_MAX_POOL", 64)),
        retries={"mode": "adaptive", "max_attempts": int(getattr(config, "DDB_MAX_ATTEMPTS", 8))},
        connect_timeout=int(getattr(config, "DDB_CONNECT_TIMEOUT", 5)),
        read_timeout=int(getattr(config, "DDB_READ_TIMEOUT", 10)),
        tcp_keepalive=True,
    )

    # S3/DynamoDB 리소스 컨텍스트 진입
    s3_client_cm = boto_session.client("s3", config=s3_cfg)
    dynamodb_cm = boto_session.resource("dynamodb", config=ddb_cfg)
    s3_client = await s3_client_cm.__aenter__()
    dynamodb = await dynamodb_cm.__aenter__()
    ddb_table = await dynamodb.Table(config.DYNAMODB_LOG_TABLE_NAME)

    # OpenAI
    openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, max_retries=2, timeout=20.0)

    # DB 엔진/세션팩토리(싱글턴) — pymysql → aiomysql 자동 전환
    dsn = config.DB_CONNECTION_STRING.replace("mysql+pymysql", "mysql+aiomysql")
    engine = create_async_engine(
        dsn,
        pool_size=int(getattr(config, "DB_POOL_SIZE", 10)),
        max_overflow=int(getattr(config, "DB_MAX_OVERFLOW", 20)),
        pool_recycle=int(getattr(config, "DB_POOL_RECYCLE", 1800)),
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    # ── 애플리케이션 서비스 인스턴스 구성 (수동 주입)
    s3 = S3Client(s3_client=s3_client)                 # (변경) 세션이 아니라 s3_client 핸들
    db_logger = DynamoDBLogger(table=ddb_table)        # (변경) 세션이 아니라 Table 핸들
    license_service = DatabaseLicenseService(          # (변경) 직접 주입
        session_factory=SessionLocal,
        table_name=config.DB_TABLE_NAME,
    )

    epub_parser = get_epub_parser()
    analyzer = get_ebook_analyzer(epub_parser)
    llm_client = LlmClient(
        client=openai_client,
        model_name=config.OPENAI_MODEL_NAME,
        system_prompt=config.SYSTEM_PROMPT,
        user_prompt_template=config.USER_PROMPT_TEMPLATE,
    )
    start_point_detector = get_start_point_detector()

    # ───────────────────────────────────────────────────────────────────────────
    # 파이프라인 실행
    # ───────────────────────────────────────────────────────────────────────────
    decrypted_epub = None
    event_id = None
    try:
        # 샘플 입력
        s3_bucket = "ai-data-research"
        s3_key = "AI-EPUB-API/1143778_1722965_v2.epub"
        tenant_id = "test-tenant"
        itemId = "312392359"  # 테스트용

        total_start_time = time.time()

        # 1) S3에서 암호화 EPUB 수신 (레질리언트 Range 다운로드)
        step_start_time = time.time()
        encrypted_epub = await s3.get_object_bytes(bucket=s3_bucket, key=s3_key)
        print(f"[TIMER] S3 get_object_bytes took {time.time() - step_start_time:.2f} seconds.")

        # 2) 라이선스 키 조회
        step_start_time = time.time()
        license_key = await license_service.get_license(itemId)
        if not license_key:
            raise Exception(f"'{itemId}'에 대한 라이선스 키를 찾을 수 없습니다.")
        print(f"[TIMER] license_service.get_license took {time.time() - step_start_time:.2f} seconds.")

        # 3) DRM 해제 시작 + 로그(Processing)
        undrm_input = UndrmInput(
            encrypted_epub=encrypted_epub,
            license_key=license_key,
            grant_id="N/A",
            tenant_id=tenant_id,
        )
        start_time = datetime.now(timezone.utc)

        try:
            step_start_time = time.time()
            output = await undrm_adapter.decrypt_async(undrm_input)
            print(f"[TIMER] undrm_adapter.decrypt_async took {time.time() - step_start_time:.2f} seconds.")

            log_entry = UndrmLog(
                tenant_id=tenant_id,
                itemId=itemId,
                grant_id="N/A",
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                reason="find_start_point",
                status="PROCESSING",
                drm_type=output.drm_type,
                undrm_start_time=start_time.isoformat(),
                undrm_end_time=None,          # (일관성) end_time 대신 undrm_end_time 사용
            )
            event_id = await db_logger.create_log(log_entry)
            decrypted_epub = output.decrypted_epub

        except Exception as e:
            # 해제 단계에서 즉시 실패 로그(완료시간 포함)
            fail_entry = UndrmLog(
                tenant_id=tenant_id,
                itemId=itemId,
                grant_id="N/A",
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                reason="find_start_point",
                status="FAILURE",
                failure_reason=str(e),
                undrm_start_time=start_time.isoformat(),
                undrm_end_time=datetime.now(timezone.utc).isoformat(),
            )
            await db_logger.create_log(fail_entry)
            raise Exception(f"EPUB 복호화 실패: {e}") from e

        # 4) 분석 → LLM → 결정
        step_start_time = time.time()
        analysis = await analyzer.analyze_async(decrypted_epub)
        print(f"[TIMER] analyzer.analyze_async took {time.time() - step_start_time:.2f} seconds.")
        llm_input = LlmInput(toc=analysis.toc, file_char_counts=analysis.file_char_counts)

        # (디버그) LLM 입력 저장
        llm_input_json_str = llm_client.format_input_for_llm(llm_input.toc, llm_input.file_char_counts)
        os.makedirs("./.sample", exist_ok=True)
        with open("./.sample/llm_input.json", "w", encoding="utf-8") as f:
            f.write(llm_input_json_str)

        step_start_time = time.time()
        llm_candidate = await llm_client.suggest_start(llm_input)
        print(f"[TIMER] llm_client.suggest_start took {time.time() - step_start_time:.2f} seconds.")
        
        step_start_time = time.time()
        decision = start_point_detector.decide(
            DecideInput(
                toc=analysis.toc,
                file_char_counts=analysis.file_char_counts,
                llm=llm_candidate,
            )
        )
        print(f"[TIMER] start_point_detector.decide took {time.time() - step_start_time:.2f} seconds.")
        result = {"start_point": decision.model_dump()}

        # 5) 결과 저장
        step_start_time = time.time()
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[TIMER] Result saving took {time.time() - step_start_time:.2f} seconds.")

        print(f"\n[SUCCESS] 파이프라인 실행 완료. 결과가 '{args.output}' 파일에 저장되었습니다.")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"[TIMER] Total execution time: {time.time() - total_start_time:.2f} seconds.")

    except Exception as e:
        print(f"\n[ERROR] 파이프라인 실행 중 오류가 발생했습니다: {e}")
        if event_id:
            # (변경된 로거) update_log는 undrm_end_time을 end_time 파라미터로 받음
            await db_logger.update_log(
                event_id=event_id,
                status="FAILURE",
                end_time=datetime.now(timezone.utc).isoformat(),
                failure_reason=str(e),
            )
    finally:
        # 성공/실패 모두 종료시간 기록 (성공 케이스)
        if event_id:
            await db_logger.update_log(
                event_id=event_id,
                status="SUCCESS",
                end_time=datetime.now(timezone.utc).isoformat(),
            )

        if decrypted_epub:
            del decrypted_epub
            print("\n[INFO] 복호화된 EPUB 데이터가 메모리에서 해제되었습니다.")

        # 리소스 정리
        await s3_client_cm.__aexit__(None, None, None)
        await dynamodb_cm.__aexit__(None, None, None)
        await engine.dispose()
        # OpenAI는 별도 close 불필요(필요 시 aiohttp 세션을 직접 닫는 구현 추가)
        # await openai_client.close()


if __name__ == "__main__":
    asyncio.run(main())