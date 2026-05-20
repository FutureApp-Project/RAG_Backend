from app.config.log.log_config import get_logger
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import List

from app.config.database.database import get_db
from app.services.role_service import RoleService
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse, TagDto
from app.core.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/RoleResource", tags=["RoleResource"])
logger = get_logger("role_resource_router")


@router.get("/GetRoles", response_model=List[TagDto])
async def get_all_roles(
    request: Request,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get all roles (admin only)
    """
    logger.info("Fetching all roles")
    require_admin(current_user)
    role_service = RoleService(db)
    roles = await role_service.get_all_roles()
    # logger.info("Successfully fetched all roles - %s", roles)
    role_payload = [
        {
            "id": role.id,
            "role": role.role,
            "name": role.role,
            "is_active": role.is_active,
            "is_deleted": role.is_deleted,
        }
        for role in roles
    ]
    logger.info("Fetched roles from database: %s", role_payload)
    return roles


@router.get("/GetRoleDetailsById/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int, db=Depends(get_db), current_user=Depends(get_current_user)
):
    """
    Get role by ID (admin only)
    """
    require_admin(current_user)
    role_service = RoleService(db)
    role = await role_service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return role


@router.post(
    "/SaveRoleDetails", response_model=RoleResponse, status_code=status.HTTP_201_CREATED
)
async def create_role(
    role_data: RoleCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new role (admin only)
    """
    require_admin(current_user)
    role_service = RoleService(db)
    try:
        return await role_service.create_role(role_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/UpdateRoleDetails", response_model=RoleResponse)
async def update_role(
   
    role_data: RoleUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update a role (admin only)
    """
    require_admin(current_user)
    role_service = RoleService(db)

    # Prevent updating system roles
    existing_role = await role_service.get_role_by_id(role_data.id)
    if existing_role and existing_role.role in ["admin", "bot"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify system roles"
        )

    try:
        role = await role_service.update_role(role_data.id, role_data)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
            )
        return role
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/DeletedRoleById/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    soft_delete: bool = True,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Delete a role (admin only)
    """
    logger.info(f"Attempting to delete role with ID {role_id}")
    require_admin(current_user)
    role_service = RoleService(db)

    try:
        success = await role_service.delete_role(role_id, soft_delete)
        if not success:
            logger.info(f"Role with ID {role_id} not found for deletion")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
            )
    except ValueError as e:
        logger.error(f"Error deleting role with ID {role_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
