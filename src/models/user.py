"""
User SQLAlchemy model and AuthAuditLog model.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
from sqlalchemy.sql import func

from src.core.database import Base


class User(Base):
    """
    User model for authentication.
    Stores user credentials and account information.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"


class AuthAuditLog(Base):
    """
    Audit log for authentication attempts.
    Records failed login attempts for security monitoring.
    """

    __tablename__ = "auth_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False, index=True)  # IPv6 max length
    failure_reason = Column(Text, nullable=False)
    attempted_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Composite index for querying by IP and time range
    __table_args__ = (
        Index("ix_auth_audit_log_ip_attempted", "ip_address", "attempted_at"),
    )

    def __repr__(self) -> str:
        return f"<AuthAuditLog(id={self.id}, username='{self.username}', ip='{self.ip_address}')>"
