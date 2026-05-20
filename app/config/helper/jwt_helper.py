# app/helpers/jwt_helper.py
from typing import Optional, Dict, Any

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from app.config.security import JWT_SECRET_KEY, JWT_ALGORITHM
from app.schemas.token import TokenData

security = HTTPBearer()


class JWTHelper:
    """JWT token management helper"""


# Module-level verify_tokens function
def verify_tokens(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify JWT token and extract user info"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Create TokenData - handle sub as username if username is not present
        if "sub" in payload and "username" not in payload:
            payload["username"] = payload["sub"]

        user_data = TokenData(**payload)

        return user_data
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")


# Create singleton instance
jwt_helper = JWTHelper()
