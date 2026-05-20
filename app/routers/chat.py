# app/routers/chat.py
from fastapi import APIRouter, Query, Request, HTTPException, Depends, Security, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config.database.database import get_db, AsyncSessionLocal
from app.models.chat_sessions import ChatSession
from app.schemas.chat_sessions import (
    ChatSessionResponse,
    DailySessionResponse,
    SessionCreateRequest,
)
from app.models.user import User
from app.models.chat_message import ChatMessage
from app.routers.user import get_current_user
import jwt
from typing import Optional, Dict, Any, List
import uuid
from app.config.helper.jwt_helper import verify_tokens
from datetime import datetime, date


# Helper to parse datetime/date fields robustly
def parse_datetime(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return datetime.fromisoformat(dt)
    return dt


def parse_date(d):
    if d is None:
        return None
    if isinstance(d, str):
        return date.fromisoformat(d)
    return d


from app.config.log.log_config import get_logger
from app.services.chat_service import ChatService
from app.schemas.token import TokenData
from app.schemas.chat_message import (
    ChatMessageRequest,
    MessageType,
    ChatMessageResponse,
)
from app.services.image_service import ImageService
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger("chat_router")
chat_service = ChatService()
security = HTTPBearer()
logger.info("Chat router initialized")


def is_user_admin(user_data: TokenData) -> bool:
    """Check if user is admin"""
    if hasattr(user_data, "role") and user_data.role == "admin":
        return True
    if hasattr(user_data, "is_admin") and user_data.is_admin:
        return True
    return False


@router.get("/sessions", response_model=List[ChatSessionResponse])
async def get_user_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_data: TokenData = Depends(verify_tokens),
):
    """Get all chat sessions for the authenticated user with pagination"""
    try:
        route = router.prefix + "/sessions"

        # Check if user is properly authenticated
        if not user_data.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        async with AsyncSessionLocal() as db_session:
            # Get total count
            count_result = await db_session.execute(
                select(func.count(ChatSession.id)).where(
                    ChatSession.user_id == user_data.user_id
                )
            )
            total = count_result.scalar() or 0

            # Get paginated sessions
            offset = (page - 1) * page_size
            result = await db_session.execute(
                select(ChatSession)
                .where(ChatSession.user_id == user_data.user_id)
                .order_by(ChatSession.updated_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            sessions = result.scalars().all()

            session_responses = []
            for session in sessions:
                # Count messages for this session
                message_count_result = await db_session.execute(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.chat_session_id == session.id
                    )
                )
                message_count = message_count_result.scalar() or 0

                # Get last 5 messages for preview (for performance)
                messages_result = await db_session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.chat_session_id == session.id)
                    .order_by(ChatMessage.timestamp.desc())
                    .limit(5)
                )
                messages = messages_result.scalars().all()
                # Reverse to get chronological order
                messages = list(reversed(messages))

                # Create message responses
                message_responses = []
                for msg in messages:
                    message_responses.append(
                        ChatMessageResponse(
                            id=str(msg.id),
                            chat_session_id=str(msg.chat_session_id),
                            user_id=msg.user_id,
                            message_type=msg.message_type,
                            content=msg.content,
                            is_user=msg.is_user,
                            timestamp=(
                                msg.timestamp.isoformat() if msg.timestamp else None
                            ),
                            response_source=getattr(msg, "response_source", None),
                            should_add_to_vector_db=False,
                            audio_url=getattr(msg, "audio_url", None),
                            image_url=getattr(msg, "image_url", None),
                        )
                    )

                session_responses.append(
                    ChatSessionResponse(
                        id=str(session.id),
                        user_id=session.user_id,
                        title=session.title or "Unbenanntes Gespräch",
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                        session_date=session.session_date,
                        message_count=message_count,
                        messages=message_responses,
                    )
                )

            return session_responses

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting user sessions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat sessions",
        )


