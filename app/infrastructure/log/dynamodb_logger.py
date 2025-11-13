# -*- coding: utf-8 -*-
import logging
import aioboto3
from botocore.exceptions import ClientError
from app.domain.models import UndrmLog
from app.domain.interfaces import ILogger
from app.core.exceptions import ExternalServiceError
from typing import Optional

logger = logging.getLogger(__name__)

class DynamoDBLogger(ILogger):
    """
    AWS DynamoDB를 사용하여 감사 로그를 기록하는 로거 구현체입니다.
    테이블/리소스는 lifespan에서 싱글턴으로 관리.
    """
    def __init__(self, table):
        self.table = table
        self.table_name = getattr(table, "name", "<unknown>")
        logger.info(f"DynamoDBLogger 초기화 (테이블: {self.table_name})")

    async def create_log(self, log_data: UndrmLog) -> str:
        item = log_data.model_dump()
        try:
            # 중복 삽입 방지: event_id가 없을 때만 쓰기
            await self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(event_id)",
            )
            logger.info(f"감사 로그 생성 성공 (Event ID: {log_data.event_id})")
            return log_data.event_id
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            # 조건 실패는 멱등성 충족 → 성공으로 간주 가능(원하면 그대로 통과)
            if code == "ConditionalCheckFailedException":
                logger.warning(f"이미 존재하는 로그 (Event ID: {log_data.event_id})")
                return log_data.event_id
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"DynamoDB 로그 생성 실패: {msg}")
            raise ExternalServiceError(f"DynamoDB 로그 생성 실패: {msg}") from e
        except Exception as e:
            logger.exception("DynamoDB 로그 생성 중 예외")
            raise ExternalServiceError(f"DynamoDB 로그 생성 중 예외: {e}") from e

    async def update_log(
        self, event_id: str, status: str, end_time: str, failure_reason: Optional[str] = None
    ):
        update_expression = "SET #status = :status, undrm_end_time = :end_time"
        expr_names = {"#status": "status"}
        expr_values = {":status": status, ":end_time": end_time}
        if failure_reason:
            update_expression += ", failure_reason = :reason"
            expr_values[":reason"] = failure_reason

        try:
            await self.table.update_item(
                Key={"event_id": event_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
            )
            logger.info(f"감사 로그 업데이트 성공 (Event ID: {event_id})")
        except ClientError as e:
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"DynamoDB 로그 업데이트 실패: {msg}")
            raise ExternalServiceError(f"DynamoDB 로그 업데이트 실패: {msg}") from e
        except Exception as e:
            logger.exception("DynamoDB 로그 업데이트 중 예외")
            raise ExternalServiceError(f"DynamoDB 로그 업데이트 중 예외: {e}") from e
