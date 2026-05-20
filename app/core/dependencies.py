from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from app.config.database.database import get_db
from app.models.user import User
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.config.security import JWT_SECRET_KEY, JWT_ALGORITHM
from app.config.log.log_config import get_logger


logger = get_logger("dependencies")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current authenticated user
    """
    logger.info("get_current_user called")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        logger.info("Decoding JWT token")
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        logger.info(f"Token payload username: {username}")
        if username is None:
            logger.warning("Username not found in token payload")
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWTError: {str(e)}")
        raise credentials_exception
    
    result = await db.execute(
        select(User).options(selectinload(User.role)).filter(User.username == username)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        logger.warning(f"User not found for username: {username}")
        raise credentials_exception
    
    if not user.is_active or user.is_deleted:
        logger.warning(f"User account is inactive or deleted: {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive or deleted"
        )
    
    logger.info(f"Authenticated user: {user.username} (id={user.id}, role={user.role.role if user.role else None})")
    return user

def require_admin(current_user: User) -> None:
    """
    Check if current user has admin role
    """
    if not current_user.role:
        logger.error(f"User {current_user.username} has no role assigned")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no role assigned"
        )
    
    if current_user.role.role != "admin":
        logger.warning(f"User {current_user.username} attempted to access admin-only endpoint")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin access required."
        )
    
    logger.info(f"Admin access granted for user: {current_user.username}")