@router.get("/sessions/today", response_model=List[ChatSessionResponse])
async def get_today_sessions(
    request: Request,
    user_data: TokenData = Depends(verify_tokens),
):
    """Get today's chat session for the user"""
    try:
        route = router.prefix + "/sessions/today"
        logger.info(f"=== GET TODAY SESSIONS START ===")
        logger.info(f"User ID: {user_data.user_id}")

        # Check authentication
        if not user_data.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        async with AsyncSessionLocal() as db_session:
            today_date = date.today()
            logger.info(f"Looking for session with date: {today_date}")

            # Get today's session
            result = await db_session.execute(
                select(ChatSession).where(
                    ChatSession.user_id == user_data.user_id,
                    ChatSession.session_date == today_date,
                )
            )
            today_session = result.scalar_one_or_none()

            logger.info(f"Session found: {today_session is not None}")

            if today_session:
                logger.info(
                    f"Found session: ID={today_session.id}, Date={today_session.session_date}"
                )

                # Get messages for this session
                messages_result = await db_session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.chat_session_id == today_session.id)
                    .order_by(ChatMessage.timestamp)
                )
                messages = messages_result.scalars().all()

                logger.info(f"Found {len(messages)} messages in database")

                # Create message responses
                message_responses = []
                for msg in messages:
                    try:
                        message_responses.append(
                            ChatMessageResponse(
                                id=str(msg.id),
                                chat_session_id=str(msg.chat_session_id),
                                user_id=msg.user_id,
                                message_type=msg.message_type or "text",
                                content=msg.content or "",
                                is_user=(
                                    msg.is_user if msg.is_user is not None else True
                                ),
                                timestamp=(
                                    msg.timestamp.isoformat()
                                    if msg.timestamp
                                    else datetime.utcnow().isoformat()
                                ),
                                response_source=getattr(msg, "response_source", None),
                                should_add_to_vector_db=False,
                                audio_url=getattr(msg, "audio_url", None),
                                image_url=getattr(msg, "image_url", None),
                            )
                        )
                    except Exception as msg_error:
                        logger.error(
                            f"Error creating message response: {str(msg_error)}"
                        )

                # Create the session response
                session_response = ChatSessionResponse(
                    id=str(today_session.id),
                    user_id=today_session.user_id,
                    title=today_session.title or "Heutiges Gespräch",
                    created_at=today_session.created_at or datetime.utcnow(),
                    updated_at=today_session.updated_at or datetime.utcnow(),
                    session_date=today_session.session_date or today_date,
                    message_count=len(message_responses),
                    messages=message_responses,
                )

                logger.info(f"Returning session with {len(message_responses)} messages")
                return [session_response]

            else:
                logger.info(f"No session found for today for user {user_data.user_id}")
                return []

    except Exception as e:
        logger.error(f"Error in get_today_sessions: {str(e)}", exc_info=True)
        return []


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session_by_id(
    request: Request,
    session_id: str,
    user_data: TokenData = Depends(verify_tokens),
):
    """Get a specific chat session by ID - Admins can view any session, users can only view their own"""
    try:
        logger.info(f"=== GET SESSION BY ID START ===")
        logger.info(f"Route: /chat/sessions/{session_id}")
        logger.info(f"User ID: {user_data.user_id}")

        # Check if user is admin
        is_admin = is_user_admin(user_data)

        # Check if user is properly authenticated
        if not user_data.user_id:
            logger.error("User not properly authenticated - missing user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        # Validate session_id
        try:
            session_uuid = uuid.UUID(session_id)
            logger.info(f"Valid UUID: {session_uuid}")
        except ValueError as e:
            logger.error(f"Invalid UUID format: {session_id}, Error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session ID format",
            )

        # IMPORTANT: For admins, we need to pass the session owner's user_id, not the admin's user_id
        # First, get the session to find out who it belongs to
        async with AsyncSessionLocal() as db_session:
            # Get session owner
            owner_result = await db_session.execute(
                select(ChatSession.user_id).where(ChatSession.id == session_uuid)
            )
            session_owner_id = owner_result.scalar_one_or_none()

            if not session_owner_id:
                logger.warning(f"Session {session_id} not found in database")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found",
                )

            logger.info(f"Session owner ID: {session_owner_id}")

            # Check access rights
            if not is_admin and session_owner_id != user_data.user_id:
                logger.warning(
                    f"User {user_data.user_id} attempted unauthorized access to session {session_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to access this session",
                )
            # Now get the history with the appropriate parameters
            history = await chat_service.get_chat_history(
                user_id=session_owner_id,  # Always pass the session owner's ID
                session_id=session_uuid,
                is_admin=is_admin,  # Pass admin flag
            )

            logger.info(f"Got {len(history)} session(s) from chat service")

            if not history or len(history) == 0:
                logger.warning(f"Session {session_id} not found")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found",
                )

            # Get the first (and only) session from the list
            session_data = history[0]

            # Convert to ChatSessionResponse format
            session_response = ChatSessionResponse(
                id=session_data["id"],
                user_id=session_data["user_id"],
                title=session_data["title"],
                created_at=parse_datetime(session_data["created_at"]),
                updated_at=parse_datetime(session_data["updated_at"]),
                session_date=parse_date(session_data["session_date"]),
                message_count=session_data["message_count"],
                messages=[
                    ChatMessageResponse(
                        id=msg["id"],
                        chat_session_id=msg["chat_session_id"],
                        user_id=msg["user_id"],
                        message_type=msg["message_type"],
                        content=msg["content"],
                        is_user=msg["is_user"],
                        timestamp=msg["timestamp"],
                        response_source=msg.get("response_source"),
                        should_add_to_vector_db=False,
                        audio_url=msg.get("audio_url"),
                        image_url=msg.get("image_url"),
                    )
                    for msg in session_data["messages"]
                ],
            )

            logger.info(
                f"✅ Successfully returning session {session_id} with {len(session_data['messages'])} messages"
            )
            return session_response

    except HTTPException as he:
        logger.error(f"HTTPException in get_session_by_id: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"ERROR in get_session_by_id: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat session",
        )


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    request: Request,
    session_data: SessionCreateRequest,
    user_data: TokenData = Depends(verify_tokens),
):
    """Create a new chat session for the user"""
    try:
        route = router.prefix + "/sessions"

        # Check if user is properly authenticated
        if not user_data.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        # This will create or get today's session
        session = await chat_service._get_or_create_daily_session(
            user_id=user_data.user_id, session_id=None
        )

        # Update session title if provided and different from current title
        if session_data.title and session_data.title != session.title:
            async with AsyncSessionLocal() as update_session:
                try:
                    await update_session.execute(
                        update(ChatSession)
                        .where(ChatSession.id == session.id)
                        .values(title=session_data.title, updated_at=datetime.utcnow())
                    )
                    await update_session.commit()
                    session.title = session_data.title
                except Exception as e:
                    await update_session.rollback()
                    raise e

        return ChatSessionResponse(
            id=str(session.id),
            user_id=session.user_id,
            title=session.title or "Unbenanntes Gespräch",
            created_at=session.created_at,
            updated_at=session.updated_at,
            session_date=session.session_date,
            message_count=session.message_count or 0,
            messages=[],
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error creating chat session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chat session",
        )


