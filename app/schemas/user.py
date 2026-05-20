# schemas/user.py

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.schemas.MenuItemDto import TagDto


class UserRoleEnum(str, Enum):
    BOT = "bot"
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"


class UserBase(BaseModel):
    firstname: str = Field(..., min_length=1, max_length=50)
    lastname: str = Field(..., min_length=1, max_length=50)
    username: str = Field(..., min_length=3, max_length=50)
    role_id: int = Field(..., ge=1)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)


class UserUpdate(BaseModel):
    firstname: Optional[str] = Field(None, min_length=1, max_length=50)
    lastname: Optional[str] = Field(None, min_length=1, max_length=50)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    role_id: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None

    @validator("password")
    def password_not_empty(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Password cannot be empty")
        return v


class UserDTO(BaseModel):
    id: int
    name: str
    username: str
    rolle: str
    password: Optional[str] = None
    passwordneeded: Optional[bool] = None
    is_user_exit: bool = False
    is_password_wrong: bool = False
    user_can_login: bool = False
    is_deleted: bool = False
    is_admin: bool = False


class UserDetailsDTO(BaseModel):
    id: int
    firstname: str
    lastname: str
    username: str
    rolle: Optional[str] = None
    password: Optional[str] = None
    repeatPassword: Optional[str] = None  # Add this to match frontend
    passwordneeded: Optional[bool] = None
    is_user_exit: bool = False
    is_password_wrong: bool = False
    selectedRollenIDs: List[int] = Field(
        default_factory=list, alias="SelectedRollenIDs"
    )  # Changed from list[str] to list[int] to match frontend
    Tags: list[TagDto] = Field(default_factory=list)
    tags_name: Optional[str] = None  # Add this to match frontend

    class Config:
        # This allows accepting both 'SelectedRollenIDs' and 'selectedRollenIDs'
        populate_by_name = True

    def get_rollen_ids(self) -> List[int]:
        """Helper method to get rollen IDs regardless of field name"""
        return self.selectedRollenIDs


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1)


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool
    is_deleted: bool

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class UserProfileResponse(BaseModel):
    """Response schema for user profile (non-sensitive data)"""

    id: int
    firstname: str
    lastname: str
    username: str
    role_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class UserProfileUpdate(BaseModel):
    """Schema for user updating their own profile"""

    firstname: Optional[str] = Field(None, min_length=1, max_length=50)
    lastname: Optional[str] = Field(None, min_length=1, max_length=50)
    current_password: Optional[str] = Field(
        None, min_length=1, description="Required when changing password"
    )
    new_password: Optional[str] = Field(None, min_length=6, max_length=100)

    @validator("new_password")
    def validate_password_change(cls, v, values):
        if v and not values.get("current_password"):
            raise ValueError("Current password is required to change password")
        return v


class UserAdminUpdate(BaseModel):
    """Schema for admin updating user profile (includes all fields)"""

    firstname: Optional[str] = Field(None, min_length=1, max_length=50)
    lastname: Optional[str] = Field(None, min_length=1, max_length=50)

    password: Optional[str] = Field(None, min_length=1, max_length=100)
    role_id: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None

    @validator("password")
    def password_not_empty(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Password cannot be empty")
        return v
