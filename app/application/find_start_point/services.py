# -*- coding: utf-8 -*-
import logging
from app.domain.models import DecideInput, DecideOutput

logger = logging.getLogger(__name__)

class StartPointDetector:
    """LLM의 추천을 바탕으로 본문 시작점을 결정합니다."""
    def decide(self, decide_input: DecideInput) -> DecideOutput:
        """LLM 추천이 없으면 오류를 발생시키고, 있으면 최종 결정으로 채택합니다."""
        logger.info("LLM 기반으로 시작점 결정을 시작합니다.")
        if not decide_input.llm or not decide_input.llm.file:
            raise ValueError("LLM의 추천이 필요하지만 제공되지 않았습니다.")
        llm_candidate = decide_input.llm

        # ── anchor 정규화: 앞의 '#' 제거, 빈 문자열이면 None
        anchor = llm_candidate.anchor
        if isinstance(anchor, str):
            anchor = anchor.lstrip('#')  # 맨 앞(연속) '#' 제거
            if anchor == "":
                anchor = None

        logger.info(f"LLM 추천을 최종 시작점으로 채택: {llm_candidate.file}")
        return DecideOutput(
            start_file=llm_candidate.file,
            anchor=anchor,
            confidence=llm_candidate.confidence or 0.7,
            rationale=llm_candidate.rationale
        )
