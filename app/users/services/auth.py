from dataclasses import dataclass
from uuid import UUID

from app.core.audit import log_audit_event
from app.users import security
from app.users.exception import (
    AccountLockedError,
    EmailAlreadyExistsError,
    InvalidRefreshTokenError,
    LoginError,
    RefreshTokenInvalidReason,
    SessionExpiredError,
    SessionNotFoundError,
    TotpRequiredError,
    UsernameAlreadyExistsError,
)
from app.users.repository import SessionRepository, UserRepository


@dataclass
class RegisterResult:
    user_id: UUID
    email: str
    email_verification_token: str


class RegisterService:
    """Use-case: täze ulanyjy hasabyny döretmek."""

    def __init__(self, repo: UserRepository):
        self._repo = repo

    async def execute(
        self,
        conn,
        email: str,
        username: str,
        password: str,
        ip_address: str,
        user_agent: str | None,
    ) -> RegisterResult:
        async with conn.transaction():
            await self._ensure_email_and_username_free(
                conn, email, username, ip_address, user_agent
            )

            password_hash = security.hash_password(password)
            user_id = await self._repo.create(
                username=username, email=email, hashed_password=password_hash
            )

            verification_token = security.create_email_verification_token(user_id)

            await log_audit_event(
                conn,
                user_id,
                "user_registered",
                ip_address,
                user_agent,
                metadata={"email": email, "username": username},
            )

            return RegisterResult(
                user_id=user_id,
                email=email,
                email_verification_token=verification_token,
            )

    async def _ensure_email_and_username_free(
        self, conn, email: str, username: str, ip_address: str, user_agent: str | None
    ) -> None:
        """
        Iki barlagy aýratyn funksiýa etdim, sebäbi "haýsy sebäp bilen
        şowsuz boldy" diýen audit metadata-sy tapawutly bolmaly - bu,
        indiki debugging-de "köp adam email bilenmi ýa username bilen
        collision edýär" diýen statistika üçin gymmatly.
        """
        existing_email = await self._repo.get_by_email(email)
        if existing_email is not None:
            await log_audit_event(
                conn,
                None,
                "register_failed",
                ip_address,
                user_agent,
                metadata={"reason": "duplicate_email"},
            )
            raise EmailAlreadyExistsError("registration_failed")

        existing_username = await self._repo.get_by_username(username)
        if existing_username is not None:
            await log_audit_event(
                conn,
                None,
                "register_failed",
                ip_address,
                user_agent,
                metadata={"reason": "duplicate_username"},
            )
            raise UsernameAlreadyExistsError("registration_failed")


@dataclass
class LoginResult:
    access_token: str
    refresh_token: str


class LoginService:
    """Use-case: email+parol (+2FA) bilen girmek, session döretmek."""

    def __init__(self, repo: UserRepository, session_repo: SessionRepository):
        self._repo = repo
        self._session_repo = session_repo

    async def execute(
        self,
        conn,
        email: str,
        password: str,
        totp_code: str | None,
        ip_address: str,
        user_agent: str |None
    ) -> LoginResult:
        async with conn.transaction():
            user = await self._repo.get_by_email(email)
            if user is None:
                await log_audit_event(
                    conn,
                    None,
                    "login_failed",
                    ip_address,
                    user_agent,
                    metadata={"reason": "no_such_user"},
                )
                raise LoginError(email=email)

            self._ensure_not_locked(user)

            if not security.verify_password(password, user.hashed_password):
                await self._register_failed_attempt(conn, user, ip_address, user_agent)
                raise LoginError(email=email)

            # Parol dogry - eger köne hash parametrleri bilen hash-lanan bolsa, täzele.
            # Muny diňe şu ýerde edip bolýar, sebäbi plaintext parol diňe şu pursat elde.
            if security.needs_rehash(user.hashed_password):
                new_hash = security.hash_password(password)
                await self._repo.update_password_hash(user.id, new_hash)

            if user.totp_enabled:
                self._ensure_totp_valid(user, totp_code)

            await self._repo.reset_failed_login_count(user.id)
            await log_audit_event(
                conn, user.id, "login_success", ip_address, user_agent
            )

            return await self._issue_tokens(conn, user, ip_address, user_agent)

    def _ensure_not_locked(self, user) -> None:
        from datetime import datetime, timezone

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise AccountLockedError(locked_until=user.locked_until, failed_attempts=5)

    async def _register_failed_attempt(
        self, conn, user, ip_address, user_agent
    ) -> None:
        new_count = user.failed_login_count + 1
        lockout_until = security.compute_lockout(new_count)
        await self._repo.increment_failed_login(user.id, new_count, lockout_until)
        await log_audit_event(
            conn,
            user.id,
            "login_failed",
            ip_address,
            user_agent,
            metadata={"reason": "wrong_password", "attempt": new_count},
        )

    def _ensure_totp_valid(self, user, totp_code: str | None) -> None:
        if not totp_code:
            raise TotpRequiredError(user_id=str(user.id))
        raw_secret = security.decrypt_totp_secret(user.totp_secret_encrypted)
        if raw_secret is None or not security.verify_totp_code(raw_secret, totp_code):
            raise TotpRequiredError(user_id=str(user.id))

    async def _issue_tokens(
        self, conn, user, ip_address: str, user_agent: str | None
    ) -> LoginResult:
        access_token = security.create_access_token(user.id)
        refresh_token = security.generate_refresh_token()

        await self._session_repo.create(
            user_id=user.id,
            refresh_token_hash=security.hash_refresh_token(refresh_token),
            device_info=user_agent,
            ip_address=ip_address,
            expires_at=security.refresh_token_expiry(),
        )
        return LoginResult(access_token=access_token, refresh_token=refresh_token)


