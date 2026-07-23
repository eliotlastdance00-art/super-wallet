from dataclasses import dataclass
from uuid import UUID

from app.core import security as core_secure
from app.core.audit import log_audit_event
from app.core.outbox import OutboxRepository
from app.users import security
from app.users.exception import (
    InvalidVerificationTokenError,
    PasswordResetTokenInvalidError,
    SessionNotFoundError,
)
from app.users.repository import (
    SessionRepository,
    UserRepository,
    VerificationTokenRepository,
)


class EmailVerificationService:
    """
    JWT-based (stateless) - DB-de token ýazgysy ÝOK.
    """

    def __init__(self, repo: UserRepository, outbox_repo: OutboxRepository):
        self._repo = repo
        self._outbox_repo = outbox_repo

    async def verify_email(
        self, conn, token: str, ip_address: str, user_agent: str | None
    ) -> None:
        user_id = security.decode_purpose_token(token, expected_purpose="verify_email")
        if user_id is None:
            raise InvalidVerificationTokenError()

        async with conn.transaction():
            user = await self._repo.get_by_id(user_id)
            if user is None:
                raise InvalidVerificationTokenError()

            if user.email_verified:
                return  # idempotent - eýýäm tassyklanan

            await self._repo.set_email_verified(user.id)
            await log_audit_event(
                conn, user.id, "email_verified", ip_address, user_agent
            )

    async def resend_verification(
        self, conn, email: str, ip_address: str, user_agent: str | None
    ) -> None:
        """
        Return None hemişe - caller (router) email iberilip-iberilmändigini
        bilmeli DÄL, enumeration-dan gaça durmak üçin. Email ibermek
        indi ÖZI şu Service-iň içinde, outbox arkaly bolýar - router
        ony asla bilmeýär.
        """
        async with conn.transaction():
            user = await self._repo.get_by_email(email)
            if user is None or user.email_verified:
                await log_audit_event(
                    conn,
                    user.id if user else None,
                    "resend_verification_noop",
                    ip_address,
                    user_agent,
                )
                return

            token = security.create_email_verification_token(user.id)

            await self._outbox_repo.enqueue(
                event_type="email",
                payload={
                    "template": "email_verification",
                    "to": user.email,
                    "token": token,
                },
            )
            await log_audit_event(
                conn, user.id, "verification_resent", ip_address, user_agent
            )


class PasswordResetService:
    def __init__(
        self,
        repo: UserRepository,
        session_repo: SessionRepository,
        token_repo: VerificationTokenRepository,
        outbox_repo: OutboxRepository,
    ):
        self._repo = repo
        self._session_repo = session_repo
        self._token_repo = token_repo
        self._outbox_repo = outbox_repo

    async def forgot_password(
        self, conn, email: str, ip_address: str, user_agent: str | None
    ) -> None:
        async with conn.transaction():
            user = await self._repo.get_by_email(email)
            if user is None:
                await log_audit_event(
                    conn, None, "forgot_password_noop", ip_address, user_agent
                )
                return

            await self._token_repo.invalidate_all_for_user(
                user.id, type_="password_reset"
            )

            raw_token = core_secure.generate_secure_random_string()
            token_hash = security.hash_opaque_token(raw_token)
            await self._token_repo.create(
                user_id=user.id,
                token_hash=token_hash,
                type="password_reset",
                expires_at=security.password_reset_token_expiry(),
                ip_address=ip_address,
            )

            await self._outbox_repo.enqueue(
                event_type="email",
                payload={
                    "template": "password_reset",
                    "to": user.email,
                    "token": raw_token,
                },
            )
            await log_audit_event(
                conn, user.id, "password_reset_requested", ip_address, user_agent
            )

    async def reset_password(
        self,
        conn,
        raw_token: str,
        new_password: str,
        ip_address: str,
        user_agent: str | None,
    ) -> None:
        token_hash = security.hash_opaque_token(raw_token)

        async with conn.transaction():
            record = await self._token_repo.get_valid_by_hash(
                token_hash, type="password_reset"
            )
            if record is None:
                raise PasswordResetTokenInvalidError()

            new_hash = security.hash_password(new_password)
            await self._repo.update_password_hash(record.user_id, new_hash)
            await self._token_repo.mark_used(record.id)

            await self._session_repo.revoke_all_for_user(
                record.user_id, reason="password_reset"
            )

            await log_audit_event(
                conn,
                record.user_id,
                "password_reset_completed",
                ip_address,
                user_agent,
            )


@dataclass
class SessionSummary:
    id: UUID
    device_info: str | None
    ip_address: str | None
    created_at: object
    expires_at: object


class SessionManagementService:
    def __init__(self, session_repo: SessionRepository):
        self._session_repo = session_repo

    async def list_sessions(self, conn, user_id: UUID) -> list[SessionSummary]:
        records = await self._session_repo.list_active_for_user(user_id)
        return [
            SessionSummary(
                id=r.id,
                device_info=r.device_info,
                ip_address=r.ip_address,
                created_at=r.created_at,
                expires_at=r.expires_at,
            )
            for r in records
        ]

    async def revoke_session(
        self,
        conn,
        user_id: UUID,
        session_id: UUID,
        ip_address: str,
        user_agent: str | None,
    ) -> None:
        async with conn.transaction():
            session = await self._session_repo.get_by_id(session_id)

            if session is None or session.user_id != user_id:
                raise SessionNotFoundError("session_not_found")

            await self._session_repo.revoke(session.id, reason="user_revoked")
            await log_audit_event(
                conn,
                user_id,
                "session_revoked",
                ip_address,
                user_agent,
                metadata={"session_id": str(session.id)},
            )
