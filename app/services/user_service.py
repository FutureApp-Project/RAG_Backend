from app.config.log.log_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from typing import Optional
from .. import models
from ..schemas.user import UserUpdate
from app.config.helper.password_helper import PasswordHelper
from datetime import datetime

logger = get_logger("UserService")


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_id(self, user_id: int) -> models.User:
        """Get user by ID"""
        try:
            result = await self.db.execute(
                select(models.User).filter(
                    models.User.id == user_id, ~models.User.is_deleted
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
                )

            return user
        except Exception as e:
            logger.error(f"Error getting user by id {user_id}: {str(e)}")
            raise

    async def get_user_by_username(self, username: str) -> models.User:
        """Get user by username"""
        try:
            result = await self.db.execute(
                select(models.User).filter(
                    models.User.username == username, ~models.User.is_deleted
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
                )

            return user
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {str(e)}")
            raise

    async def update_user_profile(
        self,
        user_id: int,
        current_user_id: int,
        user_update: UserUpdate,
        current_password: Optional[str] = None,
    ) -> models.User:
        """
        Update user's own profile - only firstname, lastname, and password
        Users can only update their own profile
        """
        logger.info(
            f"Updating profile for user_id: {user_id}, current_user_id: {current_user_id}"
        )

        try:
            if user_id != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to update this user's data",
                )

            db_user = await self.get_user_by_id(user_id)
            logger.info(f"Found user: {db_user.username}")

            updated_fields = []

            if user_update.password:
                if not current_password:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Current password is required to change password",
                    )

                if not db_user.password or not await PasswordHelper.verify_password(
                    current_password,
                    db_user.password,
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Current password is incorrect",
                    )

                db_user.password = await PasswordHelper.get_password_hash(
                    user_update.password
                )
                updated_fields.append("password")
                logger.info("Password updated")

            if user_update.firstname is not None:
                db_user.firstname = user_update.firstname
                updated_fields.append("firstname")
                logger.info(f"Firstname updated to: {user_update.firstname}")

            if user_update.lastname is not None:
                db_user.lastname = user_update.lastname
                updated_fields.append("lastname")
                logger.info(f"Lastname updated to: {user_update.lastname}")

            if updated_fields:
                db_user.updated_at = datetime.utcnow()
                updated_fields.append("updated_at")
                logger.info(f"User {user_id} profile updated at {db_user.updated_at}")

                await self.db.commit()
                await self.db.refresh(db_user)
                logger.info(f"Successfully updated fields: {', '.join(updated_fields)}")
            else:
                logger.info("No fields to update")

            return db_user

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"Error updating user profile for user_id {user_id}: {str(e)}")
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user profile",
            )

    def validate_user_access(self, user_id: int, current_user: models.User) -> bool:
        """Validate if current user can access the requested user's data"""
        return user_id == current_user.id

    async def deactivate_user(self, user_id: int, current_user_id: int) -> bool:
        """
        Deactivate user account (soft delete)
        Users can only deactivate their own account
        """
        if user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to deactivate this account",
            )

        try:
            db_user = await self.get_user_by_id(user_id)
            db_user.is_active = False
            db_user.is_deleted = True
            db_user.updated_at = datetime.utcnow()

            await self.db.commit()
            logger.info(f"User {user_id} deactivated successfully")
            return True
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {str(e)}")
            await self.db.rollback()
            raise
