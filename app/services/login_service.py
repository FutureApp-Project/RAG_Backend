# app/services/login_service.py
"""
Login service for user authentication and token management.
Uses the common security configuration from app.config.security.
"""

from typing import Dict, Any, Optional, cast
from datetime import timedelta
import jwt
from app.config.log.log_config import get_logger
from app.config.database.database import AsyncSessionLocal
from app.config.security import (
    security_config,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.config.helper.password_helper import password_helper
from app.models.user import User
from app.models.role import Role
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload, selectinload

logger = get_logger("login_service")


class LoginService:

    def __init__(self):
        """Initialize LoginService using common security configuration"""
        self.secret_key = JWT_SECRET_KEY
        self.algorithm = JWT_ALGORITHM
        logger.info("LoginService initialized with common security configuration")

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash using password_helper"""
        return await password_helper.verify_password(plain_password, hashed_password)

    async def get_password_hash(self, password: str) -> str:
        """Generate password hash using password_helper"""
        return await password_helper.get_password_hash(password)

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials"""
        try:
            logger.info(f"Authenticating user: {username}")

            async with cast(AsyncSession, AsyncSessionLocal()) as session:
                # Fetch user with role using explicit join
                result = await session.execute(
                    select(User)
                    .join(Role, User.role_id == Role.id)
                    .where(User.username == username)
                    .where(User.is_active)
                    .where(~User.is_deleted)
                    .options(joinedload(User.role))  # This needs the import
                )
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning(f"User not found or inactive: {username}")
                    return None

                # Verify password
                if not await password_helper.verify_password(
                    password, cast(str, user.password)
                ):
                    logger.warning(f"Invalid password for user: {username}")
                    return None

                logger.info(
                    f"User authenticated successfully: {username}, role: {user.role.role}"
                )
                return user

        except Exception as e:
            logger.error(f"Error authenticating user {username}: {str(e)}")
            return None

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token using security_config"""
        try:
            # Use the common security configuration
            if expires_delta:
                token = security_config.create_access_token(data, expires_delta)
            else:
                # Use default expiration from config
                token = security_config.create_access_token(data)

            logger.debug(f"Access token created for user: {data.get('sub')}")
            return token

        except Exception as e:
            logger.error(f"Error creating access token: {str(e)}")
            raise

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create JWT refresh token using security_config"""
        try:
            token = security_config.create_refresh_token(data)
            logger.debug(f"Refresh token created for user: {data.get('sub')}")
            return token
        except Exception as e:
            logger.error(f"Error creating refresh token: {str(e)}")
            raise

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode JWT token using security_config"""
        try:
            return security_config.decode_token(token)
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise

    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Perform login and return token"""
        try:
            logger.info(f"testing login for user: {username}")
            user = await self.authenticate_user(username, password)

            if not user:
                logger.warning(f"Failed login attempt for user: {username}")
                return {"status": "error", "message": "Invalid username or password"}

            # No need to fetch role separately since we already have it via joinedload
            # user.role is already loaded from the authenticate_user query
            if not user.role:
                logger.info(f"Role not found for user: {username}")
                logger.error(f"Role not found for user: {username}")
                return {"status": "error", "message": "User role not found"}

            # Create tokens
            access_token_expires = timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = self.create_access_token(
                data={
                    "sub": user.username,
                    "user_id": user.id,
                    "role": user.role.role,  # Use user.role directly
                    "firstname": user.firstname,
                    "lastname": user.lastname,
                },
                expires_delta=access_token_expires,
            )
            logger.info(
                f"User authenticated successfully: {username}, role: {user.role.role}"
            )
            refresh_token = self.create_refresh_token(
                data={
                    "sub": user.username,
                    "user_id": user.id,
                    "role": user.role.role,  # Use user.role directly
                }
            )

            logger.info(
                f"Login successful for user: {username}, role: {user.role.role}"
            )

            # Create the response object in the requested format
            response_data = {
                "token": access_token,  # Using the actual access token generated
                "user": {
                    "id": user.id,
                    "isAdmin": user.role.role.lower() == "admin",
                    "isDeleted": user.is_deleted,
                    "isLoggedInId": user.id,
                    "username": user.username,
                    "isUserExits": True,
                    "name": f"{user.firstname} {user.lastname}",
                    "rolle": user.role.role,
                    "userCanLogin": user.is_active,
                    "role_id": user.role_id,
                },
                # Additional fields from your original return statement
                "status": "success",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
                "firstname": user.firstname,
                "lastname": user.lastname,
                "role": user.role.role,
            }

            return response_data

        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return {"status": "error", "message": "Internal server error during login"}

    async def get_menu(self, roles_id: int, is_admin: bool = False):
        """Query menu items from DB, filter for admin, and map to DTOs. Includes logging and error handling."""
        from app.schemas.MenuItemDto import MenuItemDto
        from app.models.menu import MenuItem
        from app.config.database.database import AsyncSessionLocal
        from app.models.menu_role import menu_role
        from sqlalchemy import exists
        import traceback

        logger.info(f"get_menu called with roles_id={roles_id}, is_admin={is_admin}")
        try:
            async with cast(AsyncSession, AsyncSessionLocal()) as session:
                if is_admin:
                    logger.info("Querying all menu items for admin user")
                    query = (
                        select(MenuItem)
                        .options(selectinload(MenuItem.roles))
                        .where(~MenuItem.isdeleted)
                        .order_by(MenuItem.item_order)
                    )
                else:
                    logger.info(f"Querying menu items for role_id={roles_id}")
                    subquery = select(1).where(
                        and_(
                            menu_role.c.menuitem_id == MenuItem.id,
                            menu_role.c.roles_id == roles_id,
                        )
                    )
                    query = (
                        select(MenuItem)
                        .options(selectinload(MenuItem.roles))
                        .where(
                            and_(
                                ~MenuItem.isdeleted,
                                exists(subquery).correlate(MenuItem),
                            )
                        )
                        .order_by(MenuItem.item_order)
                    )

                logger.info(f"Executing menu query: {query}")
                result = await session.execute(query)
                menu = result.unique().scalars().all()
                logger.info(f"Fetched {len(menu)} menu items from DB")

            # Map to DTOs
            menu_items = []
            for m in menu:
                role_ids = [role.id for role in m.roles] if m.roles else []
                logger.info(
                    f"Mapping MenuItem id={m.id}, text={m.text}, roles={role_ids}"
                )
                menu_items.append(
                    MenuItemDto(
                        id=cast(int, m.id),
                        text=cast(Optional[str], m.text),
                        route=cast(Optional[str], m.route),
                        icon=cast(Optional[str], m.icon),
                        itemOrder=cast(Optional[int], m.item_order),
                        selectedRollenIDs=role_ids,
                        rolle=m.roles[0].role if m.roles and len(m.roles) > 0 else None,
                        tags=[],
                    )
                )

            if not is_admin:
                items_to_remove = {"Menü", "Rolle"}
                menu_items = [x for x in menu_items if x.text not in items_to_remove]
                logger.info(
                    f"Filtered menu items for non-admin, count={len(menu_items)}"
                )

            logger.info(f"Returning {len(menu_items)} menu items")
            return menu_items
        except Exception as e:
            logger.error(f"Error in get_menu: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using refresh token"""
        try:
            # Decode refresh token
            payload = self.decode_token(refresh_token)

            if payload.get("type") != "refresh":
                logger.warning("Invalid token type for refresh")
                return {"status": "error", "message": "Invalid token type"}

            username = payload.get("sub")
            user_id = payload.get("user_id")
            role = payload.get("role")

            # Verify user still exists and is active
            async with cast(AsyncSession, AsyncSessionLocal()) as session:
                result = await session.execute(
                    select(User).where(
                        User.id == user_id,
                        User.username == username,
                        User.is_active,
                        ~User.is_deleted,  # Use bitwise NOT for SQLAlchemy column
                    )
                )
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning(
                        f"User not found or inactive for token refresh: {username}"
                    )
                    return {"status": "error", "message": "User not found or inactive"}

            # Create new access token
            access_token_expires = timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
            access_token = self.create_access_token(
                data={
                    "sub": username,
                    "user_id": user_id,
                    "role": role,
                    "firstname": user.firstname,
                    "lastname": user.lastname,
                },
                expires_delta=access_token_expires,
            )

            logger.info(f"Token refreshed for user: {username}")

            return {
                "status": "success",
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            }

        except jwt.ExpiredSignatureError:
            logger.warning("Refresh token expired")
            return {"status": "error", "message": "Refresh token expired"}
        except jwt.InvalidTokenError:
            logger.warning("Invalid refresh token")
            return {"status": "error", "message": "Invalid refresh token"}
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return {"status": "error", "message": "Internal server error"}

    async def signup(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register new user"""
        try:
            logger.info(f"Signup attempt for username: {user_data.get('username')}")

            # Validate password strength
            is_valid, error_msg = security_config.validate_password_strength(
                user_data["password"]
            )
            if not is_valid:
                logger.warning(f"Password validation failed: {error_msg}")
                return {"status": "error", "message": error_msg}

            async with cast(AsyncSession, AsyncSessionLocal()) as session:
                # Check if username exists
                result = await session.execute(
                    select(User).where(User.username == user_data["username"])
                )
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    logger.warning(f"Username already exists: {user_data['username']}")
                    return {"status": "error", "message": "Username already exists"}

                # Check if role exists
                result = await session.execute(
                    select(Role).where(Role.id == user_data["role_id"])
                )
                role = result.scalar_one_or_none()

                if not role:
                    logger.warning(f"Role not found: {user_data['role_id']}")
                    return {"status": "error", "message": "Invalid role"}

                # Hash password
                hashed_password = await self.get_password_hash(user_data["password"])

                # Create user
                user = User(
                    firstname=user_data["firstname"],
                    lastname=user_data["lastname"],
                    username=user_data["username"],
                    password=hashed_password,
                    role_id=user_data["role_id"],
                    is_active=True,
                )

                session.add(user)
                await session.commit()
                await session.refresh(user)

                logger.info(
                    f"User created successfully: {user_data['username']}, role: {role.role}"
                )

                return {
                    "status": "success",
                    "message": "User registered successfully",
                    "user_id": user.id,
                    "username": user.username,
                    "role": role.role,
                }

        except Exception as e:
            logger.error(f"Signup error: {str(e)}")
            return {"status": "error", "message": f"Error during signup: {str(e)}"}

    async def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> Dict[str, Any]:
        """Change user password"""
        try:
            async with cast(AsyncSession, AsyncSessionLocal()) as session:
                # Get user
                result = await session.execute(
                    select(User).where(
                        User.id == user_id,
                        User.is_active,
                        ~User.is_deleted,
                    )
                )
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning(f"User not found for password change: {user_id}")
                    return {"status": "error", "message": "User not found"}

                # Verify current password
                if not await self.verify_password(
                    current_password, cast(str, user.password)
                ):
                    logger.warning(
                        f"Incorrect current password for user: {user.username}"
                    )
                    return {
                        "status": "error",
                        "message": "Current password is incorrect",
                    }

                # Validate new password strength
                is_valid, error_msg = security_config.validate_password_strength(
                    new_password
                )
                if not is_valid:
                    logger.warning(f"New password validation failed: {error_msg}")
                    return {"status": "error", "message": error_msg}

                # Hash new password
                hashed_password = await self.get_password_hash(new_password)

                # Update password
                setattr(user, "password", hashed_password)
                await session.commit()

                logger.info(f"Password changed successfully for user: {user.username}")

                return {"status": "success", "message": "Password changed successfully"}

        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            return {"status": "error", "message": "Error changing password"}


# Create singleton instance
login_service = LoginService()
