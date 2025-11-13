# -*- coding: utf-8 -*-
import logging
import asyncio
import io
import random
from typing import Optional

from botocore.exceptions import ClientError, EndpointConnectionError, ConnectionClosedError
from app.core.exceptions import EpubFileNotFoundError, ExternalServiceError

logger = logging.getLogger(__name__)

# 서버 전역 동시 S3 다운로드 제한 (머신/네트워크에 맞게 조정)
_S3_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(8)

class S3Client:
    """
    앱 시작 시 lifespan에서 생성한 싱글톤 aioboto3 S3 클라이언트를 주입받아 사용합니다.
    """

    def __init__(self, s3_client):
        """
        Args:
            s3_client: lifespan에서 __aenter__된 공유 aioboto3 s3 client
        """
        self.s3 = s3_client
        logger.info("S3Client가 공유 s3 클라이언트로 초기화되었습니다.")

    async def _head(self, bucket: str, key: str):
        try:
            return await self.s3.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                raise EpubFileNotFoundError(f"S3 버킷 '{bucket}'에서 '{key}' 파일을 찾을 수 없습니다.")
            raise

    async def get_object_bytes(self, bucket: str, key: str) -> bytes:
        """
        견고한 다운로드: Range GET으로 스트리밍 + 재시도/재개.
        중간에 끊겨도 이어받기 때문에 ContentLengthError/EOF에 강함.
        """
        logger.info(f"S3 객체 다운로드 시작: s3://{bucket}/{key}")
        async with _S3_DOWNLOAD_SEMAPHORE:
            try:
                meta = await self._head(bucket, key)
            except EpubFileNotFoundError:
                logger.error(f"파일 없음: s3://{bucket}/{key}")
                raise
            except Exception as e:
                logger.exception("HEAD 실패")
                raise ExternalServiceError(f"S3 HEAD 실패: {e}") from e

            total = meta.get("ContentLength")
            checksum = meta.get("ChecksumSHA256")  # 업로드 시 설정했다면 검증에 활용 가능

            buf = io.BytesIO()
            pos = 0
            max_retries = 5
            chunk_size = 8 * 1024 * 1024  # 8MB

            while pos < total:
                end = min(pos + chunk_size - 1, total - 1)
                attempt = 0
                while True:
                    try:
                        resp = await self.s3.get_object(
                            Bucket=bucket, Key=key, Range=f"bytes={pos}-{end}"
                        )
                        async with resp["Body"] as body:
                            part = await body.read()
                            if part:
                                buf.write(part)
                        pos = buf.tell()
                        break  # 청크 성공 → 다음 청크로
                    except ClientError as e:
                        # 404/403 등 단번에 중단할 에러
                        if e.response["Error"]["Code"] in ("NoSuchKey", "AccessDenied"):
                            logger.error(f"S3 접근 오류: {e}")
                            raise ExternalServiceError(f"S3 접근 오류: {e}") from e
                        # 그 외는 재시도
                        attempt += 1
                        if attempt > max_retries:
                            logger.exception("S3 청크 재시도 초과")
                            raise ExternalServiceError(f"S3 청크 재시도 초과: {e}") from e
                        await asyncio.sleep(min(10, (2 ** attempt) * 0.2 + random.random()))
                    except (EndpointConnectionError, ConnectionClosedError, asyncio.TimeoutError) as e:
                        attempt += 1
                        if attempt > max_retries:
                            logger.exception("네트워크/타임아웃 재시도 초과")
                            raise ExternalServiceError(f"S3 네트워크 오류: {e}") from e
                        await asyncio.sleep(min(10, (2 ** attempt) * 0.2 + random.random()))
                    except Exception as e:
                        attempt += 1
                        if attempt > max_retries:
                            logger.exception("예상치 못한 예외 재시도 초과")
                            raise ExternalServiceError(f"S3 다운로드 실패: {e}") from e
                        await asyncio.sleep(min(10, (2 ** attempt) * 0.2 + random.random()))

            data = buf.getvalue()

            # 길이 검증 (헤더 약속과 실제 바이트가 맞는지)
            if total is not None and len(data) != total:
                logger.error(f"길이 불일치: expected={total}, got={len(data)}")
                raise ExternalServiceError(
                    f"S3 다운로드 길이 불일치 (expected={total}, got={len(data)})"
                )

            # (옵션) 체크섬 검증 – 업로드 시 ChecksumSHA256 사용했다면 여기에 대조
            # if checksum:
            #     import base64, hashlib
            #     got = base64.b64encode(hashlib.sha256(data).digest()).decode()
            #     if got != checksum:
            #         raise ExternalServiceError("S3 체크섬 불일치")

            logger.info(f"S3 객체 다운로드 완료: {len(data)} bytes")
            return data
