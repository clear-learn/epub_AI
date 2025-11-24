# -*- coding: utf-8 -*-
import time
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
import uvicorn

from app.domain.models import InspectRequest, InspectResponse
from app.domain.errors import MissingTocError
from app.application.find_start_point.use_case import find_start_point
from app.core.exceptions import (
    EpubFileNotFoundError,
    EpubParsingError,
    DrmDecryptionError,
    LlmApiError,
    ServerConfigurationError,
    UnsupportedPurposeError,
    ExternalServiceError,
)
from app.dependencies import (
    get_ebook_analyzer,
    get_llm_client,
    get_start_point_detector,
    get_db_logger,
)
from app.application.shared.pipeline import UndrmPipeline
from app.application.shared.services import EbookAnalyzer
from app.infrastructure.llm.openai_client import LlmClient
from app.application.find_start_point.services import StartPointDetector
from app.domain.interfaces import ILogger
from app.lifespan import lifespan

get_config()
logger = logging.getLogger(__name__)
app = FastAPI(
    title="ai-epub-api",
    description="DRM EPUB 분석 API (클린 아키텍처)",
    version="2.4.0", # Class-based Dependency Version
    lifespan=lifespan,
    responses={
        400: {"description": "잘못된 요청"},
        403: {"description": "인증 실패"},
        404: {"description": "EPUB 파일을 찾을 수 없음"},
        422: {"description": "EPUB 파일 구조 또는 내용 오류"},
        500: {"description": "서버 내부 오류"},
        503: {"description": "외부 서비스(LLM) 오류"},
    },
)

# --- Exception Handlers ---
@app.exception_handler(UnsupportedPurposeError)
async def unsupported_purpose_handler(req: Request, exc: UnsupportedPurposeError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

@app.exception_handler(MissingTocError)
async def missing_toc_handler(req: Request, exc: MissingTocError):
    return JSONResponse(status_code=422, content={"detail": f"처리할 수 없는 EPUB 파일입니다: {exc}"})

@app.exception_handler(EpubFileNotFoundError)
async def epub_not_found_handler(req: Request, exc: EpubFileNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(EpubParsingError)
async def epub_parsing_handler(req: Request, exc: EpubParsingError):
    return JSONResponse(status_code=422, content={"detail": f"처리할 수 없는 EPUB 파일입니다: {exc}"})

@app.exception_handler(DrmDecryptionError)
async def drm_decryption_handler(req: Request, exc: DrmDecryptionError):
    return JSONResponse(status_code=500, content={"detail": f"내부 처리 오류 (복호화): {exc}"})

@app.exception_handler(LlmApiError)
async def llm_api_handler(req: Request, exc: LlmApiError):
    return JSONResponse(status_code=503, content={"detail": f"외부 서비스(LLM) 오류: {exc}"})

@app.exception_handler(ExternalServiceError)
async def external_service_handler(req: Request, exc: ExternalServiceError):
    return JSONResponse(status_code=503, content={"detail": "외부 서비스 종속성 오류가 발생했습니다.", "error": str(exc)})

@app.exception_handler(ServerConfigurationError)
async def server_config_handler(req: Request, exc: ServerConfigurationError):
    return JSONResponse(status_code=500, content={"detail": f"서버 설정 오류: {exc}"})

# --- API Endpoint ---
@app.post("/v1/epub/inspect", response_model=InspectResponse)
async def inspect_epub(
    request: InspectRequest,
    analyzer: EbookAnalyzer = Depends(get_ebook_analyzer),
    llm_client: LlmClient = Depends(get_llm_client),
    detector: StartPointDetector = Depends(get_start_point_detector),
    db_logger: ILogger = Depends(get_db_logger),
    pipeline: UndrmPipeline = Depends(UndrmPipeline),
):
    start_time = time.time()
    logger.info(f"'{request.purpose}' 목적의 inspect 요청 수신: {request.s3_bucket}/{request.s3_key}")

    if request.purpose == "find_start_point":
        result = await find_start_point(
            s3_bucket=request.s3_bucket,
            s3_key=request.s3_key,
            tenant_id=request.tenant_id,
            itemId=request.itemId,
            use_full_toc_analysis=request.use_full_toc_analysis,
            analyzer=analyzer,
            llm_client=llm_client,
            detector=detector,
            db_logger=db_logger,
            pipeline=pipeline,
        )
    else:
        raise UnsupportedPurposeError(f"지원하지 않는 목적입니다: '{request.purpose}'")

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"요청 처리 완료: {duration_ms}ms")

    return InspectResponse(
        source={"bucket": request.s3_bucket, "key": request.s3_key},
        start=result.get("start_point"),
        # hashtags=result.get("hashtags"),
        processing={"duration_ms": duration_ms},
    )