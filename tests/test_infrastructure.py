# -*- coding: utf-8 -*-
import pytest
import os
import zipfile
import io
import json
from unittest.mock import MagicMock, AsyncMock

# Infrastructure 계층의 클래스들
from app.infrastructure.drm.adapter import UndrmAdapter
from app.infrastructure.llm.openai_client import LlmClient
from app.infrastructure.drm.kms_service import KmsKeyService
from app.infrastructure.drm.database_license_service import DatabaseLicenseService

# Domain 모델
from app.domain.models import UndrmInput, LlmInput, TocItem, FileCharStat

# --- DRM Adapter Test ---

@pytest.fixture
def undrm_adapter():
    return UndrmAdapter()

def test_decrypt_sample_epub_successfully(undrm_adapter):
    """샘플 EPUB 파일이 성공적으로 복호화되는지 테스트합니다."""
    epub_path = os.path.join('.sample', '364721831.EPUB')
    key_path = os.path.join('.sample', 'key.txt')

    with open(epub_path, 'rb') as f: encrypted_epub_bytes = f.read()
    with open(key_path, 'r') as f: license_key = f.read().strip()

    undrm_input = UndrmInput(
        encrypted_epub=encrypted_epub_bytes,
        license_key=license_key,
        grant_id=None,  # grant_id는 이제 선택 사항
        tenant_id="pytest-tenant"
    )
    undrm_output = undrm_adapter.decrypt(undrm_input)

    assert undrm_output.decrypted_epub
    with zipfile.ZipFile(io.BytesIO(undrm_output.decrypted_epub), 'r') as zf:
        assert 'META-INF/encryption.xml' not in zf.namelist()

# --- LLM Client Test ---

@pytest.fixture
def llm_client_with_mock_api(mocker):
    """OpenAI API 호출을 모킹한 LlmClient 인스턴스를 제공합니다."""
    mock_openai_client = MagicMock()
    # AsyncOpenAI 클라이언트의 비동기 메서드를 모킹
    mock_openai_client.responses.create = AsyncMock(return_value=MagicMock(output_text=json.dumps({
        "file": "ch1.xhtml", "rationale": "Mocked response", "confidence": 0.9
    })))
    
    client = LlmClient(
        client=mock_openai_client,
        model_name="gpt-4.1",
        system_prompt="Test system prompt.",
        user_prompt_template="Metadata: {metadata_json}"
    )
    return client, mock_openai_client

@pytest.mark.asyncio
async def test_llm_client_suggest_start_parses_response_correctly(llm_client_with_mock_api):
    """LLM 클라이언트가 API 응답을 정확하게 파싱하는지 테스트합니다."""
    client, mock_api = llm_client_with_mock_api
    llm_input = LlmInput(
        toc=[TocItem(title="Chapter 1", href="ch1.xhtml", level=1)],
        file_char_counts=[FileCharStat(path="ch1.xhtml", chars=100, has_text=True)]
    )
    result = await client.suggest_start(llm_input)
    mock_api.responses.create.assert_called_once()
    assert result.file == "ch1.xhtml"
    assert result.confidence == 0.9

# --- KMS Key Service Test ---

@pytest.fixture
def kms_service_with_mock_aiobotocore(mocker):
    """aiobotocore 클라이언트를 모킹한 KmsKeyService를 제공합니다."""
    mock_kms_client = AsyncMock()
    decrypted_key = "DECRYPTED_HEX_KEY"
    mock_kms_client.decrypt.return_value = {'Plaintext': decrypted_key.encode('utf-8')}
    
    # aiobotocore.session.get_session을 모킹
    mock_get_session = mocker.patch('app.infrastructure.drm.kms_service.get_session')
    
    mock_session = MagicMock()
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = mock_kms_client
    mock_session.create_client.return_value = mock_context_manager
    mock_get_session.return_value = mock_session
    
    service = KmsKeyService(aws_profile="mock_profile", region_name="us-east-1", key_id="mock_key_id")
    return service, mock_kms_client

@pytest.mark.asyncio
async def test_kms_key_service_decrypts_successfully(kms_service_with_mock_aiobotocore):
    """KmsKeyService가 boto3 클라이언트를 올바르게 호출하고 응답을 디코딩하는지 테스트합니다."""
    service, mock_client = kms_service_with_mock_aiobotocore
    result = await service.get_decrypted_key(item_id="any_item_id")
    mock_client.decrypt.assert_called_once()
    assert result == "DECRYPTED_HEX_KEY"

# --- Database License Service Test ---
@pytest.fixture
def db_license_service_with_mock_db():
    """데이터베이스 세션 및 쿼리 실행을 모킹한 DatabaseLicenseService를 제공합니다."""
    mock_session_instance = MagicMock()
    mock_session_instance.__aenter__.return_value = mock_session_instance
    mock_session_instance.__aexit__ = AsyncMock()

    # execute는 비동기 메서드이므로 AsyncMock으로 설정
    mock_result = MagicMock()
    mock_session_instance.execute = AsyncMock(return_value=mock_result)

    # session_factory는 이제 외부에서 주입됩니다.
    mock_session_factory = MagicMock(return_value=mock_session_instance)
    
    service = DatabaseLicenseService(session_factory=mock_session_factory, table_name="test_table")
    
    return service, mock_result

@pytest.mark.asyncio
async def test_db_license_service_returns_key_on_success(db_license_service_with_mock_db):
    """DB에서 키를 성공적으로 조회했을 때, 해당 키를 반환하는지 테스트합니다."""
    service, mock_result = db_license_service_with_mock_db
    mock_result.scalar_one_or_none.return_value = "DB_FETCHED_KEY" # 성공 시나리오 설정
    result = await service.get_license(item_id="12345")
    assert result == "DB_FETCHED_KEY"

@pytest.mark.asyncio
async def test_db_license_service_returns_none_when_not_found(db_license_service_with_mock_db):
    """DB에서 키를 찾지 못했을 때, None을 반환하는지 테스트합니다."""
    service, mock_result = db_license_service_with_mock_db
    mock_result.scalar_one_or_none.return_value = None # 키가 없는 시나리오 설정
    result = await service.get_license(item_id="not_found_id")
    assert result is None