@router.get("/sessions/check-today", response_model=DailySessionResponse)
async def check_today_session(
    request: Request, user_data: TokenData = Depends(verify_tokens)
):
    """Check if user has a session for today"""
    try:
        route = router.prefix + "/sessions/check-today"
        logger.info(f"Route: {route} | User ID: {user_data.user_id}")

        # Check if user is properly authenticated
        if not user_data or not user_data.user_id:
            logger.error(f"No user data or user_id: {user_data}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        async with AsyncSessionLocal() as db_session:
            today_date = date.today()
            logger.info(
                f"Checking for session for user {user_data.user_id} on date {today_date}"
            )

            # Check for today's session
            result = await db_session.execute(
                select(ChatSession).where(
                    ChatSession.user_id == user_data.user_id,
                    ChatSession.session_date == today_date,
                )
            )
            existing_session = result.scalar_one_or_none()

            logger.info(f"Session found: {existing_session is not None}")

            if existing_session:
                # Count messages in this session
                count_result = await db_session.execute(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.chat_session_id == existing_session.id
                    )
                )
                message_count = count_result.scalar() or 0

                session_data = {
                    "id": str(existing_session.id),
                    "user_id": existing_session.user_id,
                    "title": existing_session.title,
                    "created_at": (
                        existing_session.created_at.isoformat()
                        if existing_session.created_at
                        else None
                    ),
                    "updated_at": (
                        existing_session.updated_at.isoformat()
                        if existing_session.updated_at
                        else None
                    ),
                    "session_date": (
                        existing_session.session_date.isoformat()
                        if existing_session.session_date
                        else None
                    ),
                    "message_count": message_count,
                }

                return DailySessionResponse(
                    session_exists=True,
                    session=session_data,
                    message_count=message_count,
                    can_send_message=message_count < 100,
                )
            else:
                return DailySessionResponse(
                    session_exists=False,
                    session=None,
                    message_count=0,
                    can_send_message=True,
                )

    except Exception as e:
        logger.error(f"Error checking today's session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check session",
        )


