# app/config/security.py

"""
Security configuration for the application.
Contains password hashing, JWT settings, and other security-related configurations.
"""

import os
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import bcrypt
import jwt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Suppress bcrypt warnings
import warnings

warnings.filterwarnings("ignore", message=".*bcrypt version.*")

BCRYPT_ROUNDS = 12

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY environment variable is required. "
        'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Password policy configuration
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))

# Security headers configuration
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
}

# CORS Configuration (if needed)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")


class SecurityConfig:
    """Security configuration class with utility methods"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain password against a hashed password.
        IMPORTANT: This handles both direct bcrypt and SHA256-prehashed passwords.

        Args:
            plain_password: The plain text password to verify
            hashed_password: The hashed password to verify against

        Returns:
            bool: True if password matches, False otherwise
        """
        try:
            password_bytes = plain_password.encode("utf-8")
            # bcrypt only supports up to 72 bytes, pre-hash with sha256 to handle longer passwords
            if len(password_bytes) > 72:
                password_bytes = (
                    hashlib.sha256(password_bytes).hexdigest().encode("utf-8")
                )
            hashed_bytes = (
                hashed_password.encode("utf-8")
                if isinstance(hashed_password, str)
                else hashed_password
            )
            if bcrypt.checkpw(password_bytes, hashed_bytes):
                return True
        except Exception:
            pass

        # Fallback: try SHA256 pre-hashed verification
        try:
            sha256_hash = (
                hashlib.sha256(plain_password.encode("utf-8"))
                .hexdigest()
                .encode("utf-8")
            )
            hashed_bytes = (
                hashed_password.encode("utf-8")
                if isinstance(hashed_password, str)
                else hashed_password
            )
            if bcrypt.checkpw(sha256_hash, hashed_bytes):
                return True
        except Exception:
            pass

        return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Get password hash. Uses direct bcrypt hashing for compatibility.

        Args:
            password: Plain text password

        Returns:
            str: Hashed password
        """
        password_bytes = password.encode("utf-8")
        # bcrypt only supports up to 72 bytes, pre-hash with sha256 to handle longer passwords
        if len(password_bytes) > 72:
            password_bytes = hashlib.sha256(password_bytes).hexdigest().encode("utf-8")
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    @staticmethod
    def get_enhanced_password_hash(password: str) -> str:
        """
        Get enhanced password hash with SHA256 pre-hashing.
        Use this for new passwords to avoid bcrypt length limitations.

        Args:
            password: Plain text password

        Returns:
            str: Hashed password
        """
        # First hash with SHA256 (64 bytes, fixed length)
        sha256_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        # Then hash with bcrypt
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        return bcrypt.hashpw(sha256_hash.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def needs_rehash(hashed_password: str) -> bool:
        """
        Check if a hashed password needs rehashing.

        Args:
            hashed_password: Hashed password to check

        Returns:
            bool: True if password needs rehashing, False otherwise
        """
        # bcrypt direct does not have needs_update; return False as safe default
        return False

    @staticmethod
    def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
        """
        SIMPLIFIED: Validate password strength - only checks for minimum length.

        Args:
            password: Password to validate

        Returns:
            tuple: (is_valid: bool, error_message: Optional[str])
        """
        if len(password) < PASSWORD_MIN_LENGTH:
            return (
                False,
                f"Password must be at least {PASSWORD_MIN_LENGTH} characters long",
            )

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        return True, None

    @staticmethod
    def create_access_token(
        data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token.

        Args:
            data: Data to encode in the token
            expires_delta: Optional expiration time delta

        Returns:
            str: Encoded JWT token
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """
        Create JWT refresh token.

        Args:
            data: Data to encode in the token

        Returns:
            str: Encoded JWT refresh token
        """
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        Decode JWT token.

        Args:
            token: JWT token to decode

        Returns:
            Dict: Decoded token payload

        Raises:
            jwt.PyJWTError: If token is invalid or expired
        """
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


# Create singleton instance for easy import
security_config = SecurityConfig()

# Export pwd_context for backward compatibility
__all__ = [
    "pwd_context",
    "security_config",
    "SecurityConfig",
    "JWT_SECRET_KEY",
    "JWT_ALGORITHM",
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "JWT_REFRESH_TOKEN_EXPIRE_DAYS",
    "PASSWORD_MIN_LENGTH",
    "SECURITY_HEADERS",
    "ALLOWED_ORIGINS",
]
