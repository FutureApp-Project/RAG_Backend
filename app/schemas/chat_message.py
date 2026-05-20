from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    PDF = "pdf"


# FIX: Update ResponseSource enum to include all possible values from chat service
class ResponseSource(str, Enum):
    # Original values
    VECTOR_DB = "vector_db"
    VECTOR_DB_GENERATED = "vector_db_generated"
    LOCAL_MODEL = "local_model"
    CHATGPT_API = "chatgpt_api"
    VECTOR_DB_REFINED = "vector_db_refined"
    # Additional values from chat service
    VECTOR_DB_DIRECT = "vector_db_direct"
    VECTOR_DB_FALLBACK = "vector_db_fallback"
    VECTOR_FALLBACK = "vector_fallback"
    VECTOR_DB_ENHANCED = "vector_db_enhanced"
    VECTOR_DB_FAST = "vector_db_fast"
    OLLAMA_MISTRAL = "ollama_mistral"
    SAFE_FALLBACK = "safe_fallback"
    FALLBACK = "fallback"
    LOCAL_MODEL_FALLBACK = "local_model_fallback"
    TIMEOUT = "timeout"
    ERROR = "error"
    IMAGE = "image"
    UNKNOWN = "unknown"
    CHATGPT_QUICK = "chatgpt_quick"


class ChatMessageBase(BaseModel):
    content: str = Field(..., min_length=0, max_length=10000)
    message_type: MessageType = Field(default=MessageType.TEXT)
    is_user: bool = Field(default=True)
    original_content: Optional[str] = None
    chat_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatMessageCreate(ChatMessageBase):
    chat_session_id: UUID
    user_id: int
    response_source: Optional[ResponseSource] = None
    should_add_to_vector_db: bool = Field(default=False)


class ChatMessageUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=0, max_length=5000)
    chat_metadata: Optional[Dict[str, Any]] = None


class ChatMessageResponse(ChatMessageBase):
    id: UUID
    chat_session_id: UUID
    user_id: int
    response_source: Optional[ResponseSource]
    should_add_to_vector_db: bool
    timestamp: datetime
    audio_url: Optional[str]
    image_url: Optional[str]

    class Config:
        from_attributes = True
        json_encoders = {UUID: str, datetime: lambda dt: dt.isoformat()}


class ChatMessageWithSession(ChatMessageResponse):
    session_title: str
    session_created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageRequest(BaseModel):
    """Request schema for sending a chat message"""

    type: MessageType = Field(default=MessageType.TEXT)
    content: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    image_type: Optional[str] = Field(
        None, description="Must be 'skin' or 'scalp' for image messages"
    )
    query: Optional[str] = Field(
        None, description="User query to accompany an uploaded file (image or PDF)"
    )

    @validator("image_type")
    def validate_image_type(cls, v, values):
        if values.get("type") == MessageType.IMAGE and v not in ["skin", "scalp"]:
            raise ValueError("image_type must be 'skin' or 'scalp' for image messages")
        return v

    @validator("content")
    def validate_content(cls, v, values):
        message_type = values.get("type")

        if message_type == MessageType.IMAGE:
            # Check if it looks like a base64 image
            if not (
                v.startswith("data:image/") or len(v) > 1000
            ):  # Also accept long strings as potential base64
                raise ValueError("Image content should be in base64 format")
        elif message_type == MessageType.AUDIO:
            # Check if it looks like a base64 audio
            if not (
                v.startswith("data:audio/") or len(v) > 1000
            ):  # Also accept long strings
                raise ValueError(
                    "Audio content should be in base64 format starting with 'data:audio/'"
                )
        elif message_type == MessageType.PDF:
            # Check if it looks like base64 PDF data
            if not (v.startswith("data:application/pdf") or len(v) > 1000):
                raise ValueError("PDF content should be in base64 format")
        return v


class ChatMessageListResponse(BaseModel):
    messages: list[ChatMessageResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class AdminChatMessageResponse(ChatMessageResponse):
    """Extended response for admin with additional details"""

    user_username: str
    user_fullname: str
    vector_db_used: bool = Field(default=False)
    local_model_used: bool = Field(default=False)
    chatgpt_used: bool = Field(default=False)

    @validator(
        "vector_db_used", "local_model_used", "chatgpt_used", pre=True, always=True
    )
    def set_source_flags(cls, v, values):
        """Set source flags based on response_source"""
        response_source = values.get("response_source")
        if response_source in {
            ResponseSource.VECTOR_DB,
            ResponseSource.VECTOR_DB_GENERATED,
            ResponseSource.VECTOR_DB_REFINED,
            ResponseSource.VECTOR_DB_DIRECT,
            ResponseSource.VECTOR_DB_FALLBACK,
            ResponseSource.VECTOR_DB_ENHANCED,
            ResponseSource.VECTOR_DB_FAST,
        }:
            return True
        elif response_source == ResponseSource.LOCAL_MODEL:
            return response_source == ResponseSource.LOCAL_MODEL
        elif response_source == ResponseSource.CHATGPT_API:
            return response_source == ResponseSource.CHATGPT_API
        return v

    class Config:
        from_attributes = True
