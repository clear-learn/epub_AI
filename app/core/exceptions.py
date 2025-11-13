# -*- coding: utf-8 -*-
"""
애플리케이션 전반에서 사용될 커스텀 예외 클래스를 정의합니다.
각 예외는 특정한 실패 시나리오를 나타냅니다.
"""

class EpubFileNotFoundError(Exception):
    """S3 등 스토리지에서 EPUB 파일을 찾지 못했을 때 발생하는 예외입니다."""
    pass

class DrmDecryptionError(Exception):
    """DRM 복호화 과정에서 오류가 발생했을 때 사용됩니다."""
    pass

class EpubParsingError(Exception):
    """EPUB 파일의 구조가 잘못되었거나 필수 파일이 없어 파싱에 실패했을 때 발생합니다."""
    pass

class LlmApiError(Exception):
    """LLM API 호출 실패, 타임아웃, 응답 형식 오류 등 LLM 연동 관련 예외입니다."""
    pass

class ServerConfigurationError(Exception):
    """API 키 누락 등 서버 환경 설정이 잘못되었을 때 발생하는 예외입니다."""
    pass

class UnsupportedPurposeError(ValueError):
    """API 요청 시 지원하지 않는 'purpose'가 지정되었을 때 발생하는 예외입니다."""
    pass

class ExternalServiceError(Exception):
    """외부 서비스(AWS, LLM API 등) 연동 중 오류가 발생했을 때 사용됩니다."""
    pass
