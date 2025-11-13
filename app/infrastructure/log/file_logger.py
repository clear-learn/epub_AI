# -*- coding: utf-8 -*-
import logging
import json
import os
from app.domain.models import UndrmLog
from app.domain.interfaces import ILogger

logger = logging.getLogger(__name__)

class FileLogger(ILogger):
    """
    파일 기반 로거의 구현체입니다.
    로그를 프로젝트 루트의 'logs/' 디렉토리에 JSON 파일로 기록합니다.
    """
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        logger.info(f"FileLogger가 '{self.log_dir}' 디렉토리에 로그를 기록합니다.")

    def _get_log_path(self, event_id: str) -> str:
        return os.path.join(self.log_dir, f"{event_id}.json")

    def create_log(self, log_data: UndrmLog) -> str:
        """초기 감사 로그를 JSON 파일로 생성합니다."""
        try:
            log_path = self._get_log_path(log_data.event_id)
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(log_data.model_dump_json(indent=2))
            logger.info(f"--- AUDIT LOG CREATED --- (Event ID: {log_data.event_id})")
            return log_data.event_id
        except IOError as e:
            logger.error(f"파일 로그 생성 실패: {e}")
            return log_data.event_id

    def update_log(self, event_id: str, status: str, end_time: str, failure_reason: str = None):
        """기존 로그 JSON 파일을 읽어 상태를 업데이트합니다."""
        log_path = self._get_log_path(event_id)
        try:
            with open(log_path, 'r+', encoding='utf-8') as f:
                log_data = json.load(f)
                log_data['status'] = status
                log_data['undrm_end_time'] = end_time
                if failure_reason:
                    log_data['failure_reason'] = failure_reason
                
                f.seek(0)
                f.truncate()
                json.dump(log_data, f, indent=2)
            logger.info(f"--- AUDIT LOG UPDATED --- (Event ID: {event_id})")
        except FileNotFoundError:
            logger.error(f"업데이트할 로그 파일을 찾을 수 없습니다: {log_path}")
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"파일 로그 업데이트 실패: {e}")
