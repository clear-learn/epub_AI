# ai-epub-api v0.8

DRM EPUB을 메모리 내에서 분석하여 요청된 작업을 수행하는 API입니다. 클린 아키텍처를 적용하여 모듈 간 의존성을 최소화하고 확장성을 확보했습니다.

**주요 기능:**
-   **본문 시작점 탐지**: LLM을 사용하여 EPUB의 실제 내용이 시작되는 파일을 탐지합니다.
-   **UNDRM 모듈**: 복호화키를 통해 안전하게 메모리에서 복호화하여 원하는 작업을 실행합니다.
-   **해시태그 추출 (추가 기능 샘플)**: 신규 기능 개발 시 참고할 수 있는 샘플 모듈입니다.

---

## 목차
1.  [아키텍처](#1-아키텍처)
2.  [프로젝트 구조](#2-프로젝트-구조)
3.  [서비스 실행 방법](#3-서비스-실행-방법)
4.  [API 명세](#4-api-명세)
5.  [테스트 방법](#5-테스트-방법)
6.  [향후 개선 과제](#6-향후-개선-과제)
7.  [신규 개발자를 위한 가이드](#7-신규-개발자를-위한-가이드)
8.  [부록: 감사 로그 스키마](#8-부록-감사-로그-스키마)

---

## 1. 아키텍처

이 프로젝트는 클린 아키텍처의 계층형 구조를 따릅니다. 각 계층은 내부로만 의존하여 코드의 결합도를 낮춥니다.

-   **Domain**: 핵심 데이터 구조(Pydantic 모델)와 인터페이스를 정의합니다. 외부 의존성이 없는 가장 순수한 계층입니다.
-   **Application**: 시스템의 핵심 비즈니스 로직을 포함하며, 각 유스케이스(`find_start_point`)와 공통 로직(`shared`)으로 구성됩니다. Domain 계층에만 의존합니다.
-   **Infrastructure**: 외부 시스템(DB, S3, LLM API 등)과의 실제 연동을 구현합니다.
-   **API (Presentation)**: FastAPI를 사용하여 외부 요청을 받고 응답하는 진입점입니다. Application 계층의 유스케이스를 호출하고 필요한 의존성을 주입합니다.

```mermaid
graph TD
    subgraph "Presentation Layer"
        A["API<br/>(endpoints.py)"]
    end
    subgraph "Application Layer"
        B["Use Cases<br/>(find_start_point/use_case.py)"]
        C["Shared Components<br/>(shared/pipeline.py, shared/services.py)"]
    end
    subgraph "Domain Layer"
        D["Domain Models & Interfaces<br/>(models.py, interfaces.py)"]
    end
    subgraph "Infrastructure Layer"
        E["Infrastructure<br/>(drm, llm, storage, log, db)"]
    end

    A --> B;
    A -->|Injects Dependencies| C;
    A -->|Injects Dependencies| E;
    B -->|Depends on| C;
    B -->|Depends on| D;
    C -->|Depends on| D;
    C -->|Depends on| E;
```
*API 계층은 FastAPI의 의존성 주입 시스템을 통해 유스케이스(`B`)에 필요한 서비스(`C`, `E`)를 주입합니다. 유스케이스는 주입받은 서비스를 사용하여 비즈니스 로직을 실행합니다.*

<img width="7680" height="5408" alt="image" src="https://github.com/user-attachments/assets/97c65cc2-9f4e-471c-8b64-f25999e5fa41" />


---

## 2. 프로젝트 구조

```
/
├── app/
│   ├── api/
│   │   └── endpoints.py        # [API] FastAPI 라우터 및 엔드포인트 정의
│   ├── application/
│   │   ├── find_start_point/   # '본문 시작점 찾기' 유스케이스
│   │   │   ├── services.py     # 목차(TOC) 분석 등 핵심 비즈니스 로직 서비스
│   │   │   └── use_case.py     # 엔드포인트와 서비스를 연결하는 유스케이스
│   │   ├── extract_hashtags/   # '해시태그 추출' 유스케이스 (샘플)
│   │   │   ├── services.py
│   │   │   └── use_case.py
│   │   └── shared/             # 여러 유스케이스에서 공용으로 사용하는 로직
│   │       ├── pipeline.py     # DRM 해제 및 EPUB 로딩을 처리하는 파이프라인
│   │       └── services.py     # EPUB 파일 구조 분석 서비스
│   ├── core/
│   │   ├── epub_parser.py      # EPUB 파일(OPF, NCX)을 파싱하는 저수준 모듈
│   │   └── exceptions.py       # 프로젝트 전역에서 사용하는 커스텀 예외
│   ├── domain/
│   │   ├── errors.py           # 도메인 관련 오류 정의 (사용되지 않음)
│   │   ├── interfaces.py       # 각 계층의 서비스가 따라야 할 인터페이스(추상 클래스)
│   │   └── models.py           # Pydantic을 사용한 핵심 데이터 모델(DTO) 정의
│   ├── infrastructure/
│   │   ├── drm/
│   │   │   ├── adapter.py      # DRM 라이선스 서비스 호출을 위한 어댑터
│   │   │   ├── kms_service.py  # AWS KMS를 사용한 암호화/복호화 서비스
│   │   │   ├── license_service.py # KMS 기반 DRM 라이선스 키 관리 서비스
│   │   │   └── database_license_service.py # DB 기반 DRM 라이선스 키 관리 서비스
│   │   ├── llm/
│   │   │   ├── openai_client.py # OpenAI API 클라이언트
│   │   │   └── prompts/
│   │   │       └── find_start_point.txt # 본문 시작점 탐지를 위한 LLM 프롬프트
│   │   ├── log/
│   │   │   ├── dynamodb_logger.py # DynamoDB에 감사 로그를 기록하는 로거
│   │   │   └── file_logger.py     # 파일에 감사 로그를 기록하는 로거
│   │   └── storage/
│   │       └── s3_client.py    # AWS S3 연동 클라이언트
│   ├── clients.py              # 공유 클라이언트 인스턴스 저장소
│   ├── config.py               # 환경 변수 로딩 및 로깅 설정
│   ├── dependencies.py         # FastAPI 의존성 주입(DI) Provider 설정
│   └── lifespan.py             # 앱 시작/종료 시 클라이언트 생성/정리
│
├── logs/                       # FileLogger 사용 시 로그가 저장되는 디렉터리
│
├── tests/                      # 단위/통합 테스트 코드
│   ├── test_api.py
│   ├── test_application.py
│   ├── test_core.py
│   └── test_infrastructure.py
│
├── .env                        # 환경 변수 설정 파일 (Git 추적 안 됨)
├── .sample/                    # 샘플 EPUB 및 샘플 자료들
├── .ops/                       # 운영(Ops) 관련 스크립트 및 설정
│   └── dev/
│       └── Dockerfile          # 개발 환경용 Dockerfile
├── dev_main.py                 # 개발용 Uvicorn 실행 스크립트
├── gunicorn.conf.py            # Gunicorn 프로덕션 설정 파일
├── pytest.ini                  # Pytest 설정 파일
├── requirements.txt            # Python 의존성 목록
├── README.md                   # 프로젝트 문서
└── run_pipeline.py             # API 서버 없이 파이프라인을 직접 실행하는 테스트 스크립트
```

---

## 3. 서비스 실행 방법

### 가. 의존성 및 환경 변수 설정
1.  **가상 환경 및 의존성 설치**
    - `python3 -m venv venv`
    - `source venv/bin/activate`
    - `pip3 install -r requirements.txt`
2.  **환경 변수 설정**: 프로젝트 루트의 `sample.env` 파일을 `.env` 파일로 복사한 후, 본인의 환경에 맞게 아래 변수들의 값을 수정합니다.
    -   `OPENAI_API_KEY` (**필수**): OpenAI API 키.
    -   `DB_CONNECTION_STRING` (**필수**): 라이선스 키 조회를 위한 MariaDB 연결 문자열.
    -   `DB_DATABASE_NAME` 라이선스 키 조회를 위한 데이터베이스 이름 (기본값: `ai_epub_api_test`).
    -   `DB_TABLE_NAME` 라이선스 키 조회를 위한 테이블 이름 (기본값: `ai-epub-api-test`).
    -   `AWS_REGION` (**필수**): AWS 리전 (예: `ap-northeast-2`).
    -   `AWS_PROFILE_NAME` 로컬 개발 환경에서 사용할 AWS CLI 프로필 이름.
    -   `DYNAMODB_LOG_TABLE_NAME` 감사 로그를 저장할 DynamoDB 테이블 이름 (기본값: `ai-epub-api-undrm-logs`).
    -   `기타...` sample.env 참고

### 나. API 서버 실행

`dev_main.py`와 `gunicorn.conf.py` 파일을 통해 개발 및 프로덕션 환경에 맞는 실행 방식을 선택할 수 있습니다.

#### 개발 환경 (Uvicorn 단독 실행)
로컬 개발 시에는 코드 변경 시 자동으로 서버를 재시작해주는 `uvicorn`을 직접 사용하는 것이 편리합니다. `dev_main.py`는 이를 위한 진입점입니다.

```bash
python3 dev_main.py
```

#### 프로덕션 환경 (Gunicorn + Uvicorn 워커)
EC2와 같은 실제 운영 환경에서는 프로세스 관리, 안정성, 성능을 위해 Gunicorn을 사용을 권장합니다.

```bash
gunicorn -c gunicorn.conf.py app.api.endpoints:app
```
- `-c gunicorn.conf.py`: Gunicorn 설정 파일을 지정합니다. 포트, 워커 수 등의 설정은 해당 파일과 `.env` 파일을 통해 관리됩니다.


---

## 4. API 명세

### EPUB 분석 API
**POST** `/v1/epub/inspect`

#### Request Body
```json
{
  "s3_bucket": "your-bucket",
  "s3_key": "path/to/book.epub",
  "itemId": "1234567890",
  "purpose": "find_start_point",
  "tenant_id": "your-tenant-id",
  "use_full_toc_analysis": false
}
```

-   `s3_bucket` (string, **필수**): EPUB 파일이 저장된 S3 버킷.
-   `s3_key` (string, **필수**): S3 내 EPUB 파일의 경로.
-   `itemId` (string, **필수**): DRM 라이선스 키와 매핑되는 도서 고유 ID.
-   `purpose` (string, **필수**): 수행할 작업을 지정합니다. 현재 `"find_start_point"`만 지원됩니다.
-   `tenant_id` (string, **필수**): API를 호출하는 테넌트(서비스)를 식별하는 ID. 감사 로그에 사용됩니다.
-   `use_full_toc_analysis` (boolean, 선택): `true`로 설정 시, 목차 전체를 구조화하여 LLM에 전송합니다. (기본값: `false` - 목차갯수가 7개 이상인 경우 최소 5개 ~ 목차 갯수의 절반만 보냄)

#### Success Response (200 OK)
```json
{
    "source": {
        "bucket": "your-bucket",
        "key": "path/to/book.epub"
    },
    "start": {
        "start_file": "OEBPS/Text/chapter1.xhtml",
        "anchor": null,
        "confidence": 0.95,
        "rationale": "LLM이 왜 이 파일을 시작점으로 선택했는지에 대한 설명입니다."
    },
    "processing": {
        "duration_ms": 1250
    }
}
```
-   `source`: 원본 파일 정보.
-   `start`: 본문 시작점 분석 결과.
    -   `start_file`: EPUB 내에서 본문이 시작되는 파일의 경로.
    -   `anchor`: 파일 내 특정 위치(앵커) 정보.
    -   `confidence`: LLM이 판단한 신뢰도 점수 (0.0 ~ 1.0).
    -   `rationale`: 시작점 판단에 대한 LLM의 논리적 근거.
-   `processing`: 처리 과정에 대한 메타데이터.
    -   `duration_ms`: 요청 처리에 소요된 시간 (밀리초).

#### Error Responses
-   **`400 Bad Request`**: `purpose` 필드가 유효하지 않은 경우.
-   **`404 Not Found`**: S3 파일을 찾을 수 없는 경우.
-   **`422 Unprocessable Entity`**: EPUB 파일 구조가 손상된 경우.
-   **`500 Internal Server Error`**: DRM 복호화 실패 등 서버 내부 오류.
-   **`503 Service Unavailable`**: 외부 서비스(MariaDB, LLM API 등) 호출 실패 시.

---

## 5. 테스트 방법

### 가. 파이프라인 직접 실행 (테스트/데모용)
`run_pipeline.py`는 API 서버를 통하지 않고 전체 파이프라인을 직접 실행하는 스크립트입니다. `.sample/364721831.EPUB` 파일을 대상으로 실행되며, 실제 로직을 빠르게 테스트하거나 데모할 때 유용합니다.
```bash
python3 run_pipeline.py
```

### 나. 단위 테스트 실행
`pytest`를 실행하여 `tests` 폴더 내의 모든 테스트를 실행합니다.
```bash
pytest
```

---

## 6. 향후 개선 과제 (TODO)

-   **DB 연동 고도화**: 현재는 임시 테이블에서 `itemId`로 키를 조회합니다. 향후 운영로직에 맞는 변경이 필요합니다.

---

## 7. 신규 개발자를 위한 가이드

### 가. 의존성 주입과 서비스 교체

본 프로젝트는 의존성 주입(DI) 아키텍처를 사용하므로, 핵심 비즈니스 로직을 건드리지 않고 외부 서비스 구현을 쉽게 교체할 수 있습니다.

**예시: 라이선스 조회 방식을 DB에서 KMS로 변경하는 방법**

1.  `app/dependencies.py` 파일의 `get_license_service` 함수 내부를 수정합니다.
2.  현재 `return db_license_service`로 되어있는 부분을 `return kms_license_service`로 변경하면, 애플리케이션 전체에서 사용하는 라이선스 서비스 구현체가 즉시 변경됩니다.


### 나. 신규 기능 모듈 추가 가이드

**예시: '책 요약' (`summarize_book`) 기능 추가하기**

1.  **기능 폴더 생성**: `app/application/` 내에 `summarize_book` 폴더를 생성하고 `use_case.py`, `services.py` 파일을 만듭니다.

2.  **서비스 구현 (`services.py`)**: 책을 요약하는 `BookSummarizer` 클래스를 작성합니다. `LlmClient`에 의존하여 실제 요약 기능을 수행합니다.
    ```python
    # app/application/summarize_book/services.py
    from app.infrastructure.llm.openai_client import LlmClient
    from app.core.epub_parser import EpubParser # 텍스트 추출을 위해 추가
    import io, zipfile

    class BookSummarizer:
        def __init__(self, llm_client: LlmClient, parser: EpubParser):
            self.llm_client = llm_client
            self.parser = parser

        async def summarize_async(self, decrypted_epub: bytes) -> str:
            # 1. EPUB에서 전체 텍스트 추출 (HashtagExtractor와 유사)
            full_text = self._extract_full_text(decrypted_epub)
            
            # 2. LLM을 사용하여 텍스트 요약
            # 실제로는 LlmClient에 별도 메서드(예: request_summary)를 구현해야 함
            summary = f"Summary of {len(full_text)} chars: LLM result placeholder."
            return summary

        def _extract_full_text(self, decrypted_epub: bytes) -> str:
            # ... EPUB의 모든 텍스트를 추출하여 하나의 문자열로 합치는 로직 ...
            return "Long text from epub..."
    ```

3.  **의존성 제공자 추가 (`dependencies.py`)**: `BookSummarizer` 인스턴스를 생성하는 함수를 추가합니다.
    ```python
    # app/dependencies.py (추가)
    from app.application.summarize_book.services import BookSummarizer
    from app.core.epub_parser import EpubParser

    def get_book_summarizer(
        llm_client: LlmClient = Depends(get_llm_client),
        parser: EpubParser = Depends(EpubParser)
    ) -> BookSummarizer:
        return BookSummarizer(llm_client=llm_client, parser=parser)
    ```

4.  **유스케이스 구현 (`use_case.py`)**: `find_start_point`와 동일한 구조로 엔드-투-엔드 시나리오를 작성합니다. `UndrmPipeline`을 사용하여 DRM을 해제하고, `BookSummarizer`로 책을 요약합니다.
    ```python
    # app/application/summarize_book/use_case.py
    import logging
    from datetime import datetime, timezone
    from app.application.shared.pipeline import UndrmPipeline
    from .services import BookSummarizer
    from app.domain.interfaces import ILogger

    logger = logging.getLogger(__name__)

    async def summarize_book(
        s3_bucket: str, s3_key: str, tenant_id: str, itemId: str, # 요청 파라미터
        pipeline: UndrmPipeline,
        summarizer: BookSummarizer,
        db_logger: ILogger,
    ) -> dict:
        pipeline_output = await pipeline.run(
            s3_bucket=s3_bucket, s3_key=s3_key, tenant_id=tenant_id, 
            itemId=itemId, reason="summarize_book"
        )
        event_id = pipeline_output.event_id
        decrypted_epub = None
        try:
            decrypted_epub = pipeline_output.decrypted_epub
            summary = await summarizer.summarize_async(decrypted_epub)
            
            await db_logger.update_log(event_id, status="SUCCESS", end_time=datetime.now(timezone.utc).isoformat())
            return {"summary": summary}
        except Exception as e:
            await db_logger.update_log(
                event_id, status="FAILURE", end_time=datetime.now(timezone.utc).isoformat(), failure_reason=str(e)
            )
            raise e
        finally:
            if decrypted_epub:
                del decrypted_epub
                logger.info(f"[{event_id}] 복호화된 EPUB 데이터가 메모리에서 해제되었습니다.")
    ```

5.  **API 엔드포인트 연결 (`endpoints.py`)**: `inspect_epub` 함수에 새로운 `purpose`("summarize_book")를 처리하는 `elif` 구문을 추가하고, `summarize_book` 유스케이스를 호출하도록 의존성을 주입합니다.
    ```python
    # app/api/endpoints.py (수정)
    from app.application.summarize_book.use_case import summarize_book
    from app.application.summarize_book.services import BookSummarizer
    from app.dependencies import get_book_summarizer
    # ...

    async def inspect_epub(
        request: InspectRequest,
        # ... (기존 의존성)
        summarizer: BookSummarizer = Depends(get_book_summarizer),
        # ...
    ):
        # ...
        elif request.purpose == "summarize_book":
            # 유스케이스에 필요한 모든 의존성을 명시적으로 전달
            result = await summarize_book(
                s3_bucket=request.s3_bucket,
                s3_key=request.s3_key,
                tenant_id=request.tenant_id,
                itemId=request.itemId,
                pipeline=pipeline, # 기존 의존성 재사용
                summarizer=summarizer,
                db_logger=db_logger, # 기존 의존성 재사용
            )
        # ...
    ```

---

## 8. 부록: 감사 로그 스키마 (`UndrmLog`)

애플리케이션은 모든 복호화 요청에 대한 감사 로그를 기록합니다. 다음은 로그를 구성하는 각 필드에 대한 상세 설명입니다.

| 필드 (Field) | 타입 (Type) | 설명 (Description) |
| :--- | :--- | :--- |
| `event_id` | `string` | 복호화 요청 이벤트를 식별하는 UUID. |
| `tenant_id` | `string` | API를 호출한 서비스를 식별하는 ID. |
| `user_context` | `dict` (선택) | 추가적인 사용자 관련 정보 (예: 사용자 ID, IP 주소). |
| `s3_bucket` | `string` | EPUB 파일이 저장된 S3 버킷 이름. |
| `s3_key` | `string` | S3 버킷 내 파일의 전체 경로. |
| `grant_id` | `string` | DRM 복호화에 사용된 라이선스 발급(Grant)의 고유 ID. DB 조회 방식으로 변경되면서 더 이상 사용되지 않음 (`"N/A"`). |
| `action` | `string` | 수행된 작업. 항상 `"UNDRM"`(복호화) 입니다. |
| `reason` | `string` | 복호화 작업이 수행된 목적 (예: `"find_start_point"`). |
| `status` | `string` | 작업의 상태: `"PROCESSING"`, `"SUCCESS"`, `"FAILURE"`. |
| `failure_reason` | `string` (선택) | 작업 실패 시 원인(예외 메시지). |
| `drm_type` | `string` | DRM의 종류(현재 V2로 고정). |
| `undrm_start_time` | `string` | 작업 시작 시간 (ISO 8601 UTC). |
| `undrm_end_time` | `string` (선택) | 작업 종료 시간 (ISO 8601 UTC). |
| `event_time` | `string` | 로그 레코드가 처음 생성된 시간 (ISO 8601 UTC). |

## 기타 : Docker Build and Run

### 1. Docker Image Build
다음 명령어를 사용하여 프로젝트 루트에서 Docker 이미지를 빌드합니다.
```bash
docker build -t ai-epub-api -f .ops/dev/Dockerfile .
```

### 2. Docker Container Run
아래 명령어는 `sample.env`에 정의된 환경 변수들을 직접 주입하여 컨테이너를 실행하는 예시입니다. 각 `-e` 플래그의 `"..."` 부분을 실제 값으로 채워야 합니다.

```bash
docker run -d --rm --name ai-epub-api-container \
   -p 18000:18000 \
   -e API_KEY='...' \
   -e OPENAI_API_KEY='...' \
   -e AWS_REGION='ap-northeast-2' \
   -e DB_CONNECTION_STRING='mysql+pymysql://user:password@host:port/dbname' \
   -e DYNAMODB_LOG_TABLE_NAME='ai-epub-api-undrm-logs' \
   -e DB_DATABASE_NAME='ai_epub_api_test' \
   -e DB_TABLE_NAME='license_keys' \
   # --- 선택적 변수 (필요시 주입) ---
   -e AWS_PROFILE_NAME='...' \
   ai-epub-api
```
- `-d`: 백그라운드에서 컨테이너를 실행합니다.
- `--rm`: 컨테이너가 중지될 때 자동으로 삭제합니다.
- `--name ai-epub-api-container`: 컨테이너에 이름을 부여합니다.
- `-p 18000:18000`: 호스트의 18000번 포트를 컨테이너의 18000번 포트와 매핑합니다.
- `-e VAR="value"`: 환경 변수를 컨테이너에 주입합니다.
- `ai-epub-api`: 실행할 Docker 이미지의 이름입니다.
