# -*- coding: utf-8 -*-
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from app.api.endpoints import app
from app.dependencies import (
    get_ebook_analyzer,
    get_llm_client,
    get_start_point_detector,
    get_db_logger,
)
from app.application.shared.pipeline import UndrmPipeline
from app.domain.models import UndrmPipelineOutput, LlmStartCandidate, DecideOutput

# --- Mock Fixtures (가짜 객체 설정) ---

@pytest.fixture
def mock_pipeline():
    """UndrmPipeline의 가짜(Mock) 객체를 생성합니다."""
    pipeline = MagicMock(spec=UndrmPipeline)
    pipeline.run = AsyncMock(return_value=UndrmPipelineOutput(
        decrypted_epub=b"fake epub data",
        event_id="api-test-event"
    ))
    return pipeline

@pytest.fixture
def mock_analyzer():
    """EbookAnalyzer의 가짜(Mock) 객체를 생성합니다."""
    analyzer = MagicMock()
    analyzer.analyze_async = AsyncMock()
    return analyzer

@pytest.fixture
def mock_llm_client():
    """LlmClient의 가짜(Mock) 객체를 생성합니다."""
    llm = MagicMock()
    llm.client = MagicMock() # 'client' 속성 추가
    llm.suggest_start = AsyncMock(return_value=LlmStartCandidate(file="test.xhtml"))
    return llm

@pytest.fixture
def mock_detector():
    """StartPointDetector의 가짜(Mock) 객체를 생성합니다."""
    detector = MagicMock()
    detector.decide.return_value = DecideOutput(
        start_file="OEBPS/Text/chapter1.xhtml",
        confidence=0.99,
        rationale="Successfully determined by mock."
    )
    return detector

@pytest.fixture
def mock_db_logger():
    """ILogger의 가짜(Mock) 객체를 생성합니다."""
    logger = MagicMock()
    logger.create_log = AsyncMock()
    logger.update_log = AsyncMock()
    return logger

# --- 의존성이 교체된 TestClient Fixture ---

@pytest.fixture
def client(mock_pipeline, mock_analyzer, mock_llm_client, mock_detector, mock_db_logger):
    """
    모든 외부 의존성이 가짜 객체(Mock)로 교체된 TestClient를 제공합니다.
    """
    app.dependency_overrides = {
        UndrmPipeline: lambda: mock_pipeline,
        get_ebook_analyzer: lambda: mock_analyzer,
        get_llm_client: lambda: mock_llm_client,
        get_start_point_detector: lambda: mock_detector,
        get_db_logger: lambda: mock_db_logger,
    }
    
    with TestClient(app) as test_client:
        yield test_client
    
    # 테스트가 끝난 후 교체된 의존성을 원래대로 되돌립니다.
    app.dependency_overrides.clear()

# --- API 테스트 ---

def test_inspect_epub_success(client):
    """
    /v1/epub/inspect 엔드포인트의 정상적인 성공 경로를 테스트합니다.
    """
    request_payload = {
        "s3_bucket": "test-bucket",
        "s3_key": "test-key.epub",
        "itemId": "1234567890",
        "purpose": "find_start_point",
        "tenant_id": "api-test-tenant"
    }
    response = client.post("/v1/epub/inspect", json=request_payload)
    
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["source"]["bucket"] == "test-bucket"
    assert response_data["start"]["start_file"] == "OEBPS/Text/chapter1.xhtml"

def test_inspect_epub_invalid_purpose(client):
    """
    지원하지 않는 'purpose'로 요청했을 때의 응답을 테스트합니다.
    """
    request_payload = {
        "s3_bucket": "test-bucket",
        "s3_key": "test-key.epub",
        "itemId": "1234567890",
        "purpose": "unsupported_purpose",
        "tenant_id": "api-test-tenant"
    }
    response = client.post("/v1/epub/inspect", json=request_payload)
    
    assert response.status_code == 400
    assert "지원하지 않는 목적입니다" in response.json()["detail"]

def test_inspect_epub_missing_field(client):
    """
    필수 필드가 누락된 요청에 대한 응답을 테스트합니다.
    """
    request_payload = {
        "s3_bucket": "test-bucket",
        "itemId": "1234567890",
        "purpose": "find_start_point",
        "tenant_id": "api-test-tenant"
    }
    response = client.post("/v1/epub/inspect", json=request_payload)
    
    assert response.status_code == 422
    assert "s3_key" in response.json()["detail"][0]["loc"]