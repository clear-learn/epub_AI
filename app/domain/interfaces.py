# -*- coding: utf-8 -*-
"""
도메인 계층의 추상 인터페이스를 정의합니다.

이 인터페이스들은 시스템의 핵심 개념과 규칙을 정의하며,
인프라스트럭처 계층의 구체적인 구현체들이 따라야 할 계약(Contract) 역할을 합니다.
"""
from abc import ABC, abstractmethod
from app.domain.models import UndrmLog

class ILogger(ABC):
    """
    감사 로그 생성을 위한 추상 인터페이스입니다.
    모든 로거 구현체는 이 인터페이스를 상속받아야 합니다.
    """
    @abstractmethod
    def create_log(self, log_data: UndrmLog) -> str:
        """초기 감사 로그를 생성하고, 생성된 로그의 고유 ID를 반환합니다."""
        pass

    @abstractmethod
    def update_log(self, event_id: str, status: str, end_time: str, failure_reason: str = None):
        """기존 감사 로그를 업데이트합니다."""
        pass

class ILicenseService(ABC):
    """
    라이선스 키 조회를 위한 추상 인터페이스입니다.
    """
    @abstractmethod
    async def get_license(self, item_id: str) -> str:
        """주어진 item_id에 해당하는 라이선스 키를 반환합니다."""
        pass
