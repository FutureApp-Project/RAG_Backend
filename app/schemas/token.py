# app/schemas/token.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Token(BaseModel):
    """Schema for OAuth2 token response"""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: Optional[int] = Field(
        3600, description="Token expiration time in seconds"
    )
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    scope: Optional[str] = Field("", description="Token scope")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "scope": "",
            }
        }


class TokenPayload(BaseModel):
    """Schema for JWT token payload"""

    sub: str = Field(..., description="Subject (user identifier)")
    exp: datetime = Field(..., description="Expiration time")
    iat: Optional[datetime] = Field(None, description="Issued at time")
    jti: Optional[str] = Field(None, description="JWT ID")
    user_id: Optional[int] = Field(None, description="User ID")
    username: Optional[str] = Field(None, description="Username")

    roles: Optional[List[str]] = Field([], description="User roles")
    permissions: Optional[List[str]] = Field([], description="User permissions")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "sub": "user123",
                "exp": "2024-12-31T23:59:59Z",
                "iat": "2024-01-01T00:00:00Z",
                "jti": "unique-token-id",
                "user_id": 1,
                "username": "john_doe",
                "roles": ["user", "admin"],
                "permissions": ["read", "write"],
            }
        }


class TokenData(BaseModel):
    """Schema for token data used in dependencies"""

    username: Optional[str] = None
    user_id: Optional[int] = None
    sub: Optional[str] = None
    roles: Optional[List[str]] = None
    permissions: Optional[List[str]] = None
    expires: Optional[datetime] = None


class Config:
    from_attributes = True


# Add property to get username from sub if username is None
@property
def effective_username(self) -> Optional[str]:
    return self.username or self.sub


@property
def isAdmin(self) -> bool:
    return "admin" in self.roles if self.roles else False


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""

    refresh_token: str = Field(..., description="Refresh token")
    grant_type: str = Field("refresh_token", description="Grant type")


class TokenRefreshResponse(BaseModel):
    """Schema for token refresh response"""

    access_token: str = Field(..., description="New access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(3600, description="Token expiration time in seconds")
    refresh_token: Optional[str] = Field(
        None, description="New refresh token (if rotated)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            }
        }


class TokenValidationResponse(BaseModel):
    """Schema for token validation response"""

    valid: bool = Field(..., description="Whether the token is valid")
    message: Optional[str] = Field(None, description="Validation message")
    payload: Optional[TokenPayload] = Field(None, description="Decoded token payload")
    expires_in: Optional[int] = Field(None, description="Seconds until expiration")

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "message": "Token is valid",
                "payload": {
                    "sub": "user123",
                    "exp": "2024-12-31T23:59:59Z",
                    "user_id": 1,
                    "username": "john_doe",
                },
                "expires_in": 3600,
            }
        }


class TokenRevokeRequest(BaseModel):
    """Schema for token revocation request"""

    token: str = Field(..., description="Token to revoke")
    token_type_hint: Optional[str] = Field(
        None, description="Type of token (access_token or refresh_token)"
    )


class TokenRevokeResponse(BaseModel):
    """Schema for token revocation response"""

    revoked: bool = Field(..., description="Whether the token was revoked")
    message: str = Field(..., description="Revocation message")

    class Config:
        json_schema_extra = {
            "example": {"revoked": True, "message": "Token successfully revoked"}
        }


class OAuth2PasswordRequest(BaseModel):
    """Schema for OAuth2 password grant request"""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    grant_type: str = Field("password", description="Grant type")
    scope: Optional[str] = Field("", description="Requested scope")
    client_id: Optional[str] = Field(None, description="Client ID")
    client_secret: Optional[str] = Field(None, description="Client secret")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "secret",
                "grant_type": "password",
                "scope": "",
                "client_id": "webapp",
                "client_secret": "webapp-secret",
            }
        }


class LoginRequest(BaseModel):
    """Schema for login request (simplified version)"""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    remember_me: Optional[bool] = Field(False, description="Remember login")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "secret123",
                "remember_me": True,
            }
        }
