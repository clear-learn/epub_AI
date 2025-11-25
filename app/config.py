# -*- coding: utf-8 -*-
"""
애플리케이션의 설정을 관리하는 모듈입니다.

- .env 파일에서 환경 변수를 로드합니다.
- 주요 설정 값을 파이썬 변수로 정의하여 다른 모듈에서 쉽게 사용하도록 합니다.
- 애플리케이션 전체의 로깅 설정을 초기화합니다.
- LLM 프롬프트를 외부 파일에서 로드합니다.
"""
import os
import json
import logging
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

class Config:
    def __init__(self):

        # 로깅 설정
        self.setup_logging()

        # .env 파일 로드 (환경 변수 우선 적용)
        load_dotenv()

        # 환경 구분 (local / dev / prod)
        self.ENV = os.getenv("ENV", "local")
        self.PROJECT = os.getenv("PROJECT", "ai-epub")
        self.COMPONENT = os.getenv("COMPONENT", "api")

        # Secrets Manager에서 민감 정보 로드
        secrets = self._get_secret()

        # API 키 (로컬/배포 모두 Secrets Manager 사용)
        self.LANGSMITH_API_KEY = secrets.get("LANGSMITH_API_KEY")
        self.OPENAI_API_KEY = secrets.get("OPENAI_API_KEY")
        self.OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

        # LangSmith 설정
        self.LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "ai-epub-api")
        self.LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING_V2", "false").lower() == "true"

        # LangSmith 환경변수 설정 (langsmith 라이브러리가 읽을 수 있도록)
        if self.LANGSMITH_API_KEY:
            os.environ["LANGSMITH_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGSMITH_PROJECT"] = self.LANGSMITH_PROJECT
            if self.LANGSMITH_TRACING:
                os.environ["LANGSMITH_TRACING_V2"] = "true"
            logging.info(f"LangSmith 트레이싱이 활성화되었습니다. (프로젝트: {self.LANGSMITH_PROJECT})")

        # AWS 설정 (.env에서 로드)
        self.AWS_PROFILE_NAME           = os.getenv("AWS_PROFILE_NAME")
        self.AWS_REGION                 = os.getenv("AWS_REGION", "ap-northeast-2")
        self.KMS_KEY_ID                 = os.getenv("KMS_KEY_ID")

        # AWS 설정 : S3 (.env에서 로드)
        self.S3_MAX_POOL        = int(os.getenv("S3_MAX_POOL", "128"))
        self.S3_MAX_ATTEMPTS    = int(os.getenv("S3_MAX_ATTEMPTS", "8"))
        self.S3_CONNECT_TIMEOUT = int(os.getenv("S3_CONNECT_TIMEOUT", "5"))
        self.S3_READ_TIMEOUT    = int(os.getenv("S3_READ_TIMEOUT", "120"))

        # AWS 설정 : DDB (.env에서 로드)
        self.DDB_MAX_POOL           = int(os.getenv("DDB_MAX_POOL", "64"))
        self.DDB_MAX_ATTEMPTS       = int(os.getenv("DDB_MAX_ATTEMPTS", "8"))
        self.DDB_CONNECT_TIMEOUT    = int(os.getenv("DDB_CONNECT_TIMEOUT", "5"))
        self.DDB_READ_TIMEOUT       = int(os.getenv("DDB_READ_TIMEOUT", "10"))

        # 로컬 환경: DynamoDB 테이블명은 .env에서
        # 배포 환경: Secrets Manager에서 (없으면 기본값)
        if self.ENV == "local":
            self.DYNAMODB_LOG_TABLE_NAME = os.getenv("DYNAMODB_LOG_TABLE_NAME")
        else:
            self.DYNAMODB_LOG_TABLE_NAME = secrets.get("DYNAMODB_LOG", "ai-epub-api-undrm-logs")

        # DB엔진 설정 (.env에서 로드)
        self.DB_POOL_SIZE       = int(os.getenv("DB_POOL_SIZE", "10"))
        self.DB_MAX_OVERFLOW    = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        self.DB_POOL_RECYCLE    = int(os.getenv("DB_POOL_RECYCLE", "1800"))

        # 데이터베이스 설정
        # 로컬: .env에서 DB_CONNECTION_STRING 직접 사용
        # 배포: Secrets Manager에서 개별 값 가져와서 조합 (없으면 .env 폴백)
        if self.ENV == "local":
            self.DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
            self.DB_DATABASE_NAME = os.getenv("DB_DATABASE_NAME", "ai_epub_api_test")
            self.DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "ai-epub-api-test")
        else:
            db_host = secrets.get("DB_HOST")
            db_user = secrets.get("DB_USER")
            db_pass = secrets.get("DB_PASS")
            db_database = secrets.get("DB_DATABASE", "ai_epub_api_test")

            if db_host and db_user and db_pass:
                self.DB_CONNECTION_STRING = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:3306/{db_database}?charset=utf8mb4"
            else:
                logging.warning("Secrets Manager에 DB 정보가 없습니다. .env 폴백을 사용합니다.")
                self.DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")

            self.DB_DATABASE_NAME = db_database
            self.DB_TABLE_NAME = secrets.get("DB_TABLE") or os.getenv("DB_TABLE_NAME", "license_keys")

        # LLM 프롬프트 로딩
        self._load_prompts()

    def _get_secret(self) -> dict:
        """AWS Secrets Manager에서 민감 정보를 가져옵니다."""
        secret_name = f"{self.ENV}/{self.PROJECT}/{self.COMPONENT}"
        region_name = os.getenv("AWS_REGION", "ap-northeast-2")

        try:
            # 로컬: AWS SSO 프로파일 사용
            if self.ENV == "local":
                profile_name = os.getenv("AWS_PROFILE", os.getenv("AWS_PROFILE_NAME"))
                if profile_name:
                    session = boto3.session.Session(profile_name=profile_name)
                else:
                    logging.warning("AWS_PROFILE이 설정되지 않았습니다. 기본 자격 증명을 사용합니다.")
                    session = boto3.session.Session()
            # 배포: IAM Role 사용
            else:
                session = boto3.session.Session()

            client = session.client(
                service_name='secretsmanager',
                region_name=region_name
            )

            resp = client.get_secret_value(SecretId=secret_name)
            secret_dict = json.loads(resp["SecretString"])

            logging.info(f"Secrets Manager에서 설정 로드 완료: {secret_name}")
            return secret_dict

        except ClientError as e:
            error_code = e.response['Error']['Code']
            logging.error(f"Secrets Manager 조회 실패 ({secret_name}): {error_code} - {e}")

            # 폴백: 빈 딕셔너리 반환 (앱이 .env 값을 사용하도록)
            return {}
        except Exception as e:
            logging.error(f"Secrets Manager 조회 중 예외 발생: {e}")
            return {}

    def setup_logging(self):
        """애플리케이션의 전역 로깅 설정을 구성합니다."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    def _load_prompts(self):
        """LLM 프롬프트 파일에서 프롬프트를 로드합니다."""
        try:
            prompt_file_path = os.path.join(os.path.dirname(__file__), "infrastructure", "llm", "prompts", "find_start_point.txt")
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                parts = content.split('---', 1)
                if len(parts) == 2:
                    self.SYSTEM_PROMPT, self.USER_PROMPT_TEMPLATE = map(str.strip, parts)
                else:
                    self.SYSTEM_PROMPT = content.strip()
                    logging.warning(f"프롬프트 파일({prompt_file_path})에 '---' 구분자가 없어 전체를 시스템 프롬프트로 사용합니다.")
        except FileNotFoundError:
            logging.error(f"프롬프트 파일을 찾을 수 없습니다: {prompt_file_path}. 기본 프롬프트를 사용합니다.")
        except Exception as e:
            logging.error(f"프롬프트 파일 로딩 중 오류 발생: {e}")

# --- 설정 인스턴스 제공자 ---
def get_config() -> Config:
    """
    Config 클래스의 새 인스턴스를 반환합니다.
    """
    return Config()