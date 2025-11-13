# -*- coding: utf-8 -*-
import logging
from typing import List
import io
import zipfile
from app.core.epub_parser import EpubParser
from app.infrastructure.llm.openai_client import LlmClient

logger = logging.getLogger(__name__)

class HashtagExtractor:
    """EPUB 본문에서 LLM을 사용하여 해시태그를 추출합니다."""
    def __init__(self, parser: EpubParser, llm_client: LlmClient):
        self._parser = parser
        self._llm_client = llm_client

    async def extract_async(self, decrypted_epub: bytes) -> List[str]:
        """EPUB의 전체 텍스트를 추출하고 LLM을 호출하여 해시태그를 생성합니다."""
        logger.info("해시태그 추출을 위한 전체 텍스트 추출을 시작합니다...")
        
        full_text = []
        epub_buffer = io.BytesIO(decrypted_epub)
        with zipfile.ZipFile(epub_buffer, "r") as zf:
            opf_path = self._parser._find_opf_path(zf)
            manifest, (spine_ids, _) = self._parser._parse_opf_bytes(self._parser._zip_read(zf, opf_path))
            
            text_files = self._parser.get_text_files_from_spine(opf_path, manifest, spine_ids)
            for file_path in text_files:
                content_bytes = self._parser._zip_read(zf, file_path)
                plain_text = self._parser.get_plain_text(content_bytes)
                full_text.append(plain_text)
        
        combined_text = " ".join(full_text)
        logger.info(f"총 {len(combined_text)}자의 텍스트를 추출했습니다.")

        # TODO: LlmClient에 해시태그 추출을 위한 별도의 메서드(예: generate_hashtags)를 만들고 호출해야 합니다.
        # 현재는 suggest_start를 재활용하지만, 실제로는 별도 프롬프트와 함께 구현해야 합니다.
        # hashtags_json = await self._llm_client.generate_hashtags(combined_text)
        
        # 임시로 플레이스홀더를 반환합니다.
        return [f"text_extracted_{len(combined_text)}_chars", "#llm_called", "#sample_hashtag"]
