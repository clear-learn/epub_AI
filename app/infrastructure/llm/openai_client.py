# -*- coding: utf-8 -*-
import json
import logging
from typing import List
import math
from openai import AsyncOpenAI, RateLimitError, APITimeoutError

from app.domain.models import LlmInput, LlmStartCandidate, TocItem, FileCharStat
from app.core.exceptions import LlmApiError, ServerConfigurationError

logger = logging.getLogger(__name__)

class LlmClient:
    def __init__(self, client: AsyncOpenAI, model_name: str, system_prompt: str, user_prompt_template: str):
        self.client = client
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.user_prompt_template = user_prompt_template
        
        if not self.client:
            logger.warning("AsyncOpenAI 클라이언트가 제공되지 않았습니다. LLM 관련 기능이 비활성화됩니다.")

    def format_input_for_llm(self, toc: List[TocItem], file_stats: List[FileCharStat], use_full_toc_analysis: bool = True) -> str:
        """LLM에 전달할 메타데이터를 TOC와 파일 통계를 병합하여 JSON 문자열로 포맷합니다."""
        
        char_counts_map = {stat.path: stat.chars for stat in file_stats}
        
        toc_with_chars = []
        sort = 0
        for item in toc:
            path_without_anchor = item.href.split('#')[0]
            chars = char_counts_map.get(path_without_anchor, 0)
            sort = sort + 1
            toc_with_chars.append({
                "순서": sort, "title": item.title, "href": item.href, "level": item.level, "chars": chars
            })

        # full_payload가 False일 때 TOC 축약
        if not use_full_toc_analysis and len(toc_with_chars) >= 7:
            n = len(toc_with_chars)
            limit = max(math.ceil(n / 2), 5)          # 최소 5개 보장
            actual = min(n, limit)                    # 실제로 잘려 나가는 개수
            toc_with_chars = toc_with_chars[:limit]   # limit가 n보다 커도 안전함
            logger.info(f"TOC가 7개 이상이므로 {actual}개로 축약합니다. (최소 5개 보장)")

        metadata = {
            "task_description": "목차와 각 항목의 글자 수('chars')를 분석하여 실제 내용이 시작되는 첫 번째 항목을 선택하세요.\n목차는 각 장의 표지로 이동 할 수 있으니, file_stats을 추가로 참고하세요.\n입력된 순서가 실제 도서의 순서임을 명심하세요.",
            "table_of_contents_with_stats": toc_with_chars,
            "file_stats": char_counts_map
        }
        return json.dumps(metadata, indent=2, ensure_ascii=False)

    async def suggest_start(self, llm_input: LlmInput, use_full_toc_analysis: bool = True) -> LlmStartCandidate:
        if not self.client:
            raise ServerConfigurationError("OpenAI API 키가 설정되지 않아 LLM을 호출할 수 없습니다.")

        user_prompt_content = self.format_input_for_llm(llm_input.toc, llm_input.file_char_counts, use_full_toc_analysis)
        
        logger.info(f"OpenAI API ({self.model_name}) 호출을 시작합니다...")
        response_content = ""
        try:
            if self.model_name.startswith('gpt-5'):
                # GPT-5 계열 리즈닝 API 호출
                payload = {
                    "model": self.model_name,
                    "input": [
                        {"role": "developer", "content": [{"type": "input_text", "text": self.system_prompt}]},
                        {"role": "user", "content": [{"type": "input_text", "text": user_prompt_content}]},
                    ],
                    "text": {"format": {"type": "json_object"}, "verbosity": "low"},
                    "reasoning": {"effort": "minimal"},
                }
                response = await self.client.responses.create(**payload)
                
                if hasattr(response, "output_text") and response.output_text:
                    response_content = response.output_text
                elif hasattr(response, "output"):
                    parts = [o.get("text", "") for o in response.output if o.get("type") == "output_text"]
                    response_content = "\n".join(parts).strip()

            else:
                # 기존 GPT-4.1 계열 API 호출
                response = await self.client.responses.create(
                    model=self.model_name,
                    input=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt_content},
                    ],
                    text={"format": {"type": "json_object"}, "verbosity": "medium"},
                    temperature=0.3,
                )
                response_content = response.output_text

            logger.info(f"OpenAI API 응답 수신: {response_content}")
            
            if not response_content:
                raise ValueError("LLM으로부터 빈 응답을 받았습니다.")
                
            response_data = json.loads(response_content)
            
            start_file = response_data.get("file")
            if not start_file:
                raise ValueError("LLM 응답 JSON에 'file' 키가 없습니다.")

            return LlmStartCandidate(
                file=start_file,
                anchor=response_data.get("anchor", None),
                rationale=response_data.get("rationale", "No rationale provided."),
                confidence=response_data.get("confidence", 0.7),
            )
        except (RateLimitError, APITimeoutError) as e:
            logger.error(f"OpenAI API 속도 제한 또는 타임아웃 오류: {e}")
            raise LlmApiError("LLM 서비스가 응답하지 않거나 요청 제한에 도달했습니다.")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"LLM 응답 파싱 실패: {e}\n응답 내용: {response_content}")
            raise LlmApiError("LLM으로부터 유효하지 않은 형식의 응답을 받았습니다.")
        except Exception as e:
            logger.exception(f"LLM API 호출 중 예상치 못한 오류 발생: {e}")
            raise LlmApiError(f"LLM API 호출 중 예상치 못한 오류가 발생했습니다.")