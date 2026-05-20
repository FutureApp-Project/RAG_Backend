# schemas/menu.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from .role import RoleResponse


class MenuItemBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=255)
    route: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=255)
    item_order: int = Field(default=0, ge=0)

    @validator("text")
    def text_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Menu item text cannot be empty")
        return v.strip()


class MenuItemDTO(BaseModel):
    id: Optional[int] = None
    text: str = Field(..., min_length=1, max_length=255)
    route: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=255)
    itemOrder: int = Field(default=0, ge=0)
    selectedRollenIDs: List[int] = Field(default_factory=list)
    rolle: Optional[str] = Field(None, max_length=255)
    tags: List[Dict[str, Any]] = Field(default_factory=list)  # Added tags field

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class MenuItemCreate(MenuItemBase):
    role_ids: List[int] = Field(default_factory=list)


class MenuItemUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=255)
    route: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=255)
    item_order: Optional[int] = Field(None, ge=0)
    isdeleted: Optional[bool] = None
    role_ids: Optional[List[int]] = None


class MenuItemResponse(MenuItemBase):
    id: int
    isdeleted: bool
    roles: Optional[List[RoleResponse]] = None

    class Config:
        from_attributes = True


class MenuItemOrderDTO(BaseModel):
    id: int
    itemOrder: int = Field(..., ge=0)