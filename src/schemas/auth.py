"""
Pydantic schemas for authentication.
Defines request/response models with validation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    """Request schema for login endpoint."""

    username: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User's username",
        examples=["john_doe"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User's password",
        examples=["securePassword123"],
    )

    @field_validator("username", "password")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip leading/trailing whitespace from inputs."""
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "john_doe",
                    "password": "securePassword123",
                }
            ]
        }
    }


class TokenResponse(BaseModel):
    """Response schema for successful authentication."""

    access_token: str = Field(
        ...,
        description="JWT access token",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Token expiration time in seconds",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "expires_in": 1800,
                }
            ]
        }
    }


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh."""

    token: str = Field(
        ...,
        description="Valid JWT token to refresh",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    detail: str = Field(
        ...,
        description="Error message",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": "Invalid credentials",
                }
            ]
        }
    }


class ValidationErrorResponse(BaseModel):
    """Response schema for validation errors (422)."""

    detail: list = Field(
        ...,
        description="List of validation errors",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": [
                        {
                            "loc": ["body", "username"],
                            "msg": "field required",
                            "type": "value_error.missing",
                        }
                    ]
                }
            ]
        }
    }
