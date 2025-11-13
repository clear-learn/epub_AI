# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timezone

from app.domain.interfaces import ILogger
from app.application.shared.pipeline import UndrmPipeline
from .services import HashtagExtractor

logger = logging.getLogger(__name__)

async def extract_hashtags(
    s3_bucket: str, 
    s3_key: str, 
    tenant_id: str,
    itemId: str,
    pipeline: UndrmPipeline,
    extractor: HashtagExtractor,
    db_logger: ILogger,
) -> dict:
    """
    '해시태그 추출' 유스케이스.
    복호화 파이프라인을 실행하고, EPUB 텍스트를 추출하여 해시태그를 생성합니다.
    """
    pipeline_output = await pipeline.run(
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        tenant_id=tenant_id,
        itemId=itemId,
        reason="extract_hashtags"
    )
    
    event_id = pipeline_output.event_id
    decrypted_epub = None

    try:
        decrypted_epub = pipeline_output.decrypted_epub
        
        hashtags = await extractor.extract_async(decrypted_epub)
        
        await db_logger.update_log(
            event_id=event_id, 
            status="SUCCESS", 
            end_time=datetime.now(timezone.utc).isoformat()
        )
        
        return {"hashtags": hashtags}

    except Exception as e:
        await db_logger.update_log(
            event_id=event_id, 
            status="FAILURE", 
            end_time=datetime.now(timezone.utc).isoformat(),
            failure_reason=str(e)
        )
        raise e
    finally:
        if decrypted_epub:
            del decrypted_epub
            logger.info(f"[{event_id}] 복호화된 EPUB 데이터가 메모리에서 해제되었습니다.")
