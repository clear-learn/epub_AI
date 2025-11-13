# -*- coding: utf-8 -*-
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
import aioboto3
from botocore.config import Config
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.clients import clients
from app.config import get_config

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 애플리케이션의 생명주기 이벤트를 처리합니다.
    - 시작 시: 공유 클라이언트 세션 및 인스턴스를 생성합니다.
    - 종료 시: 리소스를 정리합니다.
    """
    # --- 애플리케이션 시작 시 실행 ---
    logger.info("애플리케이션 시작... 공유 클라이언트를 생성합니다.")
    
    config = get_config()

    # DRM 및 분석용 스레드풀 제한 (asyncio.to_thread()의 default executor)
    loop = asyncio.get_running_loop()
    epub_threads = int(getattr(config, "EPUB_THREADS", max(10, (os.cpu_count() or 2)*3)))
    epub_executor = ThreadPoolExecutor(max_workers=epub_threads, thread_name_prefix="epub")
    loop.set_default_executor(epub_executor)
    logger.info(f"EPUB 전용 스레드풀 초기화: max_workers={epub_threads}")
    
    # aioboto3 세션 생성
    if config.AWS_PROFILE_NAME:
        logger.info(f"로컬 환경으로 감지되었습니다. AWS 프로필 '{config.AWS_PROFILE_NAME}'을(를) 사용하여 aioboto3 세션을 생성합니다.")
        boto_session = aioboto3.Session(
            profile_name=config.AWS_PROFILE_NAME,
            region_name=config.AWS_REGION
        )
    else:
        logger.info(f"EC2 환경으로 감지되었습니다. 기본 자격증명(IAM 역할)을 사용하여 aioboto3 세션을 생성합니다.")
        boto_session = aioboto3.Session(region_name=config.AWS_REGION)

    # botocore s3 Config
    s3_cfg = Config(
        region_name=config.AWS_REGION,
        max_pool_connections=int(getattr(config, "S3_MAX_POOL", 128)),
        retries={"mode": "adaptive", "max_attempts": int(getattr(config, "S3_MAX_ATTEMPTS", 8))},
        connect_timeout=int(getattr(config, "S3_CONNECT_TIMEOUT", 5)),
        read_timeout=int(getattr(config, "S3_READ_TIMEOUT", 120)),
        tcp_keepalive=True,
    )
    # 싱글톤 S3 클라이언트 열기 (컨텍스트 진입)
    s3_client_cm = boto_session.client("s3", config=s3_cfg)
    s3_client = await s3_client_cm.__aenter__()
    clients["boto_session"] = boto_session
    clients["s3_client"] = s3_client
    logger.info("공유 aioboto3 세션이 성공적으로 생성되었습니다.")
    logger.info("공유 S3 클라이언트가 성공적으로 생성되었습니다.")
    
    # botocore 다이나모DB Config
    ddb_cfg = Config(
        region_name=config.AWS_REGION,
        max_pool_connections=int(getattr(config, "DDB_MAX_POOL", 64)),
        retries={"mode": "adaptive", "max_attempts": int(getattr(config, "DDB_MAX_ATTEMPTS", 8))},
        connect_timeout=int(getattr(config, "DDB_CONNECT_TIMEOUT", 5)),
        read_timeout=int(getattr(config, "DDB_READ_TIMEOUT", 10)),
        tcp_keepalive=True,
    )
    # 리소스 컨텍스트를 lifespan에서 열고 닫기
    dynamodb_cm = boto_session.resource("dynamodb", config=ddb_cfg)
    dynamodb = await dynamodb_cm.__aenter__()
    clients["dynamodb_table"] = await dynamodb.Table(config.DYNAMODB_LOG_TABLE_NAME)
    logger.info("공유 dynamoDB 클라이언트가 성공적으로 생성되었습니다.")

    # DSN 보정: pymysql -> aiomysql (이미 하신 로직과 동일)
    dsn = config.DB_CONNECTION_STRING.replace('mysql+pymysql', 'mysql+aiomysql')
    # 커넥션 풀/헬스체크/재활용
    engine = create_async_engine(
        dsn,
        pool_size=int(getattr(config, "DB_POOL_SIZE", 10)),
        max_overflow=int(getattr(config, "DB_MAX_OVERFLOW", 20)),
        pool_timeout=int(getattr(config, "DB_POOL_TIMEOUT", 2)),
        pool_recycle=int(getattr(config, "DB_POOL_RECYCLE", 1800)),  # 30분
        pool_pre_ping=True,  # 죽은 커넥션 즉시 감지
        connect_args={
            "connect_timeout": int(getattr(config, "DB_CONNECT_TIMEOUT", 3)),  # ✅ TCP connect 빠른 실패
            # "ssl": ssl_context  # (필요 시) RDS SSL 강제
        },
    )
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    clients["db_engine"] = engine
    clients["db_sessionmaker"] = AsyncSessionLocal
    logger.info("공유 db_engine 클라이언트가 성공적으로 생성되었습니다.")

    # AsyncOpenAI 클라이언트 생성
    if config.OPENAI_API_KEY:
        openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, max_retries=2, timeout=20.0)
        clients["openai_client"] = openai_client
        logger.info("공유 AsyncOpenAI 클라이언트가 생성되었습니다.")
    else:
        clients["openai_client"] = None
        logger.warning("OpenAI API 키가 없어 AsyncOpenAI 클라이언트를 생성하지 않았습니다.")

    yield
    
    # --- 애플리케이션 종료 시 실행 ---
    logger.info("애플리케이션 종료... 리소스를 정리합니다.")
    # await clients["openai_client"].close() # 필요 시 종료 처리
    await s3_client_cm.__aexit__(None, None, None)
    await dynamodb_cm.__aexit__(None, None, None)
    await engine.dispose()
    clients.clear()
    logger.info("공유 클라이언트가 정리되었습니다.")
