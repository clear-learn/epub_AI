# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, AsyncMock

from app.application.find_start_point.use_case import find_start_point
from app.application.shared.services import EbookAnalyzer
from app.application.find_start_point.services import StartPointDetector
from app.infrastructure.llm.openai_client import LlmClient
from app.domain.interfaces import ILogger
from app.application.shared.pipeline import UndrmPipeline
from app.domain.models import (
    AnalyzeOutput, TocItem, FileCharStat, LlmStartCandidate, 
    UndrmPipelineOutput, DecideOutput
)

# --- 의존성 Mocking을 위한 Fixtures ---

@pytest.fixture
def mock_analyzer():
    """EbookAnalyzer의 가짜 객체를 생성합니다."""
    analyzer = MagicMock(spec=EbookAnalyzer)
    analyzer.analyze_async = AsyncMock(return_value=AnalyzeOutput(
        toc=[TocItem(title="Chapter 1", href="ch1.xhtml", level=1)],
        file_char_counts=[FileCharStat(path="ch1.xhtml", chars=2000, has_text=True)],
    ))
    return analyzer

@pytest.fixture
def mock_llm_client():
    """LlmClient의 가짜 객체를 생성합니다."""
    llm_client = MagicMock(spec=LlmClient)
    llm_client.client = MagicMock()  # 'client' 속성 추가
    llm_client.suggest_start = AsyncMock(return_value=LlmStartCandidate(
        file="ch1.xhtml", rationale="LLM thinks this is the start.", confidence=0.9
    ))
    return llm_client

from app.application.extract_hashtags.services import HashtagExtractor


@pytest.fixture
def mock_detector():
    """StartPointDetector의 가짜 객체를 생성합니다."""
    detector = MagicMock(spec=StartPointDetector)
    detector.decide.return_value = DecideOutput(
        start_file="ch1.xhtml", confidence=0.95, rationale="Detector confirmed."
    )
    return detector

@pytest.fixture
def mock_extractor():
    """HashtagExtractor의 가짜 객체를 생성합니다."""
    extractor = MagicMock(spec=HashtagExtractor)
    extractor.extract_async = AsyncMock(return_value=["#ebook", "#test", "#sample"])
    return extractor


@pytest.fixture
def mock_db_logger():
    """ILogger의 가짜 객체를 생성합니다."""
    logger = MagicMock(spec=ILogger)
    logger.update_log = AsyncMock()
    return logger

@pytest.fixture
def mock_pipeline():
    """비동기 run 메서드를 가진 UndrmPipeline의 가짜 객체를 생성합니다."""
    pipeline = MagicMock(spec=UndrmPipeline)
    pipeline.run = AsyncMock(return_value=UndrmPipelineOutput(
        decrypted_epub=b"decrypted epub data",
        event_id="test-event-id"
    ))
    return pipeline

# --- find_start_point 유스케이스 테스트 ---

@pytest.mark.asyncio
async def test_find_start_point_use_case_success(
    mock_analyzer, mock_llm_client, mock_detector, mock_db_logger, mock_pipeline
):
    """
    find_start_point 유스케이스의 성공적인 실행을 테스트합니다.
    모든 의존성이 올바르게 호출되고 유효한 결과가 반환되는지 검증합니다.
    """
    # --- 준비 (Arrange) ---
    # 유스케이스에 전달할 입력 파라미터
    params = {
        "s3_bucket": "test-bucket",
        "s3_key": "test-key.epub",
        "tenant_id": "test-tenant",
        "itemId": "12345",
        "use_full_toc_analysis": False,
        "analyzer": mock_analyzer,
        "llm_client": mock_llm_client,
        "detector": mock_detector,
        "db_logger": mock_db_logger,
        "pipeline": mock_pipeline,
    }

    # --- 실행 (Act) ---
    result = await find_start_point(**params)

    # --- 검증 (Assert) ---
    # 1. 파이프라인이 올바른 인자와 함께 호출되었는지 확인
    mock_pipeline.run.assert_called_once_with(
        s3_bucket="test-bucket",
        s3_key="test-key.epub",
        tenant_id="test-tenant",
        itemId="12345",
        reason="find_start_point"
    )

    # 2. 핵심 로직(analyze, suggest, decide)이 호출되었는지 확인
    mock_analyzer.analyze_async.assert_called_once_with(b"decrypted epub data")
    mock_llm_client.suggest_start.assert_called_once()
    mock_detector.decide.assert_called_once()

    # 3. 최종 로그가 업데이트되었는지 확인
    mock_db_logger.update_log.assert_called()
    # 최종 상태가 "SUCCESS"인지 확인
    assert mock_db_logger.update_log.call_args.kwargs['status'] == "SUCCESS"

    # 4. 결과 형식이 올바른지 확인
    assert "start_point" in result
    assert result["start_point"]["start_file"] == "ch1.xhtml"
    assert result["start_point"]["confidence"] == 0.95

