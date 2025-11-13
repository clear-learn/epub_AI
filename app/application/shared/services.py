# -*- coding: utf-8 -*-
import logging
import io
import zipfile
import asyncio

from app.domain.models import AnalyzeOutput, FileCharStat
from app.core.epub_parser import EpubParser
from app.domain.errors import MissingTocError

logger = logging.getLogger(__name__)

class EbookAnalyzer:
    """EPUB 파일을 분석하여 구조화된 메타데이터를 추출하는 서비스입니다."""
    def __init__(self, parser: EpubParser):
        self._parser = parser

    def analyze(self, decrypted_epub: bytes) -> AnalyzeOutput:
        """EPUB 바이트를 분석하여 목차, 파일 통계 등을 반환합니다."""
        logger.info("EPUB 파일 분석을 시작합니다...")
        epub_buffer = io.BytesIO(decrypted_epub)
        with zipfile.ZipFile(epub_buffer, "r") as zf:
            opf_path = self._parser._find_opf_path(zf)
            opf_bytes = self._parser._zip_read(zf, opf_path)
            manifest, (spine_ids, spine_props) = self._parser._parse_opf_bytes(opf_bytes)
            toc = self._parser.get_toc_from_stream(zf, opf_path, manifest, spine_props)

            # 비즈니스 규칙: 목차(TOC)가 없는 EPUB은 처리하지 않음
            if not toc:
                raise MissingTocError("EPUB 파일에 목차(TOC) 정보가 존재하지 않아 처리를 중단합니다.")

            text_files = self._parser.get_text_files_from_spine(opf_path, manifest, spine_ids)
            file_char_counts = [
                FileCharStat(path=file_path, chars=len(self._parser.get_plain_text(self._parser._zip_read(zf, file_path))), has_text=True)
                for file_path in text_files
            ]
        logger.info(f"분석 완료: TOC {len(toc)}개, 텍스트 파일 {len(file_char_counts)}개")
        return AnalyzeOutput(file_char_counts=file_char_counts, toc=toc, meta={"file_count": len(zf.infolist())})

    async def analyze_async(self, decrypted_epub: bytes) -> AnalyzeOutput:
        """
        동기적인 analyze 메서드를 별도의 스레드에서 실행하여 비동기적으로 호출합니다.
        """
        return await asyncio.to_thread(self.analyze, decrypted_epub)
