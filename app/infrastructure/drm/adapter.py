# -*- coding: utf-8 -*-
import os
# import time
# import logging
# logger = logging.getLogger(__name__)

import base64
import hmac
import hashlib
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import List
import asyncio

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding

from app.domain.models import UndrmInput, UndrmOutput

# --- 상수 정의 ---
# 원본 C# Decryptor와 호환성을 유지하기 위한 상수들입니다.

# AES-256-CBC 복호화에 사용될 고정 IV(초기화 벡터)
AES_256_IV_FILE = bytes([
    0x2A, 0x22, 0x32, 0x62, 0x5C, 0x5F, 0x6F, 0x67,
    0x75, 0x6D, 0x7B, 0x29, 0x2B, 0x2E, 0x78, 0x69,
])

# HMAC-SHA1 무결성 검증에 사용될 고정 키
HMAC_SHA1_KEY_FILE_V2 = bytes([
    0x3E, 0x40, 0x7A, 0x6C, 0x71, 0x38, 0x7D, 0x7C, 0x51, 0x70, 0x2C, 0x62, 0x53, 0x39, 0x5F, 0x7E,
    0x2B, 0x78, 0x57, 0x31, 0x26, 0x4E, 0x49, 0x71, 0x68, 0x29, 0x31, 0x36, 0x25, 0x3B, 0x41, 0x74,
    0x59, 0x3B, 0x73, 0x36, 0x30, 0x31, 0x78, 0x35, 0x7A, 0x6C, 0x23, 0x5F, 0x61, 0x4C, 0x41, 0x7E,
    0x60, 0x34, 0x4D, 0x2A, 0x71, 0x50, 0x3B, 0x44, 0x64, 0x2B, 0x3D, 0x37, 0x26, 0x2C, 0x4A, 0x44,
])

# 환경변수/설정에서 동시성 상한 주입 (기본: CPU 코어 * 2, 최소 5)
_DRM_MAX_CONC = int(os.getenv("DRM_MAX_CONCURRENCY", max(5, (os.cpu_count() or 2)*2)))
_DRM_SEM = asyncio.BoundedSemaphore(_DRM_MAX_CONC)

