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
    LANGSMITH_INSTALLED = True
except ImportError:
    LANGSMITH_INSTALLED = False

    def traceable(*args, **kwargs):
        """LangSmith가 없을 때 데코레이터 더미"""
        def decorator(func):
            return func
        return decorator

    def get_current_run_tree():
        """LangSmith가 없을 때 더미 함수"""
        return None


# LangSmith 클라이언트는 lazy initialization
_langsmith_client = None

def get_langsmith_client():
    """LangSmith 클라이언트를 반환합니다. (lazy initialization)"""
    global _langsmith_client

    if not LANGSMITH_INSTALLED:
        return None

    if not os.getenv("LANGSMITH_API_KEY"):
        return None

    if _langsmith_client is None:
        _langsmith_client = Client()
        logger.info("LangSmith 클라이언트가 초기화되었습니다.")

    return _langsmith_client


def is_langsmith_available():
    """LangSmith를 사용할 수 있는지 확인합니다."""
    return LANGSMITH_INSTALLED and bool(os.getenv("LANGSMITH_API_KEY"))


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
        return str(dataset.id)
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


# ==================== 평가(Evaluation) 함수들 ====================

def run_evaluation(
    dataset_name: str,
    target_function: Callable,
    evaluators: List[Callable],
    experiment_prefix: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    데이터셋에 대해 평가를 실행합니다.

    Args:
        dataset_name: 평가할 데이터셋 이름
        target_function: 평가 대상 함수 (입력을 받아 출력을 반환)
        evaluators: 평가자 함수 리스트
        experiment_prefix: 실험 이름 접두사
        metadata: 실험 메타데이터

    Returns:
        평가 결과 딕셔너리 또는 None

    Example:
        >>> def my_epub_analyzer(inputs: dict) -> dict:
        ...     # 실제 분석 로직
        ...     return {"file": "chapter1.xhtml", "confidence": 0.95}
        >>>
        >>> evaluators = [accuracy_evaluator, confidence_evaluator]
        >>> results = run_evaluation(
        ...     dataset_name="epub_test_set",
        ...     target_function=my_epub_analyzer,
        ...     evaluators=evaluators,
        ...     experiment_prefix="epub_v1"
        ... )
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        logger.warning("LangSmith를 사용할 수 없어 평가를 건너뜁니다.")
        return None

    try:
        from langsmith import evaluate

        results = evaluate(
            target_function,
            data=dataset_name,
            evaluators=evaluators,
            experiment_prefix=experiment_prefix,
            metadata=metadata
        )

        logger.info(f"평가 완료: {dataset_name}")
        return results
    except Exception as e:
        logger.warning(f"평가 실행 실패: {e}")
        return None


def create_accuracy_evaluator(expected_key: str = "file") -> Callable:
    """
    정확도 평가자를 생성합니다.

    Args:
        expected_key: 비교할 출력 키 (기본값: "file")

    Returns:
        평가자 함수

    Example:
        >>> accuracy_eval = create_accuracy_evaluator("file")
        >>> result = accuracy_eval(run, example)
    """
    def accuracy_evaluator(run: Run, example: Example) -> Dict[str, Any]:
        """실제 출력과 예상 출력을 비교하여 정확도를 계산합니다."""
        try:
            if not run.outputs:
                return {"key": "accuracy", "score": 0.0, "comment": "출력 없음"}

            predicted = run.outputs.get(expected_key)
            expected = example.outputs.get(expected_key) if example.outputs else None

            if predicted == expected:
                return {"key": "accuracy", "score": 1.0}
            else:
                return {
                    "key": "accuracy",
                    "score": 0.0,
                    "comment": f"예상: {expected}, 실제: {predicted}"
                }
        except Exception as e:
            return {"key": "accuracy", "score": 0.0, "comment": f"평가 오류: {str(e)}"}

    return accuracy_evaluator


def create_confidence_evaluator(
    min_threshold: float = 0.7,
    confidence_key: str = "confidence"
) -> Callable:
    """
    신뢰도 평가자를 생성합니다.

    Args:
        min_threshold: 최소 신뢰도 임계값 (기본값: 0.7)
        confidence_key: 신뢰도 키 이름 (기본값: "confidence")

    Returns:
        평가자 함수

    Example:
        >>> confidence_eval = create_confidence_evaluator(min_threshold=0.8)
        >>> result = confidence_eval(run, example)
    """
    def confidence_evaluator(run: Run, example: Example) -> Dict[str, Any]:
        """출력의 신뢰도를 평가합니다."""
        try:
            if not run.outputs:
                return {"key": "confidence_check", "score": 0.0, "comment": "출력 없음"}

            confidence = run.outputs.get(confidence_key, 0.0)

            if confidence >= min_threshold:
                return {
                    "key": "confidence_check",
                    "score": 1.0,
                    "comment": f"신뢰도: {confidence:.2f}"
                }
            else:
                return {
                    "key": "confidence_check",
                    "score": 0.0,
                    "comment": f"낮은 신뢰도: {confidence:.2f} (최소: {min_threshold})"
                }
        except Exception as e:
            return {"key": "confidence_check", "score": 0.0, "comment": f"평가 오류: {str(e)}"}

    return confidence_evaluator


def create_latency_evaluator(max_seconds: float = 5.0) -> Callable:
    """
    지연시간 평가자를 생성합니다.

    Args:
        max_seconds: 최대 허용 지연시간 (초, 기본값: 5.0)

    Returns:
        평가자 함수

    Example:
        >>> latency_eval = create_latency_evaluator(max_seconds=3.0)
        >>> result = latency_eval(run, example)
    """
    def latency_evaluator(run: Run, example: Example) -> Dict[str, Any]:
        """실행 시간을 평가합니다."""
        try:
            if not run.end_time or not run.start_time:
                return {"key": "latency", "score": 0.0, "comment": "시간 정보 없음"}

            duration = (run.end_time - run.start_time).total_seconds()

            if duration <= max_seconds:
                score = 1.0
                comment = f"지연시간: {duration:.2f}초"
            else:
                # 초과한 만큼 점수 감점 (최소 0.0)
                score = max(0.0, 1.0 - (duration - max_seconds) / max_seconds)
                comment = f"높은 지연시간: {duration:.2f}초 (최대: {max_seconds}초)"

            return {"key": "latency", "score": score, "comment": comment}
        except Exception as e:
            return {"key": "latency", "score": 0.0, "comment": f"평가 오류: {str(e)}"}

    return latency_evaluator


def create_output_format_evaluator(required_keys: List[str]) -> Callable:
    """
    출력 형식 평가자를 생성합니다.

    Args:
        required_keys: 필수 출력 키 리스트

    Returns:
        평가자 함수

    Example:
        >>> format_eval = create_output_format_evaluator(["file", "anchor", "confidence"])
        >>> result = format_eval(run, example)
    """
    def format_evaluator(run: Run, example: Example) -> Dict[str, Any]:
        """출력이 필수 키를 모두 포함하는지 확인합니다."""
        try:
            if not run.outputs:
                return {"key": "format_check", "score": 0.0, "comment": "출력 없음"}

            missing_keys = [key for key in required_keys if key not in run.outputs]

            if not missing_keys:
                return {"key": "format_check", "score": 1.0, "comment": "모든 필수 키 존재"}
            else:
                return {
                    "key": "format_check",
                    "score": 0.0,
                    "comment": f"누락된 키: {', '.join(missing_keys)}"
                }
        except Exception as e:
            return {"key": "format_check", "score": 0.0, "comment": f"평가 오류: {str(e)}"}

    return format_evaluator


def get_evaluation_results(
    experiment_name: Optional[str] = None,
    limit: int = 10
) -> Optional[List[Dict[str, Any]]]:
    """
    평가 결과를 조회합니다.

    Args:
        experiment_name: 실험 이름 (None이면 최근 실험)
        limit: 조회할 결과 개수

    Returns:
        평가 결과 리스트 또는 None

    Example:
        >>> results = get_evaluation_results(experiment_name="epub_v1_20231201", limit=5)
        >>> for result in results:
        ...     print(f"정확도: {result['accuracy']}, 신뢰도: {result['confidence']}")
    """
    if not LANGSMITH_AVAILABLE or not langsmith_client:
        return None

    try:
        # LangSmith API를 통해 실험 결과 조회
        project_name = os.getenv("LANGSMITH_PROJECT", "ai-epub-api")

        # 실험별 run 조회
        runs = langsmith_client.list_runs(
            project_name=project_name,
            execution_order=1,
            filter=f'eq(name, "{experiment_name}")' if experiment_name else None
        )

        results = []
        for i, run in enumerate(runs):
            if i >= limit:
                break

            # 피드백 정보 수집
            feedbacks = langsmith_client.list_feedback(run_ids=[str(run.id)])
            feedback_scores = {fb.key: fb.score for fb in feedbacks}

            results.append({
                "run_id": str(run.id),
                "inputs": run.inputs,
                "outputs": run.outputs,
                "feedback_scores": feedback_scores,
                "latency_ms": (run.end_time - run.start_time).total_seconds() * 1000 if run.end_time and run.start_time else None
            })

        logger.info(f"평가 결과 {len(results)}개 조회 완료")
        return results
    except Exception as e:
        logger.warning(f"평가 결과 조회 실패: {e}")
        return None


def calculate_aggregate_metrics(
    evaluation_results: List[Dict[str, Any]]
) -> Dict[str, float]:
    """
    평가 결과에서 집계 메트릭을 계산합니다.

    Args:
        evaluation_results: get_evaluation_results() 반환값

    Returns:
        집계 메트릭 딕셔너리 (평균 정확도, 평균 신뢰도, 평균 지연시간 등)

    Example:
        >>> results = get_evaluation_results(limit=100)
        >>> metrics = calculate_aggregate_metrics(results)
        >>> print(f"평균 정확도: {metrics['avg_accuracy']:.2%}")
    """
    if not evaluation_results:
        return {}

    try:
        metrics: Dict[str, List[float]] = {}

        # 모든 피드백 점수 수집
        for result in evaluation_results:
            feedback_scores = result.get("feedback_scores", {})
            for key, score in feedback_scores.items():
                if key not in metrics:
                    metrics[key] = []
                metrics[key].append(score)

            # 지연시간 추가
            if result.get("latency_ms") is not None:
                if "latency_ms" not in metrics:
                    metrics["latency_ms"] = []
                metrics["latency_ms"].append(result["latency_ms"])

        # 평균 계산
        aggregates = {}
        for key, values in metrics.items():
            if values:
                aggregates[f"avg_{key}"] = sum(values) / len(values)
                aggregates[f"min_{key}"] = min(values)
                aggregates[f"max_{key}"] = max(values)

        logger.info(f"집계 메트릭 계산 완료: {len(aggregates)} 항목")
        return aggregates
    except Exception as e:
        logger.warning(f"집계 메트릭 계산 실패: {e}")
        return {}