# models/menu_role.py
from sqlalchemy import Column, Integer, ForeignKey, Table
from .base import Base

# Association table for many-to-many relationship between MenuItem and Role
menu_role = Table(
    "menuitem_role",
    Base.metadata,
    Column("menuitem_id", Integer, ForeignKey("menuitem.id"), primary_key=True),
    Column("roles_id", Integer, ForeignKey("roles.id"), primary_key=True),
    # Unique constraint on the combination of both columns
)