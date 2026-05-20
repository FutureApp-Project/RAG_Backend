from app.schemas.user import (
    UserUpdate,
    UserProfileResponse,
    UserProfileUpdate,
)
from typing import cast
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.database.database import get_db
from app.models.user import User
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.config.log.log_config import get_logger
from app.services.user_service import UserService
from pydantic import ValidationError
from app.core.dependencies import get_current_user as dependency_get_current_user

logger = get_logger("user_router")

router = APIRouter(prefix="/users", tags=["users"])


# Re-export for backward compat (imported by UserResource.py, MenuResource.py, login.py, chat.py)
get_current_user = dependency_get_current_user


def check_admin_permission(current_user) -> bool:
    """Check if current user has admin role."""
    if hasattr(current_user, "role") and current_user.role:
        # User model loaded via SQLAlchemy with role relationship
        role_name = getattr(current_user.role, "role", None)
        if role_name == "admin":
            return True
    # TokenData from JWT with role string
    if hasattr(current_user, "role") and isinstance(current_user.role, str):
        if current_user.role == "admin":
            return True
    return False


@router.patch("/me")
async def update_users_me(
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(dependency_get_current_user),
):
    current_user_id = cast(int, current_user.id)
    logger.info(
        f"/users/me PATCH called by user: {current_user.username} (id={current_user_id})"
    )
    update_data = user_update.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    # Prevent changing username to an existing username
    if "username" in update_data:
        result = await db.execute(
            select(User).filter(User.username == update_data["username"])
        )
        existing_user = result.scalar_one_or_none()
        if existing_user is not None and cast(int, existing_user.id) != current_user_id:
            raise HTTPException(status_code=400, detail="Username already taken")

    # Only allow updating safe fields - prevent privilege escalation
    ALLOWED_FIELDS = {"firstname", "lastname", "username", "password"}
    for field, value in update_data.items():
        if field not in ALLOWED_FIELDS:
            raise HTTPException(status_code=400, detail=f"Cannot update field: {field}")
        setattr(current_user, field, value)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    logger.info(f"User updated: {current_user.username} (id={current_user_id})")
    return {
        "id": current_user_id,
        "username": current_user.username,
        "firstname": current_user.firstname,
        "lastname": current_user.lastname,
        "role": current_user.role.role if current_user.role else None,
        "role_id": current_user.role_id,
        "is_active": current_user.is_active,
        "is_deleted": current_user.is_deleted,
    }


@router.get("/me")
async def read_users_me(current_user: User = Depends(dependency_get_current_user)):
    current_user_id = cast(int, current_user.id)
    logger.info(
        f"/users/me endpoint called by user: {current_user.username} (id={current_user_id})"
    )
    return {
        "id": current_user_id,
        "username": current_user.username,
        "firstname": current_user.firstname,
        "lastname": current_user.lastname,
        "role": current_user.role.role if current_user.role else None,
        "role_id": current_user.role_id,
        "is_active": current_user.is_active,
        "is_deleted": current_user.is_deleted,
    }


@router.get("/{user_id}")
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(dependency_get_current_user),
):
    logger.info(f"/users/{{user_id}} endpoint called for user_id: {user_id}")

    # Users can only view their own profile; admins can view any
    current_user_id = cast(int, current_user.id)
    if current_user_id != user_id and not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile",
        )

    result = await db.execute(
        select(User).options(selectinload(User.role)).filter(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"User not found for id: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    logger.info(f"User found: {user.username} (id={user.id})")
    # Return a minimal user dict (customize as needed)
    return {
        "id": user.id,
        "username": user.username,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "role": user.role.role if user.role else None,
        "role_id": user.role_id,
        "is_active": user.is_active,
        "is_deleted": user.is_deleted,
    }


# Update user's own profile (firstname, lastname, password)
@router.put("/updatePatient/{user_id}", response_model=UserProfileResponse)
async def update_user_profile(
    user_id: int,
    user_update: UserProfileUpdate,
    current_user: User = Depends(dependency_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user's own profile - only firstname, lastname, and password"""
    current_user_id = cast(int, current_user.id)
    logger.info("Profile update requested for user_id=%s", user_id)

    try:
        update_dict = user_update.dict(exclude_unset=True)
        logger.info(
            "Profile update fields=%s user_id=%s",
            sorted(update_dict.keys()),
            user_id,
        )

        if current_user_id != user_id:
            logger.warning(
                "Forbidden profile update attempt actor_user_id=%s target_user_id=%s",
                current_user_id,
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile",
            )

        user_service = UserService(db)
        current_password = update_dict.pop("current_password", None)

        if "new_password" in update_dict:
            if update_dict["new_password"]:
                update_dict["password"] = update_dict.pop("new_password")
            else:
                update_dict.pop("new_password")

        try:
            user_update_obj = UserUpdate(**update_dict)
        except ValidationError as ve:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid update data: {ve.errors()}",
            )

        try:
            updated_user = await user_service.update_user_profile(
                user_id=user_id,
                current_user_id=current_user_id,
                user_update=user_update_obj,
                current_password=current_password,
            )
            logger.info("Profile updated successfully for user_id=%s", user_id)

        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except Exception:
            logger.error("Full traceback:", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile",
            )

        return updated_user

    except HTTPException as http_exc:
        logger.warning(
            "Profile update rejected for user_id=%s status=%s",
            user_id,
            http_exc.status_code,
        )
        raise http_exc

    except Exception as e:
        logger.critical(f"UNEXPECTED ERROR: {type(e).__name__}: {str(e)}")
        logger.critical("Full traceback:", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred",
        )


# Deactivate user account
@router.delete("/{user_id}/deactivate", response_model=dict)
async def deactivate_user_account(
    user_id: int,
    current_user: User = Depends(dependency_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate user account (soft delete) - users can only deactivate their own account"""
    current_user_id = cast(int, current_user.id)
    user_service = UserService(db)

    success = await user_service.deactivate_user(user_id, current_user_id)

    if success:
        return {"message": "Account deactivated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate account",
        )
