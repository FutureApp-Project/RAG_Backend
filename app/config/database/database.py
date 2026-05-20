# app/config/database/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator
from app.models.base import Base
from app.models.role import Role
from app.models.user import User
from app.models.chat_message import ChatMessage
from app.models.chat_sessions import ChatSession
from app.models.client_error_report import ClientErrorReportRecord
from app.models.menu import MenuItem
from app.models.menu_role import menu_role
from app.config.helper.password_helper import password_helper
import os
from app.config.log.log_config import get_logger
from dotenv import load_dotenv

logger = get_logger("database")
load_dotenv()

BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_BOT_PASSWORD = os.getenv("BOOTSTRAP_BOT_PASSWORD", "")

# Database URL configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables")

# Create asynchronous engine and sessionmaker
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

# Create session factory - THIS IS IMPORTANT!
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# This function creates a new session when called
async def get_async_session() -> AsyncSession:
    return AsyncSessionLocal()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create default roles if they don't exist
    session = AsyncSessionLocal()
    try:
        default_roles = ["admin", "doctor", "patient", "bot"]
        for role_name in default_roles:
            # Check if role exists
            from sqlalchemy import select

            result = await session.execute(select(Role).filter(Role.role == role_name))
            existing_role = result.scalar_one_or_none()

            if not existing_role:
                db_role = Role(role=role_name)
                session.add(db_role)

        # Create default admin menu items
        from sqlalchemy import select

        if not (await session.execute(select(MenuItem))).scalars().first():
            default_menu_items = [
                {
                    "text": "Dashboard",
                    "route": "/dashboard",
                    "icon": "bx:bx-show",
                    "item_order": 0,
                },
                {
                    "text": "Benutzer",
                    "route": "/users",
                    "icon": "bx:bxs-user",
                    "item_order": 1,
                },
                {
                    "text": "Chat History",
                    "route": "/chat-history",
                    "icon": "chat",
                    "item_order": 2,
                },
                {
                    "text": "Menü",
                    "route": "/menu",
                    "icon": "ic:twotone-menu-book",
                    "item_order": 3,
                },
                {
                    "text": "Rolle",
                    "route": "/roles",
                    "icon": "fa-solid:user-cog",
                    "item_order": 4,
                },
                {
                    "text": "FAQ",
                    "route": "/faq",
                    "icon": "mdi:question-mark-circle-outline",
                    "item_order": 5,
                },
                {
                    "text": "Daten einspeisen",
                    "route": "/upload",
                    "icon": "mdi:upload",
                    "item_order": 6,
                },
            ]

            for item_data in default_menu_items:
                menu_item = MenuItem(**item_data)
                session.add(menu_item)

            await session.commit()

            # Assign all menu items to admin role
            from sqlalchemy import select

            admin_role = (
                await session.execute(select(Role).filter(Role.role == "admin"))
            ).scalar_one_or_none()
            if admin_role:
                all_menu_items = (
                    (await session.execute(select(MenuItem))).scalars().all()
                )
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                for item in all_menu_items:
                    stmt = (
                        pg_insert(menu_role)
                        .values(menuitem_id=item.id, roles_id=admin_role.id)
                        .on_conflict_do_nothing()
                    )
                    await session.execute(stmt)

        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()

    # Create default users
    session = AsyncSessionLocal()
    try:
        from sqlalchemy import select

        # Get bot role
        result = await session.execute(select(Role).filter(Role.role == "bot"))
        bot_role = result.scalar_one_or_none()

        # Get admin role
        result = await session.execute(select(Role).filter(Role.role == "admin"))
        admin_role = result.scalar_one_or_none()

        # Log if roles are missing
        if not admin_role:
            logger.warning(
                "Admin role not found. Please ensure roles are created first."
            )
        if not bot_role:
            logger.warning("Bot role not found. Please ensure roles are created first.")

        # Create bot user if it doesn't exist
        result = await session.execute(select(User).filter(User.username == "bot"))
        bot_user = result.scalar_one_or_none()

        if not bot_user and bot_role:
            if not BOOTSTRAP_BOT_PASSWORD:
                logger.warning(
                    "Skipping bot bootstrap user because BOOTSTRAP_BOT_PASSWORD is not set."
                )
            else:
                hashed_password = await password_helper.get_password_hash(
                    BOOTSTRAP_BOT_PASSWORD
                )

                bot = User(
                    username="bot",
                    firstname="Chat",
                    lastname="Bot",
                    password=hashed_password,
                    role_id=bot_role.id,
                    is_active=True,
                )
                session.add(bot)
                logger.info("Bot user created successfully")

        # Create admin user if it doesn't exist
        admin_username = BOOTSTRAP_ADMIN_USERNAME.strip()
        result = await session.execute(
            select(User).filter(User.username == admin_username)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_username:
            logger.info(
                "Skipping admin bootstrap user because BOOTSTRAP_ADMIN_USERNAME is not set."
            )
        elif not admin_user and admin_role:
            if not BOOTSTRAP_ADMIN_PASSWORD:
                logger.warning(
                    "Skipping admin bootstrap user because BOOTSTRAP_ADMIN_PASSWORD is not set."
                )
            else:
                hashed_password = await password_helper.get_password_hash(
                    BOOTSTRAP_ADMIN_PASSWORD
                )

                admin = User(
                    username=admin_username,
                    firstname="Admin",
                    lastname="User",
                    password=hashed_password,
                    role_id=admin_role.id,
                    is_active=True,
                )
                session.add(admin)
                logger.info("Admin user '%s' created successfully", admin_username)
        elif admin_user:
            logger.info("Admin user '%s' already exists", admin_username)

        # If bot user exists but bot_role wasn't fetched earlier, fetch it for logging
        if bot_user and not bot_role:
            result = await session.execute(select(Role).filter(Role.role == "bot"))
            bot_role = result.scalar_one_or_none()
            if bot_user:
                logger.info("Bot user already exists")

        await session.commit()

    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating default users: {str(e)}")
        raise e
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get async DB session"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# Export commonly used names for convenience
__all__ = [
    "engine",
    "AsyncSessionLocal",
    "Base",
    "init_db",
    "get_db",
    "get_async_session",
]
