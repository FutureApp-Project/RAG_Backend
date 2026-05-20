# app/routers/user_resource.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, Path
from app.schemas.user import UserDTO, UserDetailsDTO
from app.services.user_resource_service import UserResourceService
from app.routers.user import get_current_user, check_admin_permission
from app.config.database.database import get_db
from app.config.log.log_config import get_logger
from app.schemas.token import TokenData

router = APIRouter(prefix="/UserResource", tags=["UserResource"])
logger = get_logger("user_resource_router")


def get_user_service(db=Depends(get_db)):
    return UserResourceService(db)


def allowed_to_edit(current_user: TokenData, target_user_id: int) -> bool:
    """
    Check if current user is allowed to edit target user
    Admins can edit anyone, users can only edit themselves
    """
    if check_admin_permission(current_user):
        return True

    # Check if user_id from token matches target user_id
    current_user_id = getattr(current_user, "user_id", None)
    if current_user_id is None:
        current_user_id = getattr(current_user, "id", None)

    if current_user_id is None:
        return False

    return current_user_id == target_user_id


@router.get("/GetUsers", response_model=List[UserDTO])
async def get_users(
    request: Request,
    current_user=Depends(get_current_user),
    user_service=Depends(get_user_service),
):
    """
    Get all users with their tags (Admin only)
    """
    try:
        logger.info("Fetching all users")
        # Check if user is admin
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(f"Admin user {current_user.id} fetching users")
        return await user_service.get_users()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetAllPatientUsers", response_model=List[UserDTO])
async def Get_All_Patient_Users(
    request: Request,
    current_user=Depends(get_current_user),
    user_service=Depends(get_user_service),
):
    """
    Get all patient users (Admin only)
    """
    try:
        logger.info("Fetching all patient users")
        # Check if user is admin
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(f"Admin user {current_user.id} fetching patient users")
        return await user_service.Get_All_Patient_Users()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient users: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetUserDetailsById/{user_id}", response_model=UserDetailsDTO)
async def get_user_details_by_id(
    user_id: int = Path(..., description="User ID"),
    current_user=Depends(get_current_user),
    user_service=Depends(get_user_service),
):
    """
    Get user details by ID
    """
    try:

        logger.info(f"GetUserDetailsById endpoint called with user_id: {user_id}")
        # Check if user is allowed to edit this user
        if not allowed_to_edit(current_user, user_id):
            logger.warning(f"User {current_user.id} not allowed to view user {user_id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(f"User {current_user.id} fetching details for user {user_id}")
        is_admin = check_admin_permission(current_user)
        return await user_service.get_user_details_by_id(user_id, is_admin)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user details by ID {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/SaveUserDetails", response_model=UserDetailsDTO)
async def save_user_details(
    user_dto: UserDetailsDTO,
    current_user=Depends(get_current_user),
    user_service=Depends(get_user_service),
):
    """
    Save or update user details
    """
    try:
        logger.info(f"SaveUserDetails called for user_id={user_dto.id}, username={user_dto.username}")

        # Validate password if provided
        if user_dto.password and user_dto.password != user_dto.repeatPassword:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        # Check if user is allowed to edit this user
        if not allowed_to_edit(
            current_user, user_dto.id if user_dto.id and user_dto.id != -1 else -1
        ):
            logger.warning(
                f"User {current_user.id} not allowed to edit user {user_dto.id}"
            )
            raise HTTPException(status_code=403, detail="Forbidden")

        # Validate input - use selectedRollenIDs instead of selectedRollenIDs
        if not user_dto.selectedRollenIDs or len(user_dto.selectedRollenIDs) == 0:
            raise HTTPException(
                status_code=400, detail="Benutzerdetails oder Rollen fehlen."
            )

        logger.info(f"User {current_user.id} saving details for user {user_dto.id}")
        return await user_service.save_user_details(user_dto)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving user details: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/DeletedUserById/{userId}", response_model=bool)
async def delete_user_by_id(
    userId: int = Path(..., description="User ID"),  # Use 'userId' (camelCase)
    current_user=Depends(get_current_user),
    user_service=Depends(get_user_service),
):
    try:
        logger.info(f"Attempting to delete user with ID {userId}")
        # Only admins can delete users
        if not check_admin_permission(current_user):
            logger.warning(f"Non-admin user attempted to delete user {userId}")
            raise HTTPException(status_code=403, detail="Forbidden")

        admin_id = (
            getattr(current_user, "id", None)
            or getattr(current_user, "user_id", None)
            or str(current_user)
        )
        logger.info(f"Admin user {admin_id} deleting user {userId}")
        deleted = await user_service.delete_user_by_id(userId)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        return True

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user by ID {userId}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