@router.post("/message", response_model=Dict[str, Any])
@limiter.limit("30/minute")
async def send_message(
    request: Request,
    message_data: ChatMessageRequest,
    user_data: TokenData = Depends(verify_tokens),
):
    """
    Send message (text/audio/image) with medical image analysis.
    """
    try:
        route = router.prefix + "/message"
        logger.info(
            f"Route: {route} | User ID: {user_data.user_id} | Username: {user_data.username} | Type: {message_data.type}"
        )

        # Ensure user is properly authenticated
        if not user_data.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        # Convert session_id string to UUID if provided
        session_uuid = None
        if message_data.session_id:
            try:
                session_uuid = uuid.UUID(message_data.session_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid session ID format. Must be a valid UUID.",
                )

        # Validate image_type for image messages
        image_type = None
        if message_data.type == MessageType.IMAGE:
            if not message_data.image_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="image_type is required for image messages",
                )
            image_type = message_data.image_type

        # Process message with the chat service
        result = await chat_service.process_message(
            user_id=user_data.user_id,
            message_type=message_data.type.value,
            content=message_data.content,
            session_id=session_uuid,
            image_type=image_type,
            query=message_data.query,
        )

        return result

    except HTTPException as he:
        logger.error(f"HTTP error in send_message: {he.detail}")
        raise he
    except ValueError as ve:
        logger.error(f"Validation error in send_message: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request data: {str(ve)}",
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in send_message endpoint: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get("/history")
async def get_chat_history(
    request: Request,
    session_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user_data: TokenData = Depends(verify_tokens),
):
    """Get chat history for user with pagination"""
    try:
        route = router.prefix + "/history"

        # Check authentication
        if not user_data.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        # Check if user is admin
        is_admin = is_user_admin(user_data)

        # Convert session_id string to UUID if provided
        session_uuid = None
        if session_id:
            try:
                session_uuid = uuid.UUID(session_id)
            except ValueError:
                logger.warning(f"Invalid session_id format: {session_id}")
                session_uuid = None

        # Get chat history
        history = await chat_service.get_chat_history(
            user_id=user_data.user_id, session_id=session_uuid, is_admin=is_admin
        )

        # Apply pagination
        if session_uuid:
            # Single session history
            if history and len(history) > 0:
                session_data = history[0]
                messages = session_data.get("messages", [])

                total = len(messages)

                # Paginate messages
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                paginated_messages = messages[start_idx:end_idx]

                session_data["messages"] = paginated_messages

                return {
                    "status": "success",
                    "user_id": user_data.user_id,
                    "session": session_data,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "has_next": end_idx < total,
                    },
                }
            else:
                return {
                    "status": "success",
                    "user_id": user_data.user_id,
                    "session": None,
                    "message": "No chat history found",
                }
        else:
            # All sessions
            total = len(history)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_sessions = history[start_idx:end_idx]

            return {
                "status": "success",
                "user_id": user_data.user_id,
                "sessions": paginated_sessions,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "has_next": end_idx < total,
                },
            }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in get_chat_history endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/GetChatById/{user_id}")