class UndrmAdapter:
    """
    메모리 내에서 EPUB 파일의 DRM을 제거하는 역할을 담당하는 어댑터입니다.
    
    이 클래스는 원본 EPUB 바이트 스트림을 입력받아 다음 작업을 수행합니다:
    1. EPUB(ZIP) 파일을 열어 `META-INF/encryption.xml`을 파싱하여 암호화된 파일 목록을 확인.
    2. 암호화된 각 파일을 스트림 상에서 읽어 복호화.
    3. 복호화된 파일과 나머지 파일들을 새로운 EPUB(ZIP) 스트림에 씀.
    
    모든 과정은 디스크 I/O 없이 메모리 내에서만 처리됩니다.
    """

    def _read_uint32_le(self, b: bytes, off: int) -> int:
        """리틀 엔디언 형식의 4바이트를 부호 없는 32비트 정수로 읽습니다."""
        return int.from_bytes(b[off:off+4], byteorder="little", signed=False)

    def _compute_hmac_sha1(self, data: bytes) -> bytes:
        """주어진 데이터의 HMAC-SHA1 다이제스트를 계산합니다."""
        return hmac.new(HMAC_SHA1_KEY_FILE_V2, data, hashlib.sha1).digest()

    def _secure_equals(self, a: bytes, b: bytes) -> bool:
        """타이밍 공격에 안전한 방식으로 두 바이트 시퀀스를 비교합니다."""
        return hmac.compare_digest(a, b)

    def _decrypt_aes256_cbc_pkcs7(self, enc: bytes, key32: bytes, iv: bytes) -> bytes:
        """AES-256-CBC로 암호화된 데이터를 복호화하고 PKCS7 패딩을 제거합니다."""
        backend = default_backend()
        cipher = Cipher(algorithms.AES(key32), modes.CBC(iv), backend=backend)
        decryptor = cipher.decryptor()
        padded = decryptor.update(enc) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded) + unpadder.finalize()
        return data

    def _parse_encryption_xml_from_bytes(self, xml_bytes: bytes) -> List[str]:
        """`encryption.xml` 파일의 바이트 데이터를 파싱하여 암호화된 파일 경로 목록을 추출합니다."""
        try:
            root = ET.fromstring(xml_bytes)
            ns = {"enc": "http://www.w3.org/2001/04/xmlenc#"}
            files: List[str] = []
            for ed in root.findall(".//enc:EncryptedData", ns):
                cref = ed.find("enc:CipherData/enc:CipherReference", ns)
                if cref is not None:
                    uri = cref.attrib.get("URI")
                    if uri:
                        files.append(uri)
            return files
        except Exception:
            # XML 파싱 실패 시 빈 목록 반환
            return []

    def _decrypt_file_native_v2(self, data: bytes, key32: bytes) -> bytes:
        """
        네이티브 v2 형식으로 암호화된 단일 파일 데이터를 복호화합니다.
        이 형식은 [헤더][HMAC 일부][암호문][HMAC 나머지] 구조를 가집니다.
        """
        if len(data) < 32:
            raise ValueError("암호화된 데이터가 너무 짧습니다.")

        # 1. 헤더 파싱
        off = 0
        dst_len = self._read_uint32_le(data, off); off += 4  # 원본 데이터 길이
        enc_len = self._read_uint32_le(data, off); off += 4  # 암호문 길이
        hmac_front = self._read_uint32_le(data, off); off += 4  # 앞부분 HMAC 길이

        if not (0 < hmac_front <= 20):
            raise ValueError("잘못된 HMAC 길이입니다.")

        # 2. 데이터 길이 검증
        total_expected = off + hmac_front + enc_len + (20 - hmac_front)
        if total_expected > len(data):
            raise ValueError("데이터 길이가 예상과 다릅니다.")

        # 3. HMAC 조각 재구성
        hmac_bytes = bytearray(20)
        hmac_bytes[0:hmac_front] = data[off:off+hmac_front]; off += hmac_front
        enc = data[off:off+enc_len]; off += enc_len
        if hmac_front < 20:
            remaining_hmac = 20 - hmac_front
            hmac_bytes[hmac_front:20] = data[off:off+remaining_hmac]

        # 4. HMAC 무결성 검증
        calculated_hmac = self._compute_hmac_sha1(enc)
        if not self._secure_equals(bytes(hmac_bytes), calculated_hmac):
            raise RuntimeError("HMAC 검증에 실패했습니다. 데이터가 변조되었거나 키가 잘못되었습니다.")

        # 5. 데이터 복호화
        plain = self._decrypt_aes256_cbc_pkcs7(enc, key32, AES_256_IV_FILE)
        if len(plain) < dst_len:
            raise ValueError("복호화된 데이터가 원본보다 짧습니다.")

        # 6. 원본 길이만큼 잘라서 반환
        return plain[:dst_len]

    def decrypt(self, undrm_input: UndrmInput) -> UndrmOutput:
        """
        암호화된 EPUB 바이트를 입력받아 DRM을 제거하고 복호화된 EPUB 바이트를 반환합니다.
        """
        # 1. Base64로 인코딩된 라이선스 키를 디코딩하고 유효성을 검사합니다.
        try:
            key = base64.b64decode(undrm_input.license_key)
        except Exception as e:
            raise ValueError(f"잘못된 Base64 키 형식입니다: {e}")

        if len(key) < 32:
            raise ValueError("AES-256 키는 반드시 32바이트 이상이어야 합니다.")
        key32 = key[:32]  # 32바이트로 정규화

        input_buffer = io.BytesIO(undrm_input.encrypted_epub)
        output_buffer = io.BytesIO()

        # 2. 입력 EPUB(ZIP) 파일을 읽기 모드로 엽니다.
        with zipfile.ZipFile(input_buffer, "r") as in_zip:
            # 3. `encryption.xml`을 찾아 암호화된 파일 목록을 가져옵니다.
            try:
                enc_xml_bytes = in_zip.read("META-INF/encryption.xml")
                enc_files = self._parse_encryption_xml_from_bytes(enc_xml_bytes)
            except KeyError:
                # `encryption.xml`이 없으면 DRM이 없거나 다른 형식으로 간주하고,
                # 원본 파일을 그대로 복사하여 반환합니다.
                input_buffer.seek(0)
                return UndrmOutput(decrypted_epub=input_buffer.read(), drm_type="V2")

            # 4. 새로운 EPUB(ZIP) 파일을 쓰기 모드로 준비합니다.
            # with zipfile.ZipFile(output_buffer, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
            with zipfile.ZipFile(output_buffer, "w", compression=zipfile.ZIP_STORED) as out_zip:

                # 5. 원본 ZIP의 모든 파일을 순회합니다.
                for item in in_zip.infolist():
                    # DRM 메타데이터 파일은 새 ZIP에 포함하지 않습니다.
                    if item.filename == "META-INF/encryption.xml":
                        continue

                    content = in_zip.read(item.filename)
                    # 6. 암호화된 파일 목록에 해당 파일이 있으면 복호화를 수행합니다.
                    if item.filename in enc_files:
                        try:
                            content = self._decrypt_file_native_v2(content, key32)
                        except Exception as e:
                            raise RuntimeError(f"파일 복호화에 실패했습니다: {item.filename}") from e
                    
                    # 7. 복호화된 (또는 원본) 내용을 새 ZIP에 씁니다.
                    # EPUB 표준에 따라 'mimetype' 파일은 압축하지 않습니다.
                    # compress_type = zipfile.ZIP_STORED if item.filename == 'mimetype' else zipfile.ZIP_DEFLATED
                    # out_zip.writestr(item, content, compress_type=compress_type)
                    out_zip.writestr(item, content, compress_type=zipfile.ZIP_STORED)

        # 8. 메모리에 생성된 새 EPUB 파일의 바이트를 DTO에 담아 반환합니다.
        output_buffer.seek(0)
        return UndrmOutput(decrypted_epub=output_buffer.read(), drm_type="V2")

    async def decrypt_async(self, undrm_input: UndrmInput) -> UndrmOutput:
        """
        동기적인 decrypt 메서드를 별도의 스레드에서 실행하여 비동기적으로 호출합니다.
        """
        # async with _DRM_SEM:
        #     return await asyncio.to_thread(self.decrypt, undrm_input)
        
        # t0 = time.perf_counter()
        await _DRM_SEM.acquire()
        # t1 = time.perf_counter()
        try:
            out = await asyncio.to_thread(self.decrypt, undrm_input)
            return out
        finally:
            # t2 = time.perf_counter()
            _DRM_SEM.release()
            # logger.info("DRM decrypt queued_wait=%.3fs exec=%.3fs", t1 - t0, t2 - t1)
        