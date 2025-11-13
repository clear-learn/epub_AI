# -*- coding: utf-8 -*-
"""
도메인 계층의 비즈니스 규칙 위반과 관련된 예외를 정의합니다.
"""

class BusinessRuleValidationError(ValueError):
    """도메인 비즈니스 규칙 위반에 대한 기본 예외 클래스입니다."""
    pass

class MissingTocError(BusinessRuleValidationError):
    """EPUB 파일에 목차(TOC)가 존재하지 않을 때 발생하는 예외입니다."""
    pass