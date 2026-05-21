# app/services/user_resource_service.py

from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.log.log_config import get_logger
from app.schemas.user import UserDTO, UserDetailsDTO
from app.schemas.MenuItemDto import TagDto
from app.config.helper.password_helper import password_helper
from app.config.helper.time_helper import get_current_berlin_time

logger = get_logger("user_resource_service")


class UserResourceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── SQL constants ────────────────────────────────────────────────

    _USERS_BASE_QUERY = """
        SELECT
            u.id   AS id,
            CONCAT(u.firstname, ' ', u.lastname) AS name,
            u.username AS username,
            r.role     AS tags_name
        FROM users u
        LEFT JOIN roles r
            ON u.role_id = r.id AND r.is_deleted = false
        WHERE u.is_deleted = false
          AND u.username != 'bot'
    """

    _ALL_TAGS_QUERY = text(
        """
        SELECT id, role AS name
        FROM roles
        WHERE is_deleted = false AND role != 'bot'
    """
    )

    _USER_DETAILS_QUERY = text(
        """
        SELECT u.id, u.firstname, u.lastname, u.username,
               r.role AS rolle, u.role_id,
               (u.password IS NOT NULL AND u.password != '') AS passwordneeded
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id AND r.is_deleted = false
        WHERE u.id = :user_id AND u.is_deleted = false
    """
    )

    _USERNAME_EXISTS_QUERY = text(
        """
        SELECT id FROM users
        WHERE username = :username
          AND is_deleted = false
            AND (CAST(:exclude_id AS INTEGER) IS NULL OR id != :exclude_id)
    """
    )

    _INSERT_USER_QUERY = text(
        """
        INSERT INTO users (
            firstname, lastname, username,
            password, role_id, created_at, is_deleted, is_active
        )
        VALUES (
            :firstname, :lastname, :username,
            :password, :role_id, NOW(), false, true
        )
        RETURNING id
    """
    )

    _UPDATE_USER_QUERY = text(
        """
        UPDATE users
        SET firstname  = :firstname,
            lastname   = :lastname,
            username   = :username,
            role_id    = :role_id,
            updated_at = NOW()
        WHERE id = :user_id
    """
    )

    _UPDATE_USER_WITH_PASSWORD_QUERY = text(
        """
        UPDATE users
        SET firstname  = :firstname,
            lastname   = :lastname,
            username   = :username,
            password   = :password,
            role_id    = :role_id,
            updated_at = NOW()
        WHERE id = :user_id
    """
    )

    # ── Private helpers ──────────────────────────────────────────────

    async def _fetch_users(self, role_filter: Optional[str] = None) -> List[UserDTO]:
        """Fetch users, optionally filtered by role name."""
        where_extra = ""
        params: dict = {}
        if role_filter:
            where_extra = " AND r.role = :role_filter"
            params["role_filter"] = role_filter

        query = text(
            self._USERS_BASE_QUERY + where_extra + "\nORDER BY LOWER(u.username)"
        )
        result = await self.db.execute(query, params)

        return [
            UserDTO(
                id=row["id"],
                name=row["name"],
                username=row["username"],
                rolle=row["tags_name"] or "",
            )
            for row in result.mappings()
        ]

    async def _fetch_tags(self, is_admin: bool) -> List[TagDto]:
        """Fetch all role tags, hiding 'admin' for non-admin users."""
        result = await self.db.execute(self._ALL_TAGS_QUERY)
        tags = [TagDto(id=row[0], name=row[1], color=None) for row in result]
        if not is_admin:
            tags = [t for t in tags if t.name.lower() != "admin"]
        return tags

    async def _username_exists(
        self,
        username: str,
        exclude_id: Optional[int] = None,
    ) -> bool:
        """Check whether username is already taken, optionally excluding a user id."""
        result = await self.db.execute(
            self._USERNAME_EXISTS_QUERY,
            {"username": username.strip(), "exclude_id": exclude_id},
        )
        return result.fetchone() is not None

    # ── Public API ───────────────────────────────────────────────────

    async def get_users(self) -> List[UserDTO]:
        """Get all users with their role."""
        return await self._fetch_users()

    async def Get_All_Patient_Users(self) -> List[UserDTO]:
        """Get all patient users with their role."""
        return await self._fetch_users(role_filter="patient")

    # -----------------------------------------------------------------
    # Get user details by ID
    # -----------------------------------------------------------------
    async def get_user_details_by_id(
        self,
        user_id: int,
        is_admin: bool,
    ) -> UserDetailsDTO:
        """Get user details by ID including selected roles/tags."""
        try:
            await self.db.rollback()  # clear stale transaction state

            tags = await self._fetch_tags(is_admin)

            # New-user placeholder
            if user_id == -1:
                return UserDetailsDTO(
                    id=-1,
                    firstname="",
                    lastname="",
                    username="",
                    rolle="",
                    password=None,
                    passwordneeded=None,
                    is_user_exit=False,
                    is_password_wrong=False,
                    SelectedRollenIDs=[],
                    Tags=tags,
                )

            result = await self.db.execute(
                self._USER_DETAILS_QUERY, {"user_id": user_id}
            )
            user_row = result.mappings().fetchone()
            if not user_row:
                raise ValueError(f"User with id {user_id} not found")

            selected_role_ids = [user_row["role_id"]] if user_row["role_id"] else []

            return UserDetailsDTO(
                id=user_row["id"],
                firstname=user_row["firstname"],
                lastname=user_row["lastname"],
                username=user_row["username"],
                rolle=user_row["rolle"] or "",
                password=None,
                passwordneeded=user_row["passwordneeded"],
                is_user_exit=False,
                is_password_wrong=False,
                SelectedRollenIDs=selected_role_ids,
                Tags=tags,
            )

        except Exception as e:
            logger.error(
                "Error fetching user details for id=%s: %s", user_id, e, exc_info=True
            )
            await self.db.rollback()
            raise

    # -----------------------------------------------------------------
    # Save / update user
    # -----------------------------------------------------------------
    async def save_user_details(self, user_dto: UserDetailsDTO) -> UserDetailsDTO:
        """Create or update a user."""
        result = UserDetailsDTO(
            id=0,
            firstname=user_dto.firstname,
            lastname=user_dto.lastname,
            username=user_dto.username,
            SelectedRollenIDs=user_dto.selectedRollenIDs,
            Tags=user_dto.Tags,
        )

        try:
            logger.info(
                "save_user_details called for user_id=%s username=%s",
                user_dto.id,
                user_dto.username,
            )

            if not user_dto.selectedRollenIDs:
                logger.warning("No role IDs provided")
                return result

            hashed_password = (
                await password_helper.get_password_hash(user_dto.password)
                if user_dto.password
                else None
            )

            is_new = not user_dto.id or user_dto.id == -1

            # Check for duplicate username (shared for create & update)
            exclude_id = None if is_new else user_dto.id
            if await self._username_exists(user_dto.username, exclude_id):
                logger.warning("Username already exists: %s", user_dto.username)
                result.username = "Benutzername existiert bereits"
                result.id = 0
                return result

            if is_new:
                return await self._create_user(user_dto, hashed_password, result)
            return await self._update_user(user_dto, hashed_password, result)

        except IntegrityError:
            await self.db.rollback()
            logger.error(
                "IntegrityError in save_user_details for user_id=%s", user_dto.id
            )
            result.username = "Benutzername existiert bereits"
            result.id = 0
            return result
        except Exception as e:
            await self.db.rollback()
            logger.error("Error saving user details: %s", e, exc_info=True)
            raise

    async def _create_user(
        self,
        user_dto: UserDetailsDTO,
        hashed_password: Optional[str],
        result: UserDetailsDTO,
    ) -> UserDetailsDTO:
        """Insert a new user row."""
        try:
            logger.info(
                "Creating user: username=%s role_id=%s",
                user_dto.username.strip(),
                user_dto.selectedRollenIDs[0],
            )
            insert_result = await self.db.execute(
                self._INSERT_USER_QUERY,
                {
                    "firstname": user_dto.firstname,
                    "lastname": user_dto.lastname,
                    "username": user_dto.username.strip(),
                    "password": hashed_password,
                    "role_id": user_dto.selectedRollenIDs[0],
                },
            )
            new_id = insert_result.scalar()
            await self.db.commit()
            logger.info("New user created with id=%s", new_id)
            result.id = int(new_id) if new_id is not None else 0
            return result

        except IntegrityError:
            await self.db.rollback()
            logger.error("IntegrityError creating user %s", user_dto.username)
            result.username = "Benutzername existiert bereits"
            result.id = 0
            return result

    async def _update_user(
        self,
        user_dto: UserDetailsDTO,
        hashed_password: Optional[str],
        result: UserDetailsDTO,
    ) -> UserDetailsDTO:
        """Update an existing user row."""
        params = {
            "firstname": user_dto.firstname,
            "lastname": user_dto.lastname,
            "username": user_dto.username.strip(),
            "role_id": user_dto.selectedRollenIDs[0],
            "user_id": user_dto.id,
        }

        if hashed_password:
            params["password"] = hashed_password
            query = self._UPDATE_USER_WITH_PASSWORD_QUERY
        else:
            query = self._UPDATE_USER_QUERY

        logger.info(
            "Updating user_id=%s fields=firstname,lastname,username,role_id%s",
            user_dto.id,
            ",password" if hashed_password else "",
        )
        await self.db.execute(query, params)
        await self.db.commit()
        logger.info("User updated: id=%s", user_dto.id)
        result.id = user_dto.id
        return result

    # -----------------------------------------------------------------
    # Delete user (soft delete)
    # -----------------------------------------------------------------
    async def delete_user_by_id(self, user_id: int) -> bool:
        """Soft-delete user by ID."""
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT username, firstname, lastname
                    FROM users
                    WHERE id = :user_id AND is_deleted = false
                """
                ),
                {"user_id": user_id},
            )
            user = result.fetchone()
            if not user:
                return False

            timestamp = get_current_berlin_time().strftime("%d%m%Y %H:%M:%S")

            await self.db.execute(
                text(
                    """
                    UPDATE users
                    SET username    = :username,
                        firstname  = :firstname,
                        lastname   = '',
                        is_deleted = true,
                        updated_at = NOW()
                    WHERE id = :user_id
                """
                ),
                {
                    "username": f"Deleted- {user[0]} {timestamp}",
                    "firstname": f"Deleted- {user[1]} {user[2]} {timestamp}",
                    "user_id": user_id,
                },
            )
            await self.db.commit()
            logger.info("Soft-deleted user id=%s", user_id)
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error("Error deleting user id=%s: %s", user_id, e)
            raise
