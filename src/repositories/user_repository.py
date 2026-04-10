"""
User repository for database operations.
Extends BaseRepository with user-specific queries.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User, AuthAuditLog
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository for User model operations.
    Inherits generic CRUD from BaseRepository.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with User model."""
        super().__init__(User, session)

    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            User instance or None if not found
        """
        return await self.get_one_by(username=username)

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: Email to look up

        Returns:
            User instance or None if not found
        """
        return await self.get_one_by(email=email)


class AuthAuditRepository:
    """
    Repository for authentication audit log operations.
    Records failed login attempts for security monitoring.
    """

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def log_failed_attempt(
        self,
        username: str,
        ip_address: str,
        failure_reason: str,
    ) -> AuthAuditLog:
        """
        Record a failed authentication attempt.

        Args:
            username: Username that was used in the attempt
            ip_address: IP address of the request
            failure_reason: Human-readable reason for failure

        Returns:
            Created AuthAuditLog instance
        """
        audit_log = AuthAuditLog(
            username=username,
            ip_address=ip_address,
            failure_reason=failure_reason,
        )
        self.session.add(audit_log)
        await self.session.flush()
        await self.session.refresh(audit_log)
        return audit_log

    async def count_recent_attempts(
        self,
        ip_address: str,
        window_seconds: int = 60,
    ) -> int:
        """
        Count recent login attempts from an IP address.

        Args:
            ip_address: IP address to check
            window_seconds: Time window in seconds (default 60)

        Returns:
            Number of attempts within the time window
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

        result = await self.session.execute(
            select(func.count(AuthAuditLog.id)).where(
                AuthAuditLog.ip_address == ip_address,
                AuthAuditLog.attempted_at >= cutoff_time,
            )
        )
        return result.scalar_one()
