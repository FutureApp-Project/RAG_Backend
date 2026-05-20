from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.config.database.database import get_db
from app.services.menu_service import MenuService
from schemas.menu import MenuItemCreate, MenuItemUpdate, MenuItemResponse
from app.core.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("/", response_model=List[MenuItemResponse])
def get_all_menu_items(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    """
    Get all menu items (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    return menu_service.get_all_menu_items()


@router.get("/{menu_id}", response_model=MenuItemResponse)
def get_menu_item(
    menu_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    """
    Get menu item by ID (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    menu_item = menu_service.get_menu_item_by_id(menu_id)
    if not menu_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found"
        )
    return menu_item


@router.get("/role/{role_id}", response_model=List[MenuItemResponse])
def get_menu_items_by_role(
    role_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    """
    Get menu items accessible by a specific role (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    return menu_service.get_menu_items_by_role(role_id)


@router.post("/", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
def create_menu_item(
    menu_data: MenuItemCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new menu item (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    try:
        return menu_service.create_menu_item(menu_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{menu_id}", response_model=MenuItemResponse)
def update_menu_item(
    menu_id: int,
    menu_data: MenuItemUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update a menu item (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    try:
        menu_item = menu_service.update_menu_item(menu_id, menu_data)
        if not menu_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found"
            )
        return menu_item
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{menu_id}/roles", response_model=MenuItemResponse)
def update_menu_roles(
    menu_id: int,
    role_ids: List[int],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update roles for a menu item (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    try:
        menu_item = menu_service.update_menu_roles(menu_id, role_ids)
        if not menu_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found"
            )
        return menu_item
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_item(
    menu_id: int,
    soft_delete: bool = True,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Delete a menu item (admin only)
    """
    require_admin(current_user)
    menu_service = MenuService(db)
    success = menu_service.delete_menu_item(menu_id, soft_delete)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found"
        )
