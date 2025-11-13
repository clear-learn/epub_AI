# -*- coding: utf-8 -*-
import logging
from app.infrastructure.drm.kms_service import KmsKeyService
from app.domain.interfaces import ILicenseService

logger = logging.getLogger(__name__)

class LicenseService(ILicenseService):
    """
    라이선스 키 획득 로직을 처리하는 서비스입니다.
    현재는 AWS KMS를 통해 키를 복호화하는 방식만 지원합니다.
    """
    def __init__(self, kms_service: KmsKeyService):
        self.kms_service = kms_service

        async def get_license(self, item_id: str) -> str:
            """
            주어진 itemId에 해당하는 라이선스 키를 반환합니다.
            KMS 서비스를 호출하여 암호화된 키를 복호화합니다.
            """
            logger.info(f"KMS를 통해 '{item_id}'의 라이선스 키 조회를 시작합니다.")
            
            decrypted_key_str = await self.kms_service.get_decrypted_key(item_id)
            logger.info(f"'{item_id}'에 대한 라이선스 키를 성공적으로 조회했습니다.")

            return decrypted_key_str

    