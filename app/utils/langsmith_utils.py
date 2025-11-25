# -*- coding: utf-8 -*-
"""
LangSmith 유틸리티 함수 및 데코레이터
"""
import os
import logging
from functools import wraps
from typing import Optional, Dict, Any, Callable, List

logger = logging.getLogger(__name__)

# LangSmith 가용성 확인
try:
    from langsmith import traceable, Client, evaluate
    from langsmith.run_helpers import get_current_run_tree
    from langsmith.evaluation import EvaluationResult
    from langsmith.schemas import Example, Run
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
    comment: Optional[str] = None,
    correction: Optional[Dict[str, Any]] = None
) -> None:
    """
    LangSmith에 피드백을 기록합니다.

    Args:
        run_id: LangSmith run ID
        key: 피드백 키 (예: "accuracy", "relevance", "quality")
        score: 점수 (0.0 ~ 1.0)
        comment: 추가 코멘트
        correction: 수정된 올바른 출력값 (선택사항)
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return

    try:
        feedback_kwargs = {
            "run_id": run_id,
            "key": key,
            "score": score,
        }
        if comment:
            feedback_kwargs["comment"] = comment
        if correction:
            feedback_kwargs["correction"] = correction

        langsmith_client.create_feedback(**feedback_kwargs)
        logger.info(f"LangSmith 피드백 기록 완료: {key}={score}")
    except Exception as e:
        logger.warning(f"LangSmith 피드백 기록 실패: {e}")


def create_dataset(
    dataset_name: str,
    description: Optional[str] = None
) -> Optional[str]:
    """
    LangSmith 데이터셋을 생성합니다.

    Args:
        dataset_name: 데이터셋 이름
        description: 데이터셋 설명

    Returns:
        생성된 데이터셋 ID 또는 None
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return None

    try:
        dataset = langsmith_client.create_dataset(
            dataset_name=dataset_name,
            description=description
        )
        logger.info(f"LangSmith 데이터셋 생성 완료: {dataset_name} (ID: {dataset.id})")
        return dataset.id
    except Exception as e:
        logger.warning(f"LangSmith 데이터셋 생성 실패: {e}")
        return None


def add_example_to_dataset(
    dataset_name: str,
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    데이터셋에 예제를 추가합니다.

    Args:
        dataset_name: 데이터셋 이름
        inputs: 입력 데이터
        outputs: 기대 출력 데이터
        metadata: 추가 메타데이터

    Returns:
        성공 여부
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return False

    try:
        langsmith_client.create_example(
            inputs=inputs,
            outputs=outputs,
            dataset_name=dataset_name,
            metadata=metadata
        )
        logger.info(f"LangSmith 데이터셋에 예제 추가 완료: {dataset_name}")
        return True
    except Exception as e:
        logger.warning(f"LangSmith 예제 추가 실패: {e}")
        return False


def get_run_url(run_id: str) -> Optional[str]:
    """
    LangSmith Run의 웹 URL을 생성합니다.

    Args:
        run_id: LangSmith run ID

    Returns:
        LangSmith 웹 URL 또는 None
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return None

    try:
        # LangSmith 웹 URL 포맷
        project_name = os.getenv("LANGSMITH_PROJECT", "ai-epub-api")
        return f"https://smith.langchain.com/o/default/projects/{project_name}/r/{run_id}"
    except Exception as e:
        logger.warning(f"LangSmith URL 생성 실패: {e}")
        return None


def log_error_to_langsmith(
    run_id: str,
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    에러를 LangSmith에 피드백으로 기록합니다.

    Args:
        run_id: LangSmith run ID
        error: 발생한 예외
        context: 에러 발생 컨텍스트
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return

    try:
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        if context:
            error_info.update(context)

        langsmith_client.create_feedback(
            run_id=run_id,
            key="error",
            score=0.0,
            comment=f"Error: {type(error).__name__} - {str(error)}",
            correction=error_info
        )
        logger.info(f"LangSmith에 에러 기록 완료: {type(error).__name__}")
    except Exception as e:
        logger.warning(f"LangSmith 에러 기록 실패: {e}")