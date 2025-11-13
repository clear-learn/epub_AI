# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timezone
from fastapi import Depends

from app.domain.models import UndrmInput, UndrmLog, UndrmPipelineOutput
from app.infrastructure.storage.s3_client import S3Client
from app.infrastructure.drm.adapter import UndrmAdapter
from app.domain.interfaces import ILogger, ILicenseService
from app.core.exceptions import DrmDecryptionError
from app.dependencies import get_s3_client, get_license_service, get_undrm_adapter, get_db_logger

logger = logging.getLogger(__name__)

class UndrmPipeline:
    def __init__(
        self,
        s3_client: S3Client = Depends(get_s3_client),
        license_service: ILicenseService = Depends(get_license_service),
        undrm_adapter: UndrmAdapter = Depends(get_undrm_adapter),
        db_logger: ILogger = Depends(get_db_logger),
    ):
        self.s3_client = s3_client
        self.license_service = license_service
        self.undrm_adapter = undrm_adapter
        self.db_logger = db_logger

    async def run(
        self, s3_bucket: str, s3_key: str, tenant_id: str, itemId: str, reason: str
    ) -> UndrmPipelineOutput:
        """
        공통 복호화 파이프라인.
        S3에서 EPUB을 가져와 복호화하고, 처리 상태 로그를 생성합니다.
        """
        encrypted_epub = await self.s3_client.get_object_bytes(bucket=s3_bucket, key=s3_key)
        license_key = await self.license_service.get_license(itemId)
        
        if not license_key:
            raise DrmDecryptionError(f"'{itemId}'에 대한 라이선스 키를 찾을 수 없습니다.")

        undrm_input = UndrmInput(
            encrypted_epub=encrypted_epub, license_key=license_key,
            grant_id=None, # grant_id는 더 이상 사용하지 않음
            tenant_id=tenant_id
        )
        
        start_time = datetime.now(timezone.utc)
        event_id = None
        try:
            output = await self.undrm_adapter.decrypt_async(undrm_input)
            
            log_entry = UndrmLog(
                tenant_id=tenant_id, itemId=itemId, grant_id="N/A",
                s3_bucket=s3_bucket, s3_key=s3_key, 
                reason=reason, status="PROCESSING", drm_type=output.drm_type,
                undrm_start_time=start_time.isoformat(), undrm_end_time=None
            )
            event_id = await self.db_logger.create_log(log_entry)
            
            return UndrmPipelineOutput(decrypted_epub=output.decrypted_epub, event_id=event_id)

        except Exception as e:
            log_entry = UndrmLog(
                tenant_id=tenant_id, itemId=itemId, grant_id="N/A",
                s3_bucket=s3_bucket, s3_key=s3_key,
                reason=reason, status="FAILURE", failure_reason=str(e),
                undrm_start_time=start_time.isoformat(), undrm_end_time=datetime.now(timezone.utc).isoformat()
            )
            await self.db_logger.create_log(log_entry)
            raise DrmDecryptionError(f"EPUB 복호화 파이프라인 실패: {e}")