# -*- coding: utf-8 -*-
import json
import logging
from typing import List
import math
import os

from app.domain.models import LlmInput, LlmStartCandidate, TocItem, FileCharStat
from app.core.exceptions import LlmApiError, ServerConfigurationError

# LangChain 및 LangSmith 설정
try:
    from langchain_openai import ChatOpenAI
    from langsmith import traceable
    from langsmith.run_helpers import get_current_run_tree
    LANGCHAIN_INSTALLED = True
except ImportError:
    LANGCHAIN_INSTALLED = False
    ChatOpenAI = None
    def traceable(*args, **kwargs):
        """LangChain/LangSmith가 없을 때 데코레이터 더미"""
        def decorator(func):
            return func
        return decorator

    def get_current_run_tree():
        return None

def is_langsmith_available():
    """LangSmith를 사용할 수 있는지 런타임에 확인합니다."""
    return LANGCHAIN_INSTALLED and bool(os.getenv("LANGSMITH_API_KEY"))

logger = logging.getLogger(__name__)

class LlmClient:
    def __init__(self, client, model_name: str, system_prompt: str, user_prompt_template: str):
        """
        LangChain 기반 LLM 클라이언트

        Args:
            client: AsyncOpenAI 클라이언트 (하위 호환성 유지, 내부적으로는 LangChain 사용)
            model_name: 사용할 모델 이름
            system_prompt: 시스템 프롬프트
            user_prompt_template: 사용자 프롬프트 템플릿
        """
        self.legacy_client = client  # 하위 호환성을 위해 유지
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.user_prompt_template = user_prompt_template

        # LangChain ChatOpenAI 클라이언트 생성
        if LANGCHAIN_INSTALLED and os.getenv("OPENAI_API_KEY"):
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=0.3,
                model_kwargs={
                    "response_format": {"type": "json_object"}
                }
            )
            logger.info(f"LangChain ChatOpenAI 클라이언트가 생성되었습니다. (model: {model_name})")
        else:
            self.llm = None
            logger.warning("LangChain이 설치되지 않았거나 OpenAI API 키가 없습니다. LLM 기능이 제한됩니다.")

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

    @traceable(
        name="llm_suggest_start_point",
        run_type="llm",
        metadata={"component": "openai_client"}
    )
    async def suggest_start(self, llm_input: LlmInput, use_full_toc_analysis: bool = True) -> LlmStartCandidate:
        if not self.llm:
            raise ServerConfigurationError("LangChain ChatOpenAI 클라이언트가 초기화되지 않았습니다.")

        user_prompt_content = self.format_input_for_llm(llm_input.toc, llm_input.file_char_counts, use_full_toc_analysis)

        # LangSmith 메타데이터 추가
        if is_langsmith_available():
            try:
                run_tree = get_current_run_tree()
                if run_tree:
                    run_tree.add_metadata({
                        "model": self.model_name,
                        "toc_count": len(llm_input.toc),
                        "file_count": len(llm_input.file_char_counts),
                        "use_full_toc": use_full_toc_analysis
                    })
                    run_tree.add_tags(["epub", "start_point_detection", f"model:{self.model_name}"])
            except Exception as e:
                logger.warning(f"LangSmith 메타데이터 추가 실패: {e}")

        logger.info(f"LangChain ChatOpenAI ({self.model_name}) 호출을 시작합니다...")

        try:
            # LangChain을 통한 OpenAI 호출 (자동으로 LangSmith에 트레이싱됨)
            messages = [
                ("system", self.system_prompt),
                ("human", user_prompt_content)
            ]

            # ainvoke를 사용하여 비동기 호출
            response = await self.llm.ainvoke(messages)
            response_content = response.content

            logger.info(f"LangChain OpenAI 응답 수신 완료")

            if not response_content:
                raise ValueError("LLM으로부터 빈 응답을 받았습니다.")

            response_data = json.loads(response_content)

            start_file = response_data.get("file")
            if not start_file:
                raise ValueError("LLM 응답 JSON에 'file' 키가 없습니다.")

            result = LlmStartCandidate(
                file=start_file,
                anchor=response_data.get("anchor", None),
                rationale=response_data.get("rationale", "No rationale provided."),
                confidence=response_data.get("confidence", 0.7),
            )

            # LangSmith에 결과 메타데이터 추가
            if is_langsmith_available():
                try:
                    run_tree = get_current_run_tree()
                    if run_tree:
                        run_tree.add_metadata({
                            "result_file": result.file,
                            "result_confidence": result.confidence,
                            "has_anchor": bool(result.anchor)
                        })
                        # confidence 기반 태그 추가
                        if result.confidence >= 0.9:
                            run_tree.add_tags(["high_confidence"])
                        elif result.confidence < 0.5:
                            run_tree.add_tags(["low_confidence"])
                except Exception as e:
                    logger.warning(f"LangSmith 결과 메타데이터 추가 실패: {e}")

            logger.info(f"LLM 처리 완료: file={result.file}, confidence={result.confidence}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"LLM 응답 파싱 실패: {e}\n응답 내용: {response_content if 'response_content' in locals() else 'N/A'}")
            raise LlmApiError("LLM으로부터 유효하지 않은 형식의 응답을 받았습니다.")
        except ValueError as e:
            logger.error(f"LLM 응답 검증 실패: {e}")
            raise LlmApiError(str(e))
        except Exception as e:
            logger.exception(f"LLM API 호출 중 예상치 못한 오류 발생: {e}")
            raise LlmApiError(f"LLM API 호출 중 예상치 못한 오류가 발생했습니다: {str(e)}")