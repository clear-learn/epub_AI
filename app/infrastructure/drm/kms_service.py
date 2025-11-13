# -*- coding: utf-8 -*-
import logging
from aiobotocore.session import get_session
import base64
from typing import Optional
from botocore.exceptions import ClientError
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

class KmsKeyService:
    """
    AWS KMS(Key Management Service)와의 연동을 처리하는 서비스입니다.
    """
    def __init__(self, aws_profile: Optional[str], region_name: str, key_id: str):
        self.key_id = key_id
        self.region_name = region_name
        
        # 암호화된 라이선스 키 (테스트용 더미 데이터)
        self.encrypted_license_key_b64 = "ZHVtbXlfZGF0YQ=="
        
        self.session = get_session()
        if aws_profile:
            self.session.set_config_variable('profile', aws_profile)
            logger.info(f"Aiobotocore KMS 세션 생성 완료 (리전: {region_name}, 프로필: {aws_profile})")
        else:
            logger.info(f"Aiobotocore KMS 세션 생성 완료 (리전: {region_name}, 기본 자격증명 사용)")

    async def get_decrypted_key(self, item_id: str) -> str:
        """
        주어진 itemId에 해당하는 암호화된 키를 KMS로 복호화합니다.
        현재는 itemId와 무관하게 하드코딩된 암호화 키를 복호화합니다.
        """
        if not self.key_id:
            raise ValueError("KMS Key ID가 설정되지 않았습니다.")

        logger.info(f"KMS 키 복호화를 시작합니다 (Key ID: {self.key_id}, itemId: {item_id})...")
        
        try:
            async with self.session.create_client("kms", region_name=self.region_name) as client:
                # Base64로 인코딩된 암호화 텍스트를 디코딩하여 바이너리로 변환
                ciphertext_blob = base64.b64decode(self.encrypted_license_key_b64)
                
                response = await client.decrypt(
                    KeyId=self.key_id,
                    CiphertextBlob=ciphertext_blob
                )
                
                # 복호화된 키는 'Plaintext' 필드에 바이너리로 반환됨
                decrypted_key_bytes = response['Plaintext']
                
                # 문자열 키를 암호화했으므로, UTF-8로 디코딩하여 반환
                decrypted_key_str = decrypted_key_bytes.decode('utf-8')
                logger.info("KMS 키 복호화 성공.")
                
                return decrypted_key_str

        except ClientError as e:
            error_message = f"KMS 키 복호화 중 오류 발생: {e}"
            logger.error(error_message)
            raise ExternalServiceError(error_message) from e
        except Exception as e:
            error_message = f"KMS 복호화 중 예상치 못한 오류 발생: {e}"
            logger.error(error_message)
            raise ExternalServiceError(error_message) from e