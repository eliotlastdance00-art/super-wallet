from fastapi import APIRouter, Depends, Request, Response, status

from app.core.database import get_db
from app.core.outbox import OutboxRepository
from app.core.dependencies import get_current_user
from app.users.exception import InvalidRefreshTokenError, RefreshTokenInvalidReason
from app.users.repository import SessionRepository, UserRepository
from app.users.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from app.users.services.auth import (
    LoginService,
    LogoutService,
    RefreshService,
    RegisterService,
)

router = APIRouter()


# =====================================================================
# Dependency factory-ler - her endpoint özüne gerek repository-leri
# şu ýerden alýar. Bulary aýratyn faýla (dependencies.py) çykarmak hem
# bolar, ýöne häzir router-e ýakyn saklamak - "haýsy service haýsy
# repo bilen gurulýar" diýen zady bir ýerde görmek üçin amatly.
# =====================================================================


def get_register_service(conn=Depends(get_db)) -> RegisterService:
    return RegisterService(UserRepository(conn), OutboxRepository(conn))


def get_login_service(conn=Depends(get_db)) -> LoginService:
    return LoginService(UserRepository(conn), SessionRepository(conn))


def get_logout_service(conn=Depends(get_db)) -> LogoutService:
    return LogoutService(SessionRepository(conn))


def get_refresh_service(conn=Depends(get_db)) -> RefreshService:
    return RefreshService(UserRepository(conn), SessionRepository(conn))


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


# =====================================================================
# Refresh token - httpOnly cookie arkaly saklanýar (body-de DÄL).
# Näme üçin? XSS bilen JS-den okalmaz ýaly. Access token bolsa
# response body-de - client (frontend) ony memory-de saklaýar, uzak
# möhlet localStorage-a ýazmaýar (localStorage XSS-e açyk).
# =====================================================================

_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_COOKIE_MAX_AGE = (
    30 * 24 * 60 * 60
)  # 30 gün, security.py-daky TTL bilen gabat gelmeli


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,  # diňe HTTPS üstünden ugradylýar
        samesite="strict",  # CSRF-e garşy esasy gorag
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path="/auth",  # diňe /auth/* endpoint-lerine ugradylýar, bütin sайta däl
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    responses={
        409: {"description": "Email or username already exists"},
        422: {
            "description": "Validation error (weak password, invalid email format, etc.)"
        },
    },
)
async def register(
    payload: RegisterRequest,
    request: Request,
    conn=Depends(get_db),
    service: RegisterService = Depends(get_register_service),
) -> RegisterResponse:
    """
    Registers a new user account.

    - **email**: must be unique, validated format
    - **username**: must be unique
    - **password**: hashed with argon2 before storage, never stored in plaintext

    Returns the newly created user's ID and email.
    """
    result = await service.execute(
        conn=conn,
        email=payload.email,
        username=payload.username,
        password=payload.password,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return RegisterResponse(user_id=result.user_id, email=result.email)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User login",
    responses={
        401: {"description": "Invalid email or password"},
        403: {"description": "Account locked or disabled"},
        422: {"description": "Invalid or missing TOTP code"},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    conn=Depends(get_db),
    service: LoginService = Depends(get_login_service),
) -> TokenResponse:
    """
    Authenticates user and issues tokens.

    - **email / password**: standard credentials
    - **totp_code**: required if 2FA is enabled on the account

    Access token is returned in the response body.
    Refresh token is set as an HttpOnly cookie (not exposed in response body for XSS protection).
    """
    result = await service.execute(
        conn=conn,
        email=payload.email,
        password=payload.password,
        totp_code=payload.totp_code,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(access_token=result.access_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User logout",
    responses={
        401: {"description": "Not authenticated"},
    },
)
async def logout(
    request: Request,
    response: Response,
    conn=Depends(get_db),
    service: LogoutService = Depends(get_logout_service),
    current_user=Depends(get_current_user),
) -> None:
    """
    Logs out the current user.

    Revokes the refresh token (if present) on the server side and clears
    the refresh token cookie. Access token remains valid until its own
    expiry — this endpoint does not blacklist access tokens.
    """
    refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if refresh_token:
        await service.execute(
            conn=conn,
            user_id=current_user.id,
            refresh_token=refresh_token,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    response.delete_cookie(_REFRESH_COOKIE_NAME, path="/auth")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    responses={
        401: {"description": "Refresh token missing, expired, revoked, or invalid"},
    },
)
async def refresh(
    request: Request,
    response: Response,
    conn=Depends(get_db),
    service: RefreshService = Depends(get_refresh_service),
) -> TokenResponse:
    """
    Issues a new access token using the refresh token stored in the HttpOnly cookie.

    Implements refresh token rotation: the old refresh token is invalidated
    and a new one is issued and set as the cookie. If the presented token
    is missing, expired, already used, or revoked, authentication fails
    and the client must re-authenticate via `/auth/login`.
    """
    refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise InvalidRefreshTokenError(reason=RefreshTokenInvalidReason.MISSING)

    result = await service.execute(
        conn=conn,
        refresh_token=refresh_token,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(access_token=result.access_token)
