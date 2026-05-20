# app/routers/login.py
from typing import List
from fastapi import APIRouter, Depends, Request, HTTPException
from app.config.log.log_config import get_logger
from app.routers.user import get_current_user
from app.schemas.MenuItemDto import MenuItemDto
from app.services.login_service import login_service
from app.schemas.user import UserLogin, UserCreate
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["authentication"])
logger = get_logger("auth_router")
loginService = login_service


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, user_credentials: UserLogin):
    """User login endpoint"""
    try:
        route = router.prefix + "/login"
        logger.info(f"Route: {route} | Username: {user_credentials.username}")

        result = await loginService.login(
            username=user_credentials.username, password=user_credentials.password
        )
        logger.info(
            "Login service completed for user=%s status=%s",
            user_credentials.username,
            result.get("status"),
        )
        if result["status"] == "error":
            logger.warning(f"Login failed for user: {user_credentials.username}")
            raise HTTPException(status_code=401, detail=result["message"])

        logger.info(f"Login successful for user: {user_credentials.username}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in login endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/signup")
@limiter.limit("3/minute")
async def signup(request: Request, user_data: UserCreate):
    """User registration endpoint"""
    try:
        route = router.prefix + "/signup"
        logger.info(f"Route: {route} | Username: {user_data.username}")

        # Convert Pydantic model to dict
        user_dict = user_data.dict()

        result = await loginService.signup(user_dict)

        if result["status"] == "error":
            logger.warning(f"Signup failed for user: {user_data.username}")
            raise HTTPException(status_code=400, detail=result["message"])

        logger.info(f"Signup successful for user: {user_data.username}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in signup endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetMenu", response_model=List[MenuItemDto])
async def get_menu(request: Request, current_user=Depends(get_current_user)):
    """
    Get menu items for authenticated user

    Args:
        current_user: Automatically extracted from JWT token via dependency

    Returns:
        List of menu items based on user's role and permissions
    """
    try:
        # current_user is injected by Depends(get_current_user)
        logger.info("Fetching menu for user")
        logger.info(f"user_id={current_user.id}")

        # Check admin role
        role_name = current_user.role.role if current_user.role else "N/A"
        logger.info(f"role={role_name}")
        is_admin = role_name == "admin"
        logger.info(f"is_admin={is_admin}")

        # Get role ID for filtering
        role_id = current_user.role.id if current_user.role else None
        if role_id is None:
            raise HTTPException(status_code=403, detail="User role is not assigned")

        # Call service to get menu items
        menu_items = await loginService.get_menu(roles_id=role_id, is_admin=is_admin)

        logger.info(
            f"Retrieved {len(menu_items)} menu items for user: {current_user.id}"
        )
        return menu_items

    except HTTPException as http_exc:
        logger.error(f"Error in get_menu endpoint: {str(http_exc.detail)}")
        raise
    except Exception as e:
        logger.error(f"Error in get_menu endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
