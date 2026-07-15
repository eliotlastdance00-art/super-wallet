
from app.users.exception import InvalidRefreshTokenError,RefreshTokenInvalidReason
from fastapi import APIRouter, Depends, Request, Response
from app.users.dependencies import get_current_user
from app.core.database import get_db
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
    return RegisterService(UserRepository(conn))


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


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    conn=Depends(get_db),
    service: RegisterService = Depends(get_register_service),
):
    result = await service.execute(
        conn=conn,
        email=payload.email,
        username=payload.username,
        password=payload.password,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    # TODO: result.email_verification_token bilen email ugrat (EmailService)
    return RegisterResponse(user_id=result.user_id, email=result.email)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    conn=Depends(get_db),
    service: LoginService = Depends(get_login_service),
):
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


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    conn=Depends(get_db),
    service: LogoutService = Depends(get_logout_service),
    current_user=Depends(get_current_user),  # app/users/dependencies.py-dan
):
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


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    conn=Depends(get_db),
    service: RefreshService = Depends(get_refresh_service),
):
    

    refresh_token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise InvalidRefreshTokenError(reason=RefreshTokenInvalidReason.REVOKED)

    result = await service.execute(
        conn=conn,
        refresh_token=refresh_token,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(access_token=result.access_token)
