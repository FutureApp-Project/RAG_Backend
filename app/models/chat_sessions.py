# models/chat_sessions.py
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from datetime import datetime, date
from .base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # NEW: Date column to enforce one entry per day
    session_date = Column(Date, default=date.today, nullable=False, index=True)
    
    # NEW: Track last activity
    message_count = Column(Integer, default=0)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage", back_populates="chat_session", cascade="all, delete-orphan"
    )
    
    # Composite unique constraint for one session per user per day
    __table_args__ = (
        UniqueConstraint('user_id', 'session_date', name='unique_user_session_per_day'),
    )