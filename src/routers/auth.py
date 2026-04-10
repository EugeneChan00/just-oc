"""
Authentication router.
Provides /api/auth/login and /api/auth/refresh endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.repositories.user_repository import UserRepository, AuthAuditRepository
from src.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    ErrorResponse,
)
from src.services.auth_service import AuthService


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.
    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    """
    Dependency to get AuthService instance.

    Args:
        db: Database session

    Returns:
        Configured AuthService instance
    """
    user_repo = UserRepository(db)
    audit_repo = AuthAuditRepository(db)
    return AuthService(user_repo, audit_repo)


async def check_rate_limit(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Rate limiting dependency.
    Limits to RATE_LIMIT_ATTEMPTS per IP per RATE_LIMIT_WINDOW_SECONDS.

    Args:
        request: FastAPI request
        db: Database session

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    client_ip = get_client_ip(request)
    audit_repo = AuthAuditRepository(db)

    recent_count = await audit_repo.count_recent_attempts(
        ip_address=client_ip,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    if recent_count >= settings.RATE_LIMIT_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        200: {"description": "Successful authentication", "model": TokenResponse},
        401: {"description": "Invalid credentials", "model": ErrorResponse},
        422: {"description": "Validation error", "model": ErrorResponse},
        429: {"description": "Rate limit exceeded", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="User Login",
    description="""
Authenticate a user and return a JWT access token.

This endpoint:
- Validates the username and password against the database
- Returns a signed JWT token on success
- Records failed attempts in the audit log for security monitoring
- Is rate-limited to 5 attempts per IP per minute

The returned token should be included in the Authorization header as:
`Authorization: Bearer <token>`
    """,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "username": "john_doe",
                        "password": "securePassword123",
                    }
                }
            }
        }
    },
)
async def login(
    request: Request,
    login_data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate user with username and password.

    Args:
        request: FastAPI request (for IP extraction)
        login_data: Login credentials
        auth_service: Auth service instance
        db: Database session (for rate limiting)

    Returns:
        TokenResponse with JWT access token

    Raises:
        HTTPException 401: Invalid credentials
        HTTPException 429: Rate limit exceeded
    """
    # Check rate limit before processing
    await check_rate_limit(request, db)

    client_ip = get_client_ip(request)

    try:
        user, error = await auth_service.authenticate_user(
            username=login_data.username,
            password=login_data.password,
            ip_address=client_ip,
        )

        if error is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Create access token
        access_token = auth_service.create_access_token(
            user_id=user.id,
            username=user.username,
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected errors but don't expose details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred",
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        200: {"description": "Token refreshed successfully", "model": TokenResponse},
        401: {"description": "Invalid or expired token", "model": ErrorResponse},
        422: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    summary="Refresh Access Token",
    description="""
Refresh an existing valid JWT access token.

This endpoint:
- Accepts a valid JWT token
- Validates the token signature and expiration
- Returns a new token with a refreshed expiration window
- Does not invalidate the old token (token rotation not implemented)

The new token will have the same TTL as the original token.
    """,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    }
                }
            }
        }
    },
)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """
    Refresh an access token.

    Args:
        refresh_data: Contains the current valid token
        auth_service: Auth service instance

    Returns:
        TokenResponse with new JWT access token

    Raises:
        HTTPException 401: Invalid or expired token
    """
    try:
        new_token, error = await auth_service.refresh_token(refresh_data.token)

        if error is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        return TokenResponse(
            access_token=new_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected errors but don't expose details
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred",
        )
