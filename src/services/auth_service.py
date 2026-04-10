"""
Authentication service.
Handles password hashing, JWT token creation and verification.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
from jose import JWTError, jwt

from src.core.config import settings
from src.models.user import User
from src.repositories.user_repository import UserRepository, AuthAuditRepository


class AuthService:
    """
    Service for authentication operations.
    Handles password verification, JWT creation and validation.
    """

    def __init__(
        self, user_repository: UserRepository, audit_repository: AuthAuditRepository
    ):
        """
        Initialize auth service.

        Args:
            user_repository: User repository instance
            audit_repository: Auth audit repository instance
        """
        self.user_repository = user_repository
        self.audit_repository = audit_repository

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Stored hash to verify against

        Returns:
            True if password matches, False otherwise
        """
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)

    @staticmethod
    def create_access_token(
        user_id: int,
        username: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create a JWT access token.

        Args:
            user_id: User's ID to include in token
            username: Username to include in token
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        expire = datetime.now(timezone.utc) + expires_delta
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }

        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return encoded_jwt

    def decode_token(self, token: str) -> Tuple[Optional[dict], Optional[str]]:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Tuple of (payload dict, error message).
            If successful, error is None.
            If failed, payload is None.
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            return payload, None
        except JWTError as e:
            return None, str(e)

    async def authenticate_user(
        self,
        username: str,
        password: str,
        ip_address: str,
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        Authenticate a user with username and password.

        Args:
            username: Username to authenticate
            password: Password to verify
            ip_address: IP address for audit logging

        Returns:
            Tuple of (User if authenticated, None) or (None, error message)
        """
        # Look up user
        user = await self.user_repository.get_by_username(username)

        if user is None:
            # Log failed attempt - user not found
            await self.audit_repository.log_failed_attempt(
                username=username,
                ip_address=ip_address,
                failure_reason="User not found",
            )
            return None, "Invalid credentials"

        if not user.is_active:
            # Log failed attempt - user inactive
            await self.audit_repository.log_failed_attempt(
                username=username,
                ip_address=ip_address,
                failure_reason="User account is inactive",
            )
            return None, "Invalid credentials"

        # Verify password
        if not self.verify_password(password, user.hashed_password):
            # Log failed attempt - wrong password
            await self.audit_repository.log_failed_attempt(
                username=username,
                ip_address=ip_address,
                failure_reason="Invalid password",
            )
            return None, "Invalid credentials"

        return user, None

    async def refresh_token(self, token: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Refresh an access token.

        Args:
            token: Current valid JWT token

        Returns:
            Tuple of (new token if successful, error message if failed)
        """
        payload, error = self.decode_token(token)

        if error is not None:
            return None, "Invalid or expired token"

        user_id = payload.get("sub")
        username = payload.get("username")

        if user_id is None or username is None:
            return None, "Invalid token payload"

        # Verify user still exists and is active
        user = await self.user_repository.get_by_id(int(user_id))

        if user is None or not user.is_active:
            return None, "Invalid or expired token"

        # Create new token
        new_token = self.create_access_token(
            user_id=user.id,
            username=user.username,
        )

        return new_token, None
