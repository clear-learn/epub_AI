# -*- coding: utf-8 -*-
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_database():
    """
    테스트용 데이터베이스 테이블을 생성하고 초기 데이터를 삽입합니다.
    """
    load_dotenv()
    db_connection_string = os.getenv("DB_CONNECTION_STRING")
    if not db_connection_string:
        logger.error("DB_CONNECTION_STRING이 .env 파일에 설정되지 않았습니다.")
        return

    try:
        # 데이터베이스 이름을 제외한 연결 정보 추출
        from sqlalchemy.engine.url import make_url
        url = make_url(db_connection_string)
        db_name = url.database
        url_without_db = url._replace(database=None)
        
        engine_without_db = create_engine(url_without_db)

        with engine_without_db.connect() as connection:
            logger.info("데이터베이스 서버에 성공적으로 연결되었습니다.")
            
            # 1. 데이터베이스 생성 (존재하지 않을 경우)
            connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))
            connection.commit()
            logger.info(f"데이터베이스 '{db_name}'이(가) 준비되었습니다.")

        # 데이터베이스가 포함된 원래 연결 문자열로 엔진 재생성
        engine = create_engine(db_connection_string)
        with engine.connect() as connection:
            # 2. 테이블 생성 (존재하지 않을 경우)
            create_table_query = text("""
            CREATE TABLE IF NOT EXISTS `ai-epub-api-test` (
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `itemId` VARCHAR(255) NOT NULL UNIQUE,
                `gkey` TEXT NOT NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            connection.execute(create_table_query)
            connection.commit()
            logger.info("`ai-epub-api-test` 테이블이 성공적으로 생성되었습니다.")

            # 3. 샘플 데이터 삽입 (중복 방지)
            item_id = "1234567890"
            license_key = "7JU0Sq/GabYj1ebnrwAE0yAA130UbeMN4KoWrjgB3XQ="
            # item_id = "312392359"
            # license_key = "YrFzzaODMptznN0fczs2YJsG77AW8o5X3ZzYfV5OtlY="
            # item_id = "42961314"
            # license_key = "JGefA4S0IBq8x+v/6SbyN2YtgsGbB7VLsziitmKQ4f4="
            
            # 기존 데이터 확인
            check_query = text("SELECT COUNT(*) FROM `ai-epub-api-test` WHERE itemId = :itemId")
            result = connection.execute(check_query, {"itemId": item_id}).scalar()

            if result == 0:
                insert_query = text("""
                INSERT INTO `ai-epub-api-test` (itemId, gkey) VALUES (:itemId, :gkey)
                """)
                connection.execute(insert_query, {"itemId": item_id, "gkey": license_key})
                connection.commit()
                logger.info("샘플 라이선스 키 데이터가 성공적으로 삽입되었습니다.")
            else:
                logger.info("샘플 데이터가 이미 존재합니다. 삽입을 건너뜁니다.")

    except Exception as e:
        logger.error(f"데이터베이스 설정 중 오류 발생: {e}")

if __name__ == "__main__":
    setup_database()
