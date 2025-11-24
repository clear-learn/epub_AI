# -*- coding: utf-8 -*-
"""
LangSmith 유틸리티 함수 및 데코레이터
"""
import os
import logging
from functools import wraps
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# LangSmith 가용성 확인
try:
    from langsmith import traceable, Client
    from langsmith.run_helpers import get_current_run_tree
    LANGSMITH_AVAILABLE = bool(os.getenv("LANGSMITH_API_KEY"))

    if LANGSMITH_AVAILABLE:
        langsmith_client = Client()
        logger.info("LangSmith 클라이언트가 초기화되었습니다.")
    else:
        langsmith_client = None

except ImportError:
    LANGSMITH_AVAILABLE = False
    langsmith_client = None

    def traceable(*args, **kwargs):
        """LangSmith가 없을 때 데코레이터 더미"""
        def decorator(func):
            return func
        return decorator

    def get_current_run_tree():
        """LangSmith가 없을 때 더미 함수"""
        return None


def add_langsmith_metadata(metadata: Dict[str, Any]) -> None:
    """
    현재 실행 중인 LangSmith trace에 메타데이터를 추가합니다.

    Args:
        metadata: 추가할 메타데이터 딕셔너리
    """
    if not LANGSMITH_AVAILABLE:
        return

    try:
        run_tree = get_current_run_tree()
        if run_tree:
            for key, value in metadata.items():
                run_tree.add_metadata({key: value})
    except Exception as e:
        logger.warning(f"LangSmith 메타데이터 추가 실패: {e}")


def add_langsmith_tags(tags: list[str]) -> None:
    """
    현재 실행 중인 LangSmith trace에 태그를 추가합니다.

    Args:
        tags: 추가할 태그 리스트
    """
    if not LANGSMITH_AVAILABLE:
        return

    try:
        run_tree = get_current_run_tree()
        if run_tree:
            run_tree.add_tags(tags)
    except Exception as e:
        logger.warning(f"LangSmith 태그 추가 실패: {e}")


def log_langsmith_feedback(
    run_id: str,
    key: str,
    score: float,
    comment: Optional[str] = None
) -> None:
    """
    LangSmith에 피드백을 기록합니다.

    Args:
        run_id: LangSmith run ID
        key: 피드백 키 (예: "accuracy", "relevance")
        score: 점수 (0.0 ~ 1.0)
        comment: 추가 코멘트
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return

    try:
        langsmith_client.create_feedback(
            run_id=run_id,
            key=key,
            score=score,
            comment=comment
        )
        logger.info(f"LangSmith 피드백 기록 완료: {key}={score}")
    except Exception as e:
        logger.warning(f"LangSmith 피드백 기록 실패: {e}")