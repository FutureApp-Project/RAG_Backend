# app/services/menu_resource_service.py

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select, text, delete, insert
from app.models.menu import MenuItem
from app.models.menu_role import menu_role
from app.models.role import Role
from app.schemas.menu import MenuItemDTO, MenuItemOrderDTO
from app.config.log.log_config import get_logger
from app.config.helper.time_helper import get_current_berlin_time

logger = get_logger("menu_resource_service")


class MenuResourceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_menu_details(self, menu_item_dto: MenuItemDTO) -> MenuItemDTO:
        """
        Save or update menu details

        Returns:
            MenuItemDTO with Id set to:
            - New menu ID on success
            - -1 if menu not found during update
            - -12121 if duplicate menu name exists
        """
        result = MenuItemDTO(
            id=None,
            text=menu_item_dto.text if menu_item_dto.text else " ",
            route=None,
            icon=None,
            itemOrder=0,
            selectedRollenIDs=[],
            rolle=None,
            tags=[],
        )

        try:
            # Determine if operation is addition (Id = -1 or None) or modification
            if menu_item_dto.id is None or menu_item_dto.id == -1:
                logger.info("Creating new menu item")

                # For addition: Check if a menu with the same name already exists
                stmt = select(MenuItem).where(
                    func.trim(func.lower(MenuItem.text))
                    == func.trim(func.lower(menu_item_dto.text)),
                    MenuItem.isdeleted == False,
                )
                result_exists = await self.db.execute(stmt)
                existing_menu = result_exists.scalar_one_or_none()

                if existing_menu:
                    # If duplicate menu name exists, return specific ID (-12121)
                    logger.warning(
                        f"Duplicate menu name '{menu_item_dto.text}' found for add"
                    )
                    result.id = -12121
                    return result

                # Get the highest item_order from existing menu items
                stmt_max_order = select(func.max(MenuItem.item_order)).where(
                    MenuItem.isdeleted == False
                )
                result_max_order = await self.db.execute(stmt_max_order)
                max_item_order = result_max_order.scalar() or 0

                # Get the highest ID from existing menu items
                stmt_max_id = select(func.max(MenuItem.id))
                result_max_id = await self.db.execute(stmt_max_id)
                max_id = result_max_id.scalar() or 0

                # Create new menu
                add_menu = MenuItem(
                    id=max_id + 1,
                    text=menu_item_dto.text.strip(),
                    route=f"/{menu_item_dto.text.strip()}",
                    icon=menu_item_dto.icon.strip() if menu_item_dto.icon else None,
                    isdeleted=False,
                    item_order=max_item_order + 1,
                )

                self.db.add(add_menu)
                await self.db.flush()

                # Add selected roles
                if menu_item_dto.selectedRollenIDs:
                    for role_id in menu_item_dto.selectedRollenIDs:
                        await self.db.execute(
                            insert(menu_role).values(
                                menuitem_id=add_menu.id, roles_id=role_id
                            )
                        )

                await self.db.commit()

                # Return the new menu's ID
                result.id = add_menu.id
                result.text = add_menu.text
                result.route = add_menu.route
                result.icon = add_menu.icon
                result.itemOrder = add_menu.item_order
                result.selectedRollenIDs = menu_item_dto.selectedRollenIDs
            else:
                logger.info(f"Updating menu with ID: {menu_item_dto.id}")
                logger.info(
                    f"Update data - text: '{menu_item_dto.text}', icon: '{menu_item_dto.icon}', selectedRollenIDs: {menu_item_dto.selectedRollenIDs}"
                )

                # For modification: Check if menu exists
                stmt = select(MenuItem).where(
                    MenuItem.id == menu_item_dto.id,
                    MenuItem.isdeleted == False,  # Fixed: Use == instead of 'not'
                )
                result_exists = await self.db.execute(stmt)
                existing_menu = result_exists.scalar_one_or_none()

                if not existing_menu:
                    logger.warning(
                        f"Menu with ID {menu_item_dto.id} not found for update"
                    )
                    result.id = -1
                    return result

                logger.info(
                    f"Found existing menu - current text: '{existing_menu.text}', icon: '{existing_menu.icon}'"
                )

                # Check for duplicate menu names during modification
                stmt_duplicate = select(MenuItem).where(
                    func.trim(func.lower(MenuItem.text))
                    == func.trim(func.lower(menu_item_dto.text)),
                    MenuItem.id != menu_item_dto.id,
                    MenuItem.isdeleted == False,  # Fixed: Use == instead of 'not'
                )
                result_duplicate = await self.db.execute(stmt_duplicate)
                duplicate_menu = result_duplicate.scalar_one_or_none()

                if duplicate_menu:
                    logger.warning(
                        f"Duplicate menu name '{menu_item_dto.text}' found for ID {duplicate_menu.id}"
                    )
                    result.id = -12121
                    return result

                # Update existing menu details
                old_text = existing_menu.text
                old_icon = existing_menu.icon
                existing_menu.text = menu_item_dto.text.strip()
                existing_menu.icon = (
                    menu_item_dto.icon.strip() if menu_item_dto.icon else None
                )
                logger.info(
                    f"Updated menu fields - text: '{old_text}' -> '{existing_menu.text}', icon: '{old_icon}' -> '{existing_menu.icon}'"
                )

                # Remove existing role associations
                logger.info(
                    f"Removing existing role associations for menu ID {menu_item_dto.id}"
                )
                delete_result = await self.db.execute(
                    delete(menu_role).where(menu_role.c.menuitem_id == menu_item_dto.id)
                )
                logger.info(f"Deleted {delete_result.rowcount} role associations")

                # Add new role associations
                if (
                    menu_item_dto.selectedRollenIDs
                    and len(menu_item_dto.selectedRollenIDs) > 0
                ):
                    logger.info(
                        f"Adding {len(menu_item_dto.selectedRollenIDs)} new role associations: {menu_item_dto.selectedRollenIDs}"
                    )
                    for role_id in menu_item_dto.selectedRollenIDs:
                        await self.db.execute(
                            insert(menu_role).values(
                                menuitem_id=menu_item_dto.id, roles_id=role_id
                            )
                        )
                    logger.info("Role associations added successfully")
                else:
                    logger.info("No role associations to add")

                logger.info("Committing transaction...")
                await self.db.commit()
                logger.info("Transaction committed successfully")

                # Return the updated menu's ID
                result.id = existing_menu.id
                result.text = existing_menu.text
                result.route = existing_menu.route
                result.icon = existing_menu.icon
                result.itemOrder = existing_menu.item_order
                result.selectedRollenIDs = menu_item_dto.selectedRollenIDs

                logger.info(f"Update completed successfully for menu ID {result.id}")

        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Database integrity error: {str(e)}")
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error saving menu details: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        return result

    async def delete_menu_by_id(self, menu_id: int) -> bool:
        """
        Delete (soft delete) a menu by its ID
        """
        try:
            logger.info(f"Deleting menu with ID: {menu_id}")
            stmt = select(MenuItem).where(
                MenuItem.id == menu_id, MenuItem.isdeleted == False
            )
            result = await self.db.execute(stmt)
            menu_item = result.scalar_one_or_none()

            if not menu_item:
                return False

            # Mark as deleted and append deletion timestamp
            today_date = get_current_berlin_time().strftime("%d%m%Y %H:%M:%S")
            menu_item.text = f"Deleted- {menu_item.text} {today_date}"
            menu_item.isdeleted = True

            await self.db.commit()
            return True

        except Exception as e:
            await self.db.rollback()
            logger.info(f"Error deleting menu by ID {menu_id}: {str(e)}")
            raise

    async def get_menu_data(self) -> List[MenuItemDTO]:
        """
        Get all active (non-deleted) menus with their tags/roles
        Using direct query
        """
        try:
            # Direct SQL query
            query = text(
                """
                SELECT 
                    m.id,
                    m.text,
                    m.route,
                    m.icon,
                    m.item_order,
                    COALESCE(STRING_AGG(r.role, ', ' ORDER BY r.id), '') as tags_name
                FROM 
                    menuitem m
                LEFT JOIN 
                    menuitem_role mr ON m.id = mr.menuitem_id
                LEFT JOIN 
                    roles r ON mr.roles_id = r.id
                WHERE 
                    m.isdeleted = false
                GROUP BY 
                    m.id, m.text, m.route, m.icon, m.item_order
                ORDER BY 
                    COALESCE(m.item_order, 0), m.id
            """
            )

            result = await self.db.execute(query)
            rows = result.fetchall()

            menus = []
            for row in rows:
                row_dict = dict(row._mapping)

                menu_item = MenuItemDTO(
                    id=row_dict["id"],
                    text=row_dict["text"],
                    route=row_dict["route"],
                    icon=row_dict["icon"],
                    itemOrder=row_dict["item_order"],
                    selectedRollenIDs=[],
                    rolle=row_dict["tags_name"] if row_dict["tags_name"] else None,
                    tags=[],  # Initialize empty tags list
                )
                menus.append(menu_item)

            return menus

        except Exception as e:
            logger.info(f"Error fetching menu data: {str(e)}")
            import traceback

            logger.info(f"Traceback: {traceback.format_exc()}")
            raise

    async def get_menu_details_by_id(self, menu_id: int) -> MenuItemDTO:
        """
        Get menu details by ID including selected roles and all tags
        """
        try:
            menu_item = None
            if menu_id != -1:
                stmt = select(MenuItem).where(
                    MenuItem.id == menu_id, not MenuItem.isdeleted
                )
                result = await self.db.execute(stmt)
                menu_item = result.scalar_one_or_none()

            # Get selected role IDs for this menu
            selected_role_ids = []
            if menu_id != -1:
                stmt_roles = select(menu_role.c.roles_id).where(
                    menu_role.c.menuitem_id == menu_id
                )
                result_roles = await self.db.execute(stmt_roles)
                selected_role_ids = [row[0] for row in result_roles.fetchall()]

            # Get all active tags (roles)
            # Get all active tags (roles) excluding 'bot' and 'patient'
            stmt_tags = select(Role).where(
                Role.is_deleted == False,
                Role.role.not_in(["bot", "patient"]),  # Exclude specific role names
            )
            logger.info(f"Fetching tags with query: {stmt_tags}")
            result_tags = await self.db.execute(stmt_tags)
            tags = result_tags.scalars().all()

            # Map roles to DTO format
            tags_list = [{"id": tag.id, "name": tag.role} for tag in tags]
            logger.info(f"Fetched {len(tags_list)} tags for menu ID: {menu_id}")
            menu_item_dto = MenuItemDTO(
                id=menu_id,
                text=menu_item.text if menu_item else " ",
                route=menu_item.route if menu_item else None,
                icon=menu_item.icon if menu_item else None,
                itemOrder=menu_item.item_order if menu_item else 0,
                selectedRollenIDs=selected_role_ids,
                rolle=None,
                tags=tags_list,  # Add tags to the DTO
            )

            return menu_item_dto

        except Exception as e:
            logger.info(f"Error fetching menu details by ID {menu_id}: {str(e)}")
            raise

    async def reorder_menu_items(self, menu_items: List[MenuItemOrderDTO]) -> bool:
        """
        Reorder menu items based on provided order
        """
        try:
            logger.info(
                "Reordering %s menu items: %s",
                len(menu_items),
                [item.id for item in menu_items],
            )
            logger.info(
                "Reorder payload (id->order): %s",
                [(item.id, item.itemOrder) for item in menu_items],
            )
            # Fetch all relevant menu items
            menu_item_ids = [item.id for item in menu_items]
            stmt = select(MenuItem).where(
                MenuItem.id.in_(menu_item_ids), MenuItem.isdeleted == False
            )
            result = await self.db.execute(stmt)
            db_menu_items = result.scalars().all()

            # Create a dictionary for quick lookup
            menu_dict = {item.id: item for item in db_menu_items}

            for menu_item_dto in menu_items:
                db_menu_item = menu_dict.get(menu_item_dto.id)
                if db_menu_item:
                    logger.info(
                        "Updating menu ID %s item_order: %s -> %s",
                        db_menu_item.id,
                        db_menu_item.item_order,
                        menu_item_dto.itemOrder,
                    )
                    db_menu_item.item_order = menu_item_dto.itemOrder

            await self.db.commit()
            logger.info("Reorder commit completed")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.info(f"Error reordering menu items: {str(e)}")
            return False
