# models/menu.py
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from .base import Base

class MenuItem(Base):
    __tablename__ = "menuitem"
    
    id = Column(Integer, primary_key=True, index=True)
    text = Column(String(255), nullable=False, unique=True)
    route = Column(String(255), nullable=True)
    icon = Column(String(255), nullable=True)
    item_order = Column(Integer, default=0)
    isdeleted = Column(Boolean, default=False, nullable=False)
    
    # Relationships - FIXED: Changed "roles" to "Role" (capitalized class name)
    roles = relationship("Role", secondary="menuitem_role", back_populates="menu_items")
    
    def __repr__(self):
        return f"<MenuItem(id={self.id}, text='{self.text}', route='{self.route}')>"