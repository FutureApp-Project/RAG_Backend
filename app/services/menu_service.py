from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from models.menu import MenuItem
from models.role import Role
from schemas.menu import MenuItemCreate, MenuItemUpdate
from typing import List, Optional
from sqlalchemy.exc import IntegrityError


class MenuService:
    def __init__(self, db: Session):
        self.db = db

    def get_menu_item_by_id(self, menu_id: int) -> Optional[MenuItem]:
        return (
            self.db.query(MenuItem)
            .filter(MenuItem.id == menu_id, ~MenuItem.isdeleted)
            .first()
        )

    def get_all_menu_items(self, include_roles: bool = True) -> List[MenuItem]:
        query = (
            self.db.query(MenuItem)
            .filter(~MenuItem.isdeleted)
            .order_by(MenuItem.item_order, MenuItem.text)
        )

        if include_roles:
            query = query.options(joinedload(MenuItem.roles))

        return query.all()

    def get_menu_items_by_role(self, role_id: int) -> List[MenuItem]:
        return (
            self.db.query(MenuItem)
            .join(MenuItem.roles)
            .filter(
                Role.id == role_id,
                ~MenuItem.isdeleted,
                ~Role.is_deleted,
                Role.is_active,
            )
            .order_by(MenuItem.item_order, MenuItem.text)
            .all()
        )

    def create_menu_item(self, menu_data: MenuItemCreate) -> MenuItem:
        # Check if menu item already exists
        existing = (
            self.db.query(MenuItem)
            .filter(MenuItem.text == menu_data.text, ~MenuItem.isdeleted)
            .first()
        )
        if existing:
            raise ValueError(f"Menu item '{menu_data.text}' already exists")

        db_menu = MenuItem(
            text=menu_data.text,
            route=menu_data.route,
            icon=menu_data.icon,
            item_order=menu_data.item_order,
        )

        try:
            self.db.add(db_menu)
            self.db.flush()  # Get ID without committing

            # Add role associations
            if menu_data.role_ids:
                roles = (
                    self.db.query(Role)
                    .filter(
                        Role.id.in_(menu_data.role_ids),
                        ~Role.is_deleted,
                        Role.is_active,
                    )
                    .all()
                )

                for role in roles:
                    db_menu.roles.append(role)

            self.db.commit()
            self.db.refresh(db_menu)
            return db_menu

        except IntegrityError:
            self.db.rollback()
            raise ValueError("Failed to create menu item")

    def update_menu_item(
        self, menu_id: int, menu_data: MenuItemUpdate
    ) -> Optional[MenuItem]:
        db_menu = self.get_menu_item_by_id(menu_id)
        if not db_menu:
            return None

        update_data = menu_data.dict(exclude_unset=True)

        # Update basic fields
        if "text" in update_data:
            # Check if new text already exists
            existing = (
                self.db.query(MenuItem)
                .filter(
                    MenuItem.text == update_data["text"],
                    MenuItem.id != menu_id,
                    ~MenuItem.isdeleted,
                )
                .first()
            )
            if existing:
                raise ValueError(f"Menu item '{update_data['text']}' already exists")
            db_menu.text = update_data["text"]

        if "route" in update_data:
            db_menu.route = update_data["route"]

        if "icon" in update_data:
            db_menu.icon = update_data["icon"]

        if "item_order" in update_data:
            db_menu.item_order = update_data["item_order"]

        if "isdeleted" in update_data:
            db_menu.isdeleted = update_data["isdeleted"]

        # Update role associations if provided
        if "role_ids" in update_data and update_data["role_ids"] is not None:
            # Clear existing roles
            db_menu.roles.clear()

            # Add new roles
            if update_data["role_ids"]:
                roles = (
                    self.db.query(Role)
                    .filter(
                        Role.id.in_(update_data["role_ids"]),
                        ~Role.is_deleted,
                        Role.is_active,
                    )
                    .all()
                )

                for role in roles:
                    db_menu.roles.append(role)

        try:
            self.db.commit()
            self.db.refresh(db_menu)
            return db_menu

        except IntegrityError:
            self.db.rollback()
            raise ValueError("Failed to update menu item")

    def delete_menu_item(self, menu_id: int, soft_delete: bool = True) -> bool:
        db_menu = self.get_menu_item_by_id(menu_id)
        if not db_menu:
            return False

        if soft_delete:
            setattr(db_menu, "isdeleted", True)
        else:
            self.db.delete(db_menu)

        self.db.commit()
        return True

    def update_menu_roles(
        self, menu_id: int, role_ids: List[int]
    ) -> Optional[MenuItem]:
        db_menu = self.get_menu_item_by_id(menu_id)
        if not db_menu:
            return None

        # Clear existing roles
        db_menu.roles.clear()

        # Add new roles
        if role_ids:
            roles = (
                self.db.query(Role)
                .filter(
                    Role.id.in_(role_ids),
                    ~Role.is_deleted,
                    Role.is_active,
                )
                .all()
            )

            for role in roles:
                db_menu.roles.append(role)

        try:
            self.db.commit()
            self.db.refresh(db_menu)
            return db_menu

        except IntegrityError:
            self.db.rollback()
            raise ValueError("Failed to update menu roles")