@pytest.mark.asyncio
async def test_find_start_point_raises_missing_toc_error(
    mock_analyzer, mock_llm_client, mock_detector, mock_db_logger, mock_pipeline
):
    """
    분석기(analyzer)에서 MissingTocError가 발생했을 때 유스케이스가 이를 올바르게 처리하는지 테스트합니다.
    """
    # --- 준비 (Arrange) ---
    from app.domain.errors import MissingTocError
    mock_analyzer.analyze_async.side_effect = MissingTocError("TOC not found")
    
    params = {
        "s3_bucket": "test-bucket",
        "s3_key": "test-key.epub",
        "tenant_id": "test-tenant",
        "itemId": "12345",
        "use_full_toc_analysis": False,
        "analyzer": mock_analyzer,
        "llm_client": mock_llm_client,
        "detector": mock_detector,
        "db_logger": mock_db_logger,
        "pipeline": mock_pipeline,
    }

    # --- 실행 및 검증 (Act & Assert) ---
    with pytest.raises(MissingTocError, match="TOC not found"):
        await find_start_point(**params)

    # 실패가 로그에 기록되었는지 확인
    mock_db_logger.update_log.assert_called_once()
    assert mock_db_logger.update_log.call_args.kwargs['status'] == "FAILURE"
    assert "TOC not found" in mock_db_logger.update_log.call_args.kwargs['failure_reason']


@pytest.mark.asyncio
async def test_find_start_point_use_case_handles_exception(
    mock_analyzer, mock_llm_client, mock_detector, mock_db_logger, mock_pipeline
):
    """
    의존성에서 예외가 발생했을 때 유스케이스가 이를 올바르게 처리하고
    실패를 기록하는지 테스트합니다.
    """
    # --- 준비 (Arrange) ---
    # 분석 단계에서 실패를 시뮬레이션
    mock_analyzer.analyze_async.side_effect = ValueError("EPUB parsing failed")
    
    params = {
        "s3_bucket": "test-bucket",
        "s3_key": "test-key.epub",
        "tenant_id": "test-tenant",
        "itemId": "12345",
        "use_full_toc_analysis": False,
        "analyzer": mock_analyzer,
        "llm_client": mock_llm_client,
        "detector": mock_detector,
        "db_logger": mock_db_logger,
        "pipeline": mock_pipeline,
    }

    # --- 실행 및 검증 (Act & Assert) ---
    with pytest.raises(ValueError, match="EPUB parsing failed"):
        await find_start_point(**params)

    # 실패가 로그에 기록되었는지 확인
    mock_db_logger.update_log.assert_called()
    # 최종 상태가 "FAILURE"인지 확인
    assert mock_db_logger.update_log.call_args.kwargs['status'] == "FAILURE"
    assert "EPUB parsing failed" in mock_db_logger.update_log.call_args.kwargs['failure_reason']


# --- extract_hashtags 유스케이스 테스트 ---

@pytest.mark.asyncio
async def test_extract_hashtags_use_case_success(
    mock_extractor, mock_db_logger, mock_pipeline
):
    """
    extract_hashtags 유스케이스의 성공적인 실행을 테스트합니다.
    """
    # --- 준비 (Arrange) ---
    from app.application.extract_hashtags.use_case import extract_hashtags
    params = {
        "s3_bucket": "test-bucket",
        "s3_key": "test-key.epub",
        "tenant_id": "test-tenant",
        "itemId": "54321",
        "pipeline": mock_pipeline,
        "extractor": mock_extractor,
        "db_logger": mock_db_logger,
    }

    # --- 실행 (Act) ---
    result = await extract_hashtags(**params)

    # --- 검증 (Assert) ---
    # 1. 파이프라인이 올바른 인자와 함께 호출되었는지 확인
    mock_pipeline.run.assert_called_once_with(
        s3_bucket="test-bucket",
        s3_key="test-key.epub",
        tenant_id="test-tenant",
        itemId="54321",
        reason="extract_hashtags"
    )

    # 2. 핵심 로직(extract_async)이 호출되었는지 확인
    mock_extractor.extract_async.assert_called_once_with(b"decrypted epub data")

    # 3. 최종 로그가 업데이트되었는지 확인
    mock_db_logger.update_log.assert_called()
    assert mock_db_logger.update_log.call_args.kwargs['status'] == "SUCCESS"

    # 4. 결과 형식이 올바른지 확인
    assert "hashtags" in result
    assert result["hashtags"] == ["#ebook", "#test", "#sample"]
