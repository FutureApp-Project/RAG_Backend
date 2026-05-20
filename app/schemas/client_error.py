from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ClientErrorReport(BaseModel):
    app: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    fingerprint: Optional[str] = Field(default=None, max_length=128)
    stack: Optional[str] = Field(default=None, max_length=16000)
    url: Optional[str] = Field(default=None, max_length=2000)
    route: Optional[str] = Field(default=None, max_length=512)
    userAgent: Optional[str] = Field(default=None, max_length=1024)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ClientErrorRecordResponse(BaseModel):
    id: int
    app: str
    source: str
    message: str
    fingerprint: str
    stack: Optional[str] = None
    url: Optional[str] = None
    route: Optional[str] = None
    userAgent: Optional[str] = None
    clientIp: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    deduplicated: bool
    createdAt: datetime


class ClientErrorListResponse(BaseModel):
    items: List[ClientErrorRecordResponse]
    total: int
    limit: int
    offset: int
