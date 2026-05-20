# app/routers/menu_resource.py

from typing import List
from fastapi import APIRouter, HTTPException, Depends, Request
from app.config.log.log_config import get_logger
from app.services.menu_resource_service import MenuResourceService
from app.schemas.menu import MenuItemDTO, MenuItemOrderDTO
from app.routers.user import get_current_user, check_admin_permission
from app.config.database.database import get_db

router = APIRouter(prefix="/MenuResource", tags=["MenuResource"])
logger = get_logger("menu_resource_router")


# Dependency to get the service instance
async def get_menu_service(db=Depends(get_db)):
    return MenuResourceService(db)


@router.post("/SaveMenuDetails", response_model=MenuItemDTO)
async def save_menu_details(
    menu_item_dto: MenuItemDTO,
    current_user=Depends(get_current_user),
    menu_service=Depends(get_menu_service),
):
    """
    Save or update menu details (Admin only)
    """
    try:
        logger.info(f"Sava {current_user.id} saving menu details")
        logger.info(f"MenuItemDTO received: {menu_item_dto.id}, {menu_item_dto.text}")
        # Check if user is admin
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(f"Admin user {current_user.id} saving menu details")
        logger.info(f"MenuItemDTO received: {menu_item_dto}")
        return await menu_service.save_menu_details(menu_item_dto)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving menu details: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetMenuData", response_model=List[MenuItemDTO])
async def get_menu_data(
    request: Request,
    current_user=Depends(get_current_user),
    menu_service=Depends(get_menu_service),
):
    """
    Get all menu data (Admin only)
    """
    try:
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(f"Admin user {current_user.id} fetching menu data")
        return await menu_service.get_menu_data()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching menu data: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetMenuDetailsById/{menu_id}", response_model=MenuItemDTO)
async def get_menu_details_by_id(
    menu_id: int,
    current_user=Depends(get_current_user),
    menu_service=Depends(get_menu_service),
):
    """
    Get menu details by ID (Admin only)
    """
    try:
        # Check if user is admin
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(
            f"Admin user {current_user.id} fetching menu details for ID: {menu_id}"
        )
        logger.debug(f"Menu ID requested: {menu_id}")
        return await menu_service.get_menu_details_by_id(menu_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching menu details by ID {menu_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/DeletedMenuById/{menu_id}", response_model=bool)
async def delete_menu_by_id(
    menu_id: int,
    current_user=Depends(get_current_user),
    menu_service=Depends(get_menu_service),
):
    """
    Delete menu by ID (Admin only)
    """
    try:
        # Check if user is admin
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        logger.info(f"Admin user {current_user.id} deleting menu with ID: {menu_id}")
        return await menu_service.delete_menu_by_id(menu_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting menu by ID {menu_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ReorderMenuItems", response_model=bool)
async def reorder_menu_items(
    menu_items: List[MenuItemOrderDTO],
    current_user=Depends(get_current_user),
    menu_service=Depends(get_menu_service),
):
    """
    Reorder menu items (Admin only)
    """
    try:
        # Check if user is admin
        if not check_admin_permission(current_user):
            logger.warning(f"Unauthorized access attempt by user {current_user.id}")
            raise HTTPException(status_code=403, detail="Forbidden")

        # Validate input
        if not menu_items:
            raise HTTPException(
                status_code=400, detail="Invalid input. The menu item list is empty."
            )

        # Ensure all IDs and orders are unique (filter out None ids)
        orders = [item.itemOrder for item in menu_items]
        ids = [item.id for item in menu_items]

        if len(set(orders)) != len(orders):
            raise HTTPException(
                status_code=400, detail="Duplicate orders found in the input."
            )

        if len(set(ids)) != len(ids):
            raise HTTPException(
                status_code=400, detail="Duplicate IDs found in the input."
            )

        logger.info(
            f"Admin user {current_user.id} reordering {len(menu_items)} menu items"
        )
        return await menu_service.reorder_menu_items(menu_items)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reordering menu items: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
