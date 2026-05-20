# schemas/role.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class RoleEnum(str, Enum):
    BOT = "bot"
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"


class RoleBase(BaseModel):
    role: str  # Change from RoleEnum to str


class RoleCreate(RoleBase):
    is_active: bool = True


class RoleUpdate(BaseModel):
    id: int
    role: Optional[str] = None  # Change from Optional[RoleEnum]
    is_active: Optional[bool] = None


class RoleResponse(RoleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool
    is_deleted: bool

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class TagDto(BaseModel):
    id: int
    name: Optional[str] = None
    role: Optional[str] = None
    transferable: Optional[bool] = None
