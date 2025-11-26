# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timezone

from app.domain.models import LlmInput, DecideInput, UndrmPipelineOutput
from app.core.exceptions import ServerConfigurationError
from app.infrastructure.llm.openai_client import LlmClient
from app.domain.interfaces import ILogger
from app.application.shared.services import EbookAnalyzer
from .services import StartPointDetector
from app.application.shared.pipeline import UndrmPipeline

logger = logging.getLogger(__name__)

async def find_start_point(
    s3_bucket: str,
    s3_key: str,
    tenant_id: str,
    itemId: str,
    use_full_toc_analysis: bool,
    analyzer: EbookAnalyzer,
    llm_client: LlmClient,
    detector: StartPointDetector,
    db_logger: ILogger,
    pipeline: UndrmPipeline,
) -> dict:
    """
    '본문 시작점 찾기' 유스케이스.
    복호화 파이프라인을 실행하고, 분석 및 LLM 추론을 통해 시작점을 결정합니다.
    """
    pipeline_output = await pipeline.run(
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        tenant_id=tenant_id,
        itemId=itemId,
        reason="find_start_point"
    )
    
    event_id = pipeline_output.event_id
    decrypted_epub = None  # Ensure decrypted_epub is defined

    try:
        decrypted_epub = pipeline_output.decrypted_epub
        
        analysis = await analyzer.analyze_async(decrypted_epub)

        if not llm_client.llm:
            raise ServerConfigurationError("이 기능은 LangChain ChatOpenAI 클라이언트가 필요합니다.")
        
        llm_input = LlmInput(toc=analysis.toc, file_char_counts=analysis.file_char_counts)
        llm_candidate = await llm_client.suggest_start(llm_input, use_full_toc_analysis=use_full_toc_analysis)

        decision = detector.decide(DecideInput(
            toc=analysis.toc, file_char_counts=analysis.file_char_counts, llm=llm_candidate
        ))
        
        # Log success before returning
        await db_logger.update_log(
            event_id=event_id, 
            status="SUCCESS", 
            end_time=datetime.now(timezone.utc).isoformat()
        )
        
        return {"start_point": decision.model_dump()}

    except Exception as e:
        # Log failure and re-raise
        await db_logger.update_log(
            event_id=event_id, 
            status="FAILURE", 
            end_time=datetime.now(timezone.utc).isoformat(),
            failure_reason=str(e)
        )
        raise e
    finally:
        # Always clean up the decrypted data
        if decrypted_epub:
            del decrypted_epub
            logger.info(f"[{event_id}] 복호화된 EPUB 데이터가 메모리에서 해제되었습니다.")
