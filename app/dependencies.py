# -*- coding: utf-8 -*-
"""
애플리케이션의 의존성 주입(Dependency Injection)을 위한 제공자(Provider) 함수들을 정의합니다.

이 파일의 함수들은 FastAPI의 `Depends` 시스템과 함께 사용되어,
각 계층이 필요로 하는 서비스 인스턴스를 생성하고 제공하는 책임을 가집니다.
"""
from app.clients import clients
from app.config import get_config, Config
from app.infrastructure.llm.openai_client import LlmClient
from app.infrastructure.storage.s3_client import S3Client
# from app.infrastructure.drm.license_service import LicenseService # KMS 기반 서비스 사용 시 주석 해제
from app.infrastructure.drm.adapter import UndrmAdapter
from app.infrastructure.drm.kms_service import KmsKeyService
from app.infrastructure.drm.database_license_service import DatabaseLicenseService
from app.infrastructure.log.dynamodb_logger import DynamoDBLogger
from app.infrastructure.log.file_logger import FileLogger
from app.application.shared.services import EbookAnalyzer
from app.application.find_start_point.services import StartPointDetector
from app.application.extract_hashtags.services import HashtagExtractor
from fastapi import Depends
from starlette import status
from app.domain.interfaces import ILogger, ILicenseService
from app.core.epub_parser import EpubParser

# --- Core Providers ---

def get_epub_parser() -> EpubParser:
    """EpubParser 인턴스를 생성하고 반환합니다."""
    return EpubParser()

# --- Infrastructure Providers ---

def get_llm_client(config: Config = Depends(get_config)) -> LlmClient:
    """공유 AsyncOpenAI 클라이언트를 사용하여 LlmClient 인스턴스를 생성하고 반환합니다."""
    return LlmClient(
        client=clients.get("openai_client"),
        model_name=config.OPENAI_MODEL_NAME,
        system_prompt=config.SYSTEM_PROMPT,
        user_prompt_template=config.USER_PROMPT_TEMPLATE,
    )

def get_s3_client() -> S3Client:
    """
    lifespan에서 생성/진입(__aenter__)된 공유 aioboto3 S3 클라이언트를 주입.
    (중요) S3Client(session=...)가 아니라 S3Client(s3_client=...) 입니다.
    """
    s3 = clients.get("s3_client")
    if s3 is None:
        # lifespan 초기화 누락 시 빠르게 실패하게
        raise RuntimeError("Shared S3 client is not initialized. Check lifespan startup.")
    return S3Client(s3_client=s3)

def get_kms_key_service(config: Config = Depends(get_config)) -> KmsKeyService:
    """KmsKeyService 인스턴스를 생성하고 반환합니다."""
    return KmsKeyService(
        aws_profile=config.AWS_PROFILE_NAME,
        region_name=config.AWS_REGION,
        key_id=config.KMS_KEY_ID
    )

# --- 라이선스 서비스 제공자 (주석 처리된 부분은 KMS 기반 구현체) ---
# def get_kms_license_service(kms_service: KmsKeyService = Depends(get_kms_key_service)) -> ILicenseService:
#     """(현재 미사용) KMS 기반 LicenseService 인스턴스를 생성하고 반환합니다."""
#     from app.infrastructure.drm.license_service import LicenseService
#     return LicenseService(kms_service)

def get_db_license_service(config: Config = Depends(get_config)) -> DatabaseLicenseService:
    session_factory = clients.get("db_sessionmaker")
    if session_factory is None:
        raise RuntimeError("DB session factory가 초기화되지 않았습니다. lifespan 확인.")
    # (선택) 테이블명 화이트리스트 검증
    # assert config.DB_TABLE_NAME in {"licenses", "license_keys"}  # 예시
    return DatabaseLicenseService(session_factory=session_factory, table_name=config.DB_TABLE_NAME)

def get_license_service(
    db_license_service: DatabaseLicenseService = Depends(get_db_license_service)
) -> ILicenseService:
    """
    기본 LicenseService 인스턴스를 ILicenseService 인터페이스로 반환합니다.
    
    라이선스 조회 방식을 KMS로 변경하려면, 이 함수의 의존성을
    `db_license_service`에서 `get_kms_license_service`로 변경하면 됩니다.
    """
    return db_license_service

def get_undrm_adapter() -> UndrmAdapter:
    """UndrmAdapter 인스턴스를 생성하고 반환합니다."""
    return UndrmAdapter()

def get_db_logger(config: Config = Depends(get_config)) -> ILogger:
    # 로깅 시스템을 교체하려면 이 부분만 수정하면 됩니다.
    # return FileLogger()
    table = clients.get("dynamodb_table")
    if table is None:
        # 필요 시 FileLogger로 폴백해도 됨
        raise RuntimeError("DynamoDB table handle is not initialized. Check lifespan.")
    return DynamoDBLogger(table=table)


# --- Application Providers ---

def get_ebook_analyzer(parser: EpubParser = Depends(get_epub_parser)) -> EbookAnalyzer:
    """EbookAnalyzer 인스턴스를 생성하고 반환합니다."""
    return EbookAnalyzer(parser)

def get_start_point_detector() -> StartPointDetector:
    """StartPointDetector 인스턴스를 생성하고 반환합니다."""
    return StartPointDetector()

def get_hashtag_extractor(parser: EpubParser = Depends(get_epub_parser)) -> HashtagExtractor:
    """HashtagExtractor 인스턴스를 생성하고 반환합니다."""
    return HashtagExtractor(parser)
