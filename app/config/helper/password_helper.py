# app/helpers/password_helper.py
"""
Async password hashing and verification helper.
Uses the common security configuration from app.config.security.
"""

import asyncio
from typing import Tuple, Optional
from app.config.security import security_config


class PasswordHelper:
    """Async password hashing and verification helper"""

    @staticmethod
    async def get_password_hash(password: str) -> str:
        """
        Hash a password asynchronously using security_config

        Args:
            password: Plain text password (any length/format)

        Returns:
            Hashed password string
        """
        return await asyncio.to_thread(security_config.get_password_hash, password)

    @staticmethod
    async def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash asynchronously

        Args:
            plain_password: Plain text password to verify
            hashed_password: Hashed password to verify against

        Returns:
            True if password matches, False otherwise
        """
        try:
            return await asyncio.to_thread(
                security_config.verify_password, plain_password, hashed_password
            )
        except Exception:
            return False

    @staticmethod
    async def needs_rehash(hashed_password: str) -> bool:
        """
        Check if a hashed password needs rehashing

        Args:
            hashed_password: Hashed password to check

        Returns:
            True if password needs rehashing, False otherwise
        """
        return await asyncio.to_thread(security_config.needs_rehash, hashed_password)

    @staticmethod
    async def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
        """
        Validate password strength asynchronously

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return await asyncio.to_thread(
            security_config.validate_password_strength, password
        )


# Create singleton instance
password_helper = PasswordHelper()