async def get_chat_By_userId_path(
    request: Request,
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user_data: TokenData = Depends(verify_tokens),
):
    """Get chat history for user with pagination - Admins can view any user, users can only view themselves"""
    try:
        logger.info(
            f"GetChatById endpoint called with userId: {user_id}, page: {page}, page_size: {page_size}"
        )
        logger.info(f"Current user ID: {user_data.user_id}")

        # Check authentication
        if not user_data.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not properly authenticated",
            )

        # Check if user is admin
        # is_admin = is_user_admin(user_data)
        # logger.info(f"Is admin: {is_admin}")

        # If not admin, they can only view their own chats
        # if not is_admin and user_data.user_id != user_id:
        #     logger.warning(f"Non-admin user {user_data.user_id} attempted to view chats of user {user_id}")
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail="You don't have permission to view other users' chats",
        #     )

        # Get chat history
        history_result = await chat_service.get_chat_By_userId(
            user_id=user_id, page=page, page_size=page_size
        )

        # Handle both dict and list return types
        if isinstance(history_result, dict):
            sessions = history_result.get("sessions", [])
            total = history_result.get("total", 0)
            current_page = history_result.get("page", page)
            current_page_size = history_result.get("page_size", page_size)

            logger.info(
                f"Returning {len(sessions)} sessions for user_id {user_id} with total {total}"
            )
            return {
                "status": "success",
                "user_id": user_data.user_id,
                "target_user_id": user_id,
                "sessions": sessions,
                "pagination": {
                    "page": current_page,
                    "page_size": current_page_size,
                    "total": total,
                    "has_next": (current_page * current_page_size) < total,
                },
            }
        else:
            total = len(history_result)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_sessions = history_result[start_idx:end_idx]

            logger.info(
                f"Returning {len(paginated_sessions)} sessions for user_id {user_id} with total {total}"
            )
            return {
                "status": "success",
                "user_id": user_data.user_id,
                "target_user_id": user_id,
                "sessions": paginated_sessions,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "has_next": end_idx < total,
                },
            }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in get_chat_history endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# Debug endpoint to check session ownership
@router.get("/debug/session/{session_id}")
async def debug_session(
    session_id: str,
    user_data: TokenData = Depends(verify_tokens),
):
    """Debug endpoint to check session details with role information"""
    try:
        session_uuid = uuid.UUID(session_id)

        # Check if user is admin
        is_admin = is_user_admin(user_data)

        async with AsyncSessionLocal() as db_session:
            # Get session with owner info
            result = await db_session.execute(
                select(ChatSession).where(ChatSession.id == session_uuid)
            )
            session = result.scalar_one_or_none()

            if session:
                # Check if it belongs to the current user
                belongs_to_user = session.user_id == user_data.user_id
                can_access = belongs_to_user or is_admin

                # Get message count
                count_result = await db_session.execute(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.chat_session_id == session_uuid
                    )
                )
                message_count = count_result.scalar() or 0

                # Get first few messages for preview
                messages_result = await db_session.execute(
                    select(
                        ChatMessage.content, ChatMessage.is_user, ChatMessage.timestamp
                    )
                    .where(ChatMessage.chat_session_id == session_uuid)
                    .order_by(ChatMessage.timestamp)
                    .limit(3)
                )
                preview_messages = messages_result.all()

                return {
                    "exists": True,
                    "session_id": str(session.id),
                    "session_owner_id": session.user_id,
                    "current_user_id": user_data.user_id,
                    "current_user_role": getattr(user_data, "role", "unknown"),
                    "is_admin": is_admin,
                    "belongs_to_user": belongs_to_user,
                    "can_access": can_access,
                    "title": session.title,
                    "message_count": message_count,
                    "created_at": (
                        session.created_at.isoformat() if session.created_at else None
                    ),
                    "updated_at": (
                        session.updated_at.isoformat() if session.updated_at else None
                    ),
                    "session_date": (
                        session.session_date.isoformat()
                        if session.session_date
                        else None
                    ),
                    "preview_messages": [
                        {
                            "content": (
                                msg[0][:50] + "..." if len(msg[0]) > 50 else msg[0]
                            ),
                            "is_user": msg[1],
                            "timestamp": msg[2].isoformat() if msg[2] else None,
                        }
                        for msg in preview_messages
                    ],
                    "access_message": (
                        "✅ ACCESS GRANTED"
                        if can_access
                        else "❌ ACCESS DENIED - Not owner and not admin"
                    ),
                }
            else:
                return {
                    "exists": False,
                    "session_id": session_id,
                    "current_user_id": user_data.user_id,
                    "current_user_role": getattr(user_data, "role", "unknown"),
                    "is_admin": is_admin,
                }
    except ValueError:
        return {"error": "Invalid UUID format"}
    except Exception as e:
        logger.error(f"Debug endpoint error: {str(e)}", exc_info=True)
        return {"error": str(e)}
