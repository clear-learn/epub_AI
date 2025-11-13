# -*- coding: utf-8 -*-
"""
애플리케이션 전체에서 공유될 클라이언트 인스턴스를 저장하는 중앙 저장소입니다.
lifespan 이벤트를 통해 앱 시작 시 여기에 클라이언트가 채워집니다.
"""
from typing import Dict, Any

# 싱글턴 클라이언트 인스턴스를 보관할 딕셔너리
clients: Dict[str, Any] = {}
