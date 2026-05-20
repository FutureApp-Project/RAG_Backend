from pydantic import BaseModel, Field, validator
from typing import Optional, List


# First, define TagDto if you don't have it yet
class TagDto(BaseModel):
    id: int
    name: str = Field(..., min_length=1, max_length=255)
    color: Optional[str] = Field(None, max_length=50)

    class Config:
        from_attributes = True


# Now the main MenuItemDto
class MenuItemDto(BaseModel):
    id: int
    text: Optional[str] = Field(None, max_length=255)
    route: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=255)
    item_order: Optional[int] = Field(None, ge=0, alias="itemOrder")
    selected_rollen_ids: List[int] = Field(
        default_factory=list, alias="selectedRollenIDs"
    )
    tags: List[TagDto] = Field(default_factory=list)
    rolle: Optional[str] = Field(None, max_length=255)

    @validator("text")
    def validate_text(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Text cannot be empty if provided")
        return v.strip() if v else v

    class Config:
        # Allow population by field name (both snake_case and camelCase)
        validate_by_name = True
        # Enable ORM mode if working with SQLAlchemy
        from_attributes = True
