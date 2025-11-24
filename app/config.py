# -*- coding: utf-8 -*-
"""
애플리케이션의 설정을 관리하는 모듈입니다.

- .env 파일에서 환경 변수를 로드합니다.
- 주요 설정 값을 파이썬 변수로 정의하여 다른 모듈에서 쉽게 사용하도록 합니다.
- 애플리케이션 전체의 로깅 설정을 초기화합니다.
- LLM 프롬프트를 외부 파일에서 로드합니다.
"""
import os
import logging
from dotenv import load_dotenv

class Config:
    def __init__(self):
        # .env 파일 로드
        load_dotenv()
        
        # 로깅 설정
        self.setup_logging()

        # OpenAI API 키 및 모델 설정
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4.1-mini")

        # LangSmith 설정 (옵션)
        self.LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
        self.LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "ai-epub-api")
        self.LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING_V2", "false").lower() == "true"

        # LangSmith 환경변수 설정 (langsmith 라이브러리가 읽을 수 있도록)
        if self.LANGSMITH_API_KEY:
            os.environ["LANGSMITH_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGSMITH_PROJECT"] = self.LANGSMITH_PROJECT
            if self.LANGSMITH_TRACING:
                os.environ["LANGSMITH_TRACING_V2"] = "true"
            logging.info(f"LangSmith 트레이싱이 활성화되었습니다. (프로젝트: {self.LANGSMITH_PROJECT})")

        # AWS 설정
        self.AWS_PROFILE_NAME           = os.getenv("AWS_PROFILE_NAME")
        self.AWS_REGION                 = os.getenv("AWS_REGION", "ap-northeast-2")
        self.DYNAMODB_LOG_TABLE_NAME    = os.getenv("DYNAMODB_LOG_TABLE_NAME", "ai-epub-api-undrm-logs")
        self.KMS_KEY_ID                 = os.getenv("KMS_KEY_ID")
        
        # AWS 설정 : S3
        self.S3_MAX_POOL        = os.getenv("S3_MAX_POOL", 128)
        self.S3_MAX_ATTEMPTS    = os.getenv("S3_MAX_ATTEMPTS", 8)
        self.S3_CONNECT_TIMEOUT = os.getenv("S3_CONNECT_TIMEOUT", 5)
        self.S3_READ_TIMEOUT    = os.getenv("S3_READ_TIMEOUT", 120)

        # AWS 설정 : DDB
        self.DDB_MAX_POOL           = os.getenv("DDB_MAX_POOL", 64)
        self.DDB_MAX_ATTEMPTS       = os.getenv("DDB_MAX_ATTEMPTS", 8)
        self.DDB_CONNECT_TIMEOUT    = os.getenv("DDB_CONNECT_TIMEOUT", 5)
        self.DDB_READ_TIMEOUT       = os.getenv("DDB_READ_TIMEOUT", 10)

        # DB엔진
        self.DB_POOL_SIZE       = os.getenv("DB_POOL_SIZE", 10)
        self.DB_MAX_OVERFLOW    = os.getenv("DB_MAX_OVERFLOW", 20)
        self.DB_POOL_RECYCLE    = os.getenv("DB_POOL_RECYCLE", 1800)

        # 데이터베이스 연결 문자열
        self.DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
        self.DB_DATABASE_NAME = os.getenv("DB_DATABASE_NAME", "ai_epub_api_test")
        self.DB_TABLE_NAME = os.getenv("DB_TABLE_NAME", "ai-epub-api-test")

        # LLM 프롬프트 로딩
        self._load_prompts()

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