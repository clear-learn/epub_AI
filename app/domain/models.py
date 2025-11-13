# -*- coding: utf-8 -*-
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Annotated, Optional
from pydantic import BaseModel, Field, StringConstraints

Digits = Annotated[str, StringConstraints(pattern=r'^\d+$')]

# --- API DTOs ---
class InspectRequest(BaseModel):
    s3_bucket: str
    s3_key: str
    itemId: Digits
    purpose: str
    tenant_id: str = "default"
    use_full_toc_analysis: bool = True

class InspectResponse(BaseModel):
    """API가 성공적으로 처리되었을 때 반환하는 응답 본문(Response Body) 구조입니다."""
    source: dict
    start: Optional[dict] = None
    # hashtags: Optional[List[str]] = None
    processing: dict

class UndrmPipelineOutput(BaseModel):
    """복호화 파이프라인의 결과를 담는 DTO입니다."""
    decrypted_epub: bytes
    event_id: str

# --- Domain DTOs ---
class UndrmInput(BaseModel):
    encrypted_epub: bytes
    license_key: str
    grant_id: Optional[str] = None
    tenant_id: str

class UndrmOutput(BaseModel):
    decrypted_epub: bytes
    drm_type: Optional[Literal["V2"]] = "V2"

class FileCharStat(BaseModel):
    path: str
    chars: int
    has_text: bool

class TocItem(BaseModel):
    title: str
    href: str
    level: int

class AnalyzeOutput(BaseModel):
    file_char_counts: List[FileCharStat]
    toc: List[TocItem]
    hints: Optional[dict] = Field(default_factory=dict)
    meta: Optional[dict] = Field(default_factory=dict)

class LlmStartCandidate(BaseModel):
    file: str
    anchor: Optional[str] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None

class LlmInput(BaseModel):
    toc: List[TocItem]
    file_char_counts: List[FileCharStat]

class DecideInput(BaseModel):
    toc: List[TocItem]
    file_char_counts: List[FileCharStat]
    llm: Optional[LlmStartCandidate] = None
    hints: Optional[dict] = Field(default_factory=dict)

class DecideOutput(BaseModel):
    start_file: str
    anchor: Optional[str] = None
    confidence: float
    rationale: Optional[str] = None

# --- Logging DTO ---
class UndrmLog(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    itemId: Digits
    user_context: Optional[dict] = None
    s3_bucket: str
    s3_key: str
    grant_id: str
    action: Literal["UNDRM"] = "UNDRM"
    reason: str
    status: Literal["SUCCESS", "FAILURE", "PROCESSING"]
    failure_reason: Optional[str] = None
    drm_type: Literal["V2"] = "V2"
    undrm_start_time: str
    undrm_end_time: Optional[str] = None
    event_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