@dataclass
class RefreshResult:
    access_token: str
    refresh_token: str


class RefreshService:
    """
    Use-case: refresh token bilen täze access token (we ROTATE edilen
    täze refresh token) almak.

    Näme üçin "rotation" gerek (köne refresh token ulanylandan soň
    ýatyrylýar, täzesi berilýär), diňe access token täzelenmeýär?
    Sebäbi "refresh token reuse detection" diýen pattern: eger biri
    ogurlanan köne refresh tokeni ulanjak bolsa (asyl eýesi eýýäm
    täzesini alan bolsa), bu - "token replay attack" alamaty. Muny
    aňlaýan badyna, şol ulanyjynyň BÄHBIR sessiýalaryny ýatyrmak gerek.
    """

    def __init__(self, repo: UserRepository, session_repo: SessionRepository):
        self._repo = repo
        self._session_repo = session_repo

    async def execute(
        self,
        conn,
        refresh_token: str,
        ip_address: str,
        user_agent: str | None
    ) -> RefreshResult:
        token_hash = security.hash_refresh_token(refresh_token)

        async with conn.transaction():
            session = await self._session_repo.get_by_token_hash(token_hash)

            if session is None:
                # Bu ýerde "session ýok" diýmek iki many bildirip biler:
                # 1) token asla bolmandy (nädogry/ýasama)
                # 2) token eýýäm bir gezek ulanylyp, rotate edilipdi (reuse!)
                # Ikinji ýagdaýy tapmak üçin, "used_token_hashes" diýen
                # aýratyn gysga-ömürli tablisa/Redis-de yzarlamak bolar -
                # häzir muny SessionRepository-ň "get_by_used_token_hash"
                # metody bilen barlaýarys (aşakda repository-de goşarys).
                await self._handle_possible_reuse(
                    conn, token_hash, ip_address, user_agent
                )

                raise InvalidRefreshTokenError(reason=RefreshTokenInvalidReason.REVOKED)

            if session.revoked_at is not None or session.expires_at < _now():
                raise SessionExpiredError(
                    session_id=str(session.id), expired_at=session.expires_at
                )

            user = await self._repo.get_by_id(session.user_id)
            if user is None:
                raise SessionExpiredError(
                    session_id=str(session.id), expired_at=session.expires_at
                )

            if user.locked_until and user.locked_until > _now():
                raise AccountLockedError(
                    locked_until=user.locked_until, failed_attempts=5
                )

            # --- Rotation: köne session-y ýatyr, täzesini döret ---
            new_refresh_token = security.generate_refresh_token()
            new_hash = security.hash_refresh_token(new_refresh_token)

            await self._session_repo.rotate(
                old_session_id=session.id,
                user_id=user.id,
                new_token_hash=new_hash,
                device_info=user_agent,
                ip_address=ip_address,
                expires_at=security.refresh_token_expiry(),
            )

            new_access_token = security.create_access_token(user.id)

            await log_audit_event(
                conn,
                user.id,
                "token_refreshed",
                ip_address,
                user_agent,
                metadata={"old_session_id": str(session.id)},
            )

            return RefreshResult(
                access_token=new_access_token, refresh_token=new_refresh_token
            )

    async def _handle_possible_reuse(
        self, conn, token_hash, ip_address, user_agent
    ) -> None:
        reused_session = await self._session_repo.get_by_used_token_hash(token_hash)
        if reused_session is not None:
            # HÜJÜM ALAMATY: eýýäm bir gezek ulanylan (rotate edilen) tokeni
            # gaýtadan ulanjak boldular - şol ulanyjynyň BÄHBIR sessiýalaryny ýatyr.
            await self._session_repo.revoke_all_for_user(reused_session.user_id)
            await log_audit_event(
                conn,
                reused_session.user_id,
                "refresh_token_reuse_detected",
                ip_address,
                user_agent,
                metadata={"session_id": str(reused_session.id)},
            )


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


class LogoutService:
    """
    Use-case: bir session-y (refresh token) revoke etmek.

    Diňe SHOL BIR enjamdan çykmak (single-session logout) - "hemme
    enjamdan çyk" aýratyn use-case bolar (SessionService-de, sebäbi ol
    "session management" feature-iniň bir bölegi, "auth" däl).
    """

    def __init__(self, session_repo: SessionRepository):
        self._session_repo = session_repo

    async def execute( 
        self,
        conn,
        user_id: UUID,
        refresh_token: str,
        ip_address: str,
        user_agent: str | None
    ) -> None:
        token_hash = security.hash_refresh_token(refresh_token)

        async with conn.transaction():
            session = await self._session_repo.get_by_token_hash(token_hash)

            # Bilgeşleýin "session tapylmady" bilen "session başga
            # user-e degişli" ýagdaýlaryny BIR HABAR bilen jogaplaýarys -
            # eger tapawutlandyrsak, hüjümçä "bu token başga birine
            # degişli eken" diýen maglumat syzdyrylan bolar (IDOR-a
            # meňzeş enumeration howpy).
            if session is None or session.user_id != user_id:
                raise SessionNotFoundError("session_not_found")

            await self._session_repo.revoke(session.id)
            await log_audit_event(
                conn,
                user_id,
                "logout",
                ip_address,
                user_agent,
                metadata={"session_id": str(session.id)},
            )
