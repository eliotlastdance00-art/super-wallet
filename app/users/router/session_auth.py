from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.database import get_db
from app.core.outbox import OutboxRepository
from app.core.dependencies import get_current_user
from app.users.exception import (
    InvalidVerificationTokenError,
    PasswordResetTokenInvalidError,
)
from app.users.repository import (
    SessionRepository,
    UserRepository,
    VerificationTokenRepository,
)
from app.users.schemas.session_auth import (
    ForgotPasswordRequest,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionListResponse,
    SessionOut,
    VerifyEmailRequest,
)
from app.users.services.session_auth import (
    EmailVerificationService,
    PasswordResetService,
    SessionManagementService,
)

router = APIRouter()
sessions_router = APIRouter()


def _client_meta(request: Request) -> tuple[str, str | None]:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent")
    return ip, ua


# ---------------- Email verification ----------------


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    conn=Depends(get_db),
):
    ip, ua = _client_meta(request)
    service = EmailVerificationService(UserRepository(conn), OutboxRepository(conn))

    try:
        await service.verify_email(conn, body.token, ip, ua)
    except InvalidVerificationTokenError:
        return MessageResponse(
            message="Token nädogry ýa-da möhleti geçen. Täzeden ibermegi soraň."
        )

    return MessageResponse(message="Email tassyklandy.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    conn=Depends(get_db),
):
    ip, ua = _client_meta(request)
    service = EmailVerificationService(UserRepository(conn), OutboxRepository(conn))

    # Email ibermek indi Service+outbox içinde bolýar - router diňe
    # generic jogap berýär, üstünlikli/şowsuz bolanyna garamazdan.
    await service.resend_verification(conn, body.email, ip, ua)

    return MessageResponse(
        message="Eger bu email registered we tassyklanmadyk bolsa, link iberildi."
    )


# ---------------- Password reset ----------------


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    conn=Depends(get_db),
):
    ip, ua = _client_meta(request)
    service = PasswordResetService(
        UserRepository(conn),
        SessionRepository(conn),
        VerificationTokenRepository(conn),
        OutboxRepository(conn),
    )

    await service.forgot_password(conn, body.email, ip, ua)

    return MessageResponse(
        message="Eger bu email registered bolsa, parol täzelemek üçin link iberildi."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    conn=Depends(get_db),
):
    ip, ua = _client_meta(request)
    service = PasswordResetService(
        UserRepository(conn),
        SessionRepository(conn),
        VerificationTokenRepository(conn),
        OutboxRepository(conn),
    )

    try:
        await service.reset_password(conn, body.token, body.new_password, ip, ua)
    except PasswordResetTokenInvalidError:
        return MessageResponse(
            message="Token nädogry, möhleti geçen ýa-da eýýäm ulanylan."
        )

    return MessageResponse(message="Parol täzelendi. Ähli enjamlardan çykaryldyňyz.")


# ---------------- Session management ----------------


@sessions_router.get("", response_model=SessionListResponse)
async def list_sessions(
    conn=Depends(get_db),
    user_id: UUID = Depends(get_current_user),
):
    service = SessionManagementService(SessionRepository(conn))
    sessions = await service.list_sessions(conn, user_id)
    return SessionListResponse(sessions=[SessionOut(**s.__dict__) for s in sessions])


@sessions_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    request: Request,
    conn=Depends(get_db),
    user_id: UUID = Depends(get_current_user),
):
    ip, ua = _client_meta(request)
    service = SessionManagementService(SessionRepository(conn))
    await service.revoke_session(conn, user_id, session_id, ip, ua)
