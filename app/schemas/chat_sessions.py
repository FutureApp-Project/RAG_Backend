from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from app.schemas.chat_message import ChatMessageResponse


class ChatSessionBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    user_id: int


class ChatSessionCreate(ChatSessionBase):
    """Schema for creating a new chat session"""

    session_date: date = Field(default_factory=date.today)

    @validator("title")
    def validate_title(cls, v):
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()


class ChatSessionUpdate(BaseModel):
    """Schema for updating a chat session"""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    message_count: Optional[int] = Field(None, ge=0)


class ChatSessionResponse(ChatSessionBase):
    """Response schema for chat session"""
    id: UUID
    # created_at: datetime
    # updated_at: datetime
    # session_date: date
    # message_count: int = Field(default=0)
    # messages: List[ChatMessageResponse] = Field(default_factory=list)
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    session_date: date
    message_count: int
    messages: List[ChatMessageResponse] = [] 

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda dt: dt.isoformat(),
            date: lambda d: d.isoformat()
        }


class ChatSessionResponses(BaseModel):
    id: str
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    session_date: date
    message_count: int
    messages: List[ChatMessageResponse] = Field(default_factory=list)  # Add this

    class Config:
        from_attributes = True


class ChatSessionWithMessages(ChatSessionResponse):
    """Chat session with its messages"""

    messages: List[ChatMessageResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class DailySessionResponse(BaseModel):
    """Response for daily session check"""

    session_exists: bool
    session: Optional[ChatSessionResponse] = None
    message_count: int = Field(default=0)
    can_send_message: bool = Field(default=True)

    @validator("can_send_message", always=True)
    def set_can_send_message(cls, v, values):
        """Set if user can send message (for rate limiting or other rules)"""
        # Add your business logic here
        # Example: Check if message count is under daily limit
        message_count = values.get("message_count", 0)
        return message_count < 100  # Example limit


class ChatSessionListResponse(BaseModel):
    sessions: List[ChatSessionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class UserSessionStats(BaseModel):
    """Statistics for user's chat sessions"""

    user_id: int
    total_sessions: int
    total_messages: int
    first_session_date: Optional[datetime]
    last_session_date: Optional[datetime]
    avg_messages_per_session: float = Field(default=0.0)

    @validator("avg_messages_per_session", always=True)
    def calculate_avg(cls, v, values):
        total_sessions = values.get("total_sessions", 0)
        total_messages = values.get("total_messages", 0)

        if total_sessions > 0:
            return round(total_messages / total_sessions, 2)
        return 0.0


class SessionCreateRequest(BaseModel):
    """Request for creating a new session"""

    title: Optional[str] = Field(None, description="Optional session title")

    @validator("title", always=True)
    def set_default_title(cls, v):
        if not v:
            return f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return v
