# app/schemas/__init__.py
# Import base schemas first
from .user import UserCreate, UserUpdate, UserResponse, UserLogin
from .role import RoleCreate, RoleUpdate, RoleResponse
from .menu import MenuItemCreate, MenuItemUpdate, MenuItemResponse

# Import token schemas
from .token import Token, TokenData, TokenPayload

# Import chat schemas - order matters due to circular dependencies
# Import the base classes first
from .chat_message import (
    ChatMessageBase,
    ChatMessageCreate,
    ChatMessageUpdate,
    ChatMessageResponse,
    ChatMessageWithSession,
    ChatMessageListResponse,
    AdminChatMessageResponse,
    MessageType,
    ResponseSource,
    ChatMessageRequest  # ADD THIS - it's used in chat router
)

from .chat_sessions import (
    ChatSessionBase,
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionResponse,
    ChatSessionWithMessages,  # CHANGED: Remove "Response" from the name
    ChatSessionListResponse,
    DailySessionResponse,  # ADD THIS
    UserSessionStats,  # ADD THIS
    SessionCreateRequest,  # ADD THIS
    # Remove schemas that don't exist in your file:
    # ChatSessionStatsResponse,  # This doesn't exist in your file
    # ChatSessionQuery,  # This doesn't exist in your file
    # ChatSessionBulkDelete,  # This doesn't exist in your file
    # ChatSessionExportRequest,  # This doesn't exist in your file
    # ChatSessionExportResponse,  # This doesn't exist in your file
    # ChatSessionSummaryResponse,  # This doesn't exist in your file
    # ChatSessionCreateResponse,  # This doesn't exist in your file
    # ChatSessionDeleteResponse,  # This doesn't exist in your file
)


__all__ = [
    # User schemas
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserLogin",
    # Role schemas
    "RoleCreate",
    "RoleUpdate",
    "RoleResponse",
    # Menu schemas
    "MenuItemCreate",
    "MenuItemUpdate",
    "MenuItemResponse",
    # Token schemas
    "Token",
    "TokenData",
    "TokenPayload",
    # Chat message schemas
    "MessageType",
    "ResponseSource",
    "ChatMessageBase",
    "ChatMessageCreate",
    "ChatMessageUpdate",
    "ChatMessageResponse",
    "ChatMessageWithSession",
    "ChatMessageListResponse",
    "AdminChatMessageResponse",
    "ChatMessageRequest",  # ADD THIS
    # Chat session schemas
    "ChatSessionBase",
    "ChatSessionCreate",
    "ChatSessionUpdate",
    "ChatSessionResponse",
    "ChatSessionWithMessages",  # CHANGED: Remove "Response" from the name
    "ChatSessionListResponse",
    "DailySessionResponse",  # ADD THIS
    "UserSessionStats",  # ADD THIS
    "SessionCreateRequest",  # ADD THIS
]