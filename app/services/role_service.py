from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.role import Role
from app.schemas.role import RoleCreate, RoleUpdate, RoleEnum, TagDto
from typing import List, Optional
from sqlalchemy.exc import IntegrityError
from app.config.log.log_config import get_logger

logger = get_logger("role_service")


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_role_by_id(self, role_id: int) -> Optional[Role]:
        logger.info(f"Fetching role with ID {role_id}")
        result = await self.db.execute(
            select(Role).where(Role.id == role_id, Role.is_deleted == False)
        )
        return result.scalars().first()

    async def get_role_by_name(self, role_name: str) -> Optional[Role]:
        result = await self.db.execute(
            select(Role).where(Role.role == role_name, Role.is_deleted == False)
        )
        return result.scalars().first()

    async def get_all_roles(self) -> List[TagDto]:
        result = await self.db.execute(
            select(Role)
            .where(and_(Role.is_deleted == False, Role.role != "bot"))
            .order_by(Role.role)
        )
        roles = result.scalars().all()
        # i want to see roles in the log for debugging
        role_payload = [
            {
                "id": role.id,
                "role": role.role,
                "name": role.role,
                "is_active": role.is_active,
                "is_deleted": role.is_deleted,
            }
            for role in roles
        ]
        logger.info("Fetched roles from database: %s", role_payload)
        return roles

    async def create_role(self, role_data: RoleCreate) -> Role:
        existing_role = await self.get_role_by_name(role_data.role)
        if existing_role:
            if existing_role.is_deleted:
                existing_role.is_deleted = False
                existing_role.is_active = role_data.is_active
                await self.db.commit()
                await self.db.refresh(existing_role)
                return existing_role
            raise ValueError(f"Role '{role_data.role}' already exists")

        db_role = Role(role=role_data.role, is_active=role_data.is_active)
        try:
            self.db.add(db_role)
            await self.db.commit()
            await self.db.refresh(db_role)
            return db_role
        except IntegrityError:
            await self.db.rollback()
            raise ValueError(f"Role '{role_data.role}' already exists")

    async def update_role(self, role_id: int, role_data: RoleUpdate) -> Optional[Role]:
        db_role = await self.get_role_by_id(role_id)
        if not db_role:
            return None

        update_data = role_data.dict(exclude_unset=True)

        if "role" in update_data and update_data["role"] != db_role.role:
            existing = await self.get_role_by_name(update_data["role"])
            if existing and existing.id != role_id:
                raise ValueError(f"Role '{update_data['role']}' already exists")
            db_role.role = update_data["role"]

        if "is_active" in update_data:
            db_role.is_active = update_data["is_active"]

        try:
            await self.db.commit()
            await self.db.refresh(db_role)
            return db_role
        except IntegrityError:
            await self.db.rollback()
            raise ValueError("Role update failed")

    async def delete_role(self, role_id: int, soft_delete: bool = True) -> bool:
        logger.info(f"Deleting role with ID {role_id}, soft_delete={soft_delete}")
        db_role = await self.get_role_by_id(role_id)
        if not db_role:
            logger.info(f"Role with ID {role_id} not found")
            return False

        # if db_role.role in [RoleEnum.ADMIN, RoleEnum.BOT]:
        #     raise ValueError("Cannot delete system roles")

        if soft_delete:
            db_role.is_deleted = True
            db_role.is_active = False
        else:
            if db_role.users:
                logger.error(f"Role ID {role_id} is assigned to users; cannot delete.")
                raise ValueError("Cannot delete role that is assigned to users")
            await self.db.delete(db_role)

        await self.db.commit()
        logger.info(f"Deleted role with ID {role_id}, soft_delete={soft_delete}")
        return True
