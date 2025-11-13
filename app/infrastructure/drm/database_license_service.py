# database_license_service.py (수정)
import logging
from typing import Optional
from sqlalchemy import text, bindparam
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces import ILicenseService
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

class DatabaseLicenseService(ILicenseService):
    def __init__(self, session_factory, table_name: str):
        """
        Args:
          session_factory: lifespan에서 만든 sessionmaker(AsyncSessionLocal)
          table_name: 라이선스 테이블명 (화이트리스트/검증 권장)
        """
        if not session_factory:
            raise ValueError("Async session factory가 필요합니다.")
        if not table_name:
            raise ValueError("데이터베이스 테이블 이름이 필요합니다.")

        self.Session = session_factory
        self.table_name = table_name

        # 미리 컴파일할 쿼리(바인딩 사용)
        # 테이블명은 식별자라 바인딩이 불가 → 화이트리스트 검증 권장
        self._stmt = text(f"SELECT gkey FROM `{self.table_name}` WHERE itemId = :item_id").bindparams(
            bindparam("item_id")
        )
        logger.info("DatabaseLicenseService 초기화 완료")

    async def get_license(self, item_id: str) -> Optional[str]:
        logger.info(f"[DB] '{self.table_name}'에서 item_id={item_id} 조회")
        async with self.Session() as session:  # 요청 단위 세션
            try:
                result = await session.execute(self._stmt, {"item_id": item_id})
                return result.scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.error(f"DB 조회 오류 (item_id={item_id}): {e}")
                raise ExternalServiceError(f"데이터베이스 오류: {e}") from e
