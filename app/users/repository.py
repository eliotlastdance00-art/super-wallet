from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg


@dataclass
class UserRecord:
    id: UUID
    username: str
    email: str
    hashed_password: str
    failed_login_count: int
    locked_until: datetime | None
    totp_enabled: bool
    totp_secret_encrypted: str | None
    email_verified: bool


class UserRepository:
    """
    'users' tablisasy bilen işleýän ÝEKE-TÄK ýer. Islendik feature
    (login, register, password reset, admin) şu class arkaly geçýär -
    bu, "bir aggregate = bir repository" DDD kadasy.
    """

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    def _to_record(self, row) -> UserRecord:
        return UserRecord(**dict(row))

    async def create(self, username: str, email: str, hashed_password: str) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO users (id, username, email, hashed_password, created_at)
            VALUES (gen_random_uuid(), $1, $2, $3, now())
            RETURNING id
            """,
            username,
            email,
            hashed_password,
        )
        if row is None:
            raise RuntimeError("Failed to insert user; no row returned.")

        return row["id"]

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        row = await self._conn.fetchrow(
            """
            SELECT id, username, email, hashed_password , failed_login_count,
                    locked_until, totp_enabled, totp_secret_encrypted,email_verified 
            FROM users WHERE id = $1
            """,
            user_id,
        )
        return self._to_record(row) if row else None

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await self._conn.fetchrow(
            """
            SELECT id, username, email, hashed_password, failed_login_count,
                    locked_until, totp_enabled, totp_secret_encrypted,email_verified 
            FROM users WHERE email = $1
            """,
            email,
        )
        return self._to_record(row) if row else None

    async def get_by_username(self, username: str) -> UserRecord | None:
        row = await self._conn.fetchrow(
            """
            SELECT id, username, email, hashed_password, failed_login_count,
                    locked_until, totp_enabled, totp_secret_encrypted,email_verified 
            FROM users WHERE username = $1
            """,
            username,
        )
        return self._to_record(row) if row else None

    async def update_password_hash(self, user_id: UUID, new_hash: str) -> None:
        """
        Iki ýerden çagyrylýar: (1) needs_rehash - argon2 parametri täzelenende,
        (2) password reset/change flow-da. Ikisinde-de diňe hash üýtgeýär,
        şonuň üçin bir ýönekeý UPDATE ýeterlik.
        """
        await self._conn.execute(
            "UPDATE users SET hashed_password  = $2 WHERE id = $1",
            user_id,
            new_hash,
        )

    async def increment_failed_login(
        self, user_id: UUID, new_count: int, lockout_until: datetime | None
    ) -> None:
        await self._conn.execute(
            "UPDATE users SET failed_login_count = $2, locked_until = $3 WHERE id = $1",
            user_id,
            new_count,
            lockout_until,
        )

    async def reset_failed_login_count(self, user_id: UUID) -> None:
        await self._conn.execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE id = $1",
            user_id,
        )

    async def set_totp_secret(
        self, user_id: UUID, encrypted_secret: str, enabled: bool
    ) -> None:
        await self._conn.execute(
            "UPDATE users SET totp_secret_encrypted = $2, totp_enabled = $3 WHERE id = $1",
            user_id,
            encrypted_secret,
            enabled,
        )

    async def set_email_verified(self, user_id: UUID) -> None:
        """
        Näme üçin aýratyn metod, update_password_hash ýaly umumy UPDATE
        etmän: sebäbi bu 'domain event' ýaly bir amal - diňe bir column
        üýtgänok, bu ulanyjynyň hasabynyň "trust" derejesiniň üýtgänini
        aňladýar. Aýratyn ada eýe bolmagy, service gatlagynda okalanda
        näme bolup geçýänini aýdyň edýär (intent-revealing name).
        """
        await self._conn.execute(
            "UPDATE users SET email_verified = true WHERE id = $1",
            user_id,
        )


@dataclass
class SessionRecord:
    id: UUID
    user_id: UUID
    refresh_token_hash: str
    device_info: str | None
    ip_address: str | None
    created_at: datetime
    revoked_at: datetime | None
    expires_at: datetime


class SessionRepository:
    """
    'sessions' tablisasy - user_id bilen baglanyşykly bolsa-da, aýratyn
    aggregate (öz lifecycle-i bar: döredilýär, rotate edilýär, revoke
    edilýär - bularyň hiç biri 'users' tablisasyna göni degmeýär).
    """

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    def _to_record(self, row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            refresh_token_hash=row["refresh_token_hash"],
            device_info=row["device_info"],
            ip_address=str(row["ip_address"]) if row["ip_address"] else None,
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            expires_at=row["expires_at"],
        )

    async def get_by_id(self, session_id: UUID) -> SessionRecord | None:
        row = await self._conn.fetchrow(
            """
            SELECT id, user_id, refresh_token_hash, device_info, ip_address,
                    created_at, revoked_at, expires_at
            FROM sessions WHERE id = $1
            """,
            session_id,
        )
        return self._to_record(row) if row else None

    async def create(
        self,
        user_id: UUID,
        refresh_token_hash: str,
        device_info: str | None,
        ip_address: str,
        expires_at: datetime,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO sessions (id, user_id, refresh_token_hash, device_info, ip_address, expires_at, created_at)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, now())
            RETURNING id
            """,
            user_id,
            refresh_token_hash,
            device_info,
            ip_address,
            expires_at,
        )
        if row is None:
            raise RuntimeError("Failed to insert user; no row returned.")

        return row["id"]

    async def get_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        """Diňe ÄHLI (revoke edilmedik) sessiýany tapýar - login/refresh üçin ulanylýar."""
        row = await self._conn.fetchrow(
            """
            SELECT id, user_id, refresh_token_hash, revoked_at, expires_at,device_info, ip_address, created_at
            FROM sessions
            WHERE refresh_token_hash = $1 AND revoked_at IS NULL
            """,
            token_hash,
        )
        return self._to_record(row) if row else None

    async def get_by_used_token_hash(self, token_hash: str) -> SessionRecord | None:
        """
        Diňe 'rotated' sebäbi bilen revoke edilen sessiýany gözleýär -
        ýagny bu token BIR GEZEK KANUNY ulanylan, indi ikinji gezek
        görünse, munuň özi - reuse attack alamaty (RefreshService-de
        şuny ulanýarys).
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, user_id, refresh_token_hash, revoked_at, expires_at,device_info, ip_address, created_at
            FROM sessions
            WHERE refresh_token_hash = $1 AND revoked_reason = 'rotated'
            """,
            token_hash,
        )
        return self._to_record(row) if row else None

    async def revoke(self, session_id: UUID, reason: str = "logout") -> None:
        await self._conn.execute(
            "UPDATE sessions SET revoked_at = now(), revoked_reason = $2 WHERE id = $1",
            session_id,
            reason,
        )

    async def revoke_all_for_user(
        self, user_id: UUID, reason: str = "security_action"
    ) -> None:
        """
        'hemme enjamdan çyk' we 'reuse detected -> ähli sessiýany öldür'
        ikisi-de şu metody ulanýar, diňe 'reason' tapawutly - audit
        log-da haýsy sebäp bilen ýatyrylandygyny yzarlamak üçin gerek.
        """
        await self._conn.execute(
            "UPDATE sessions SET revoked_at = now(), revoked_reason = $2 WHERE user_id = $1 AND revoked_at IS NULL",
            user_id,
            reason,
        )

    async def rotate(
        self,
        old_session_id: UUID,
        user_id: UUID,
        new_token_hash: str,
        device_info: str | None,
        ip_address: str,
        expires_at: datetime,
    ) -> UUID:
        """
        Köne sessiýany 'rotated' diýip belleýär (ÖÇÜRMEÝÄR - reuse
        detection üçin ýazgy galmaly), täze sessiýany döredýär, we
        ikisiniň arasyndaky baglanyşygy (replaced_by_session_id) sakla.

        Näme üçin ikisi bir metodda? Sebäbi bular ATOMIK bolmaly -
        eger köne rewoke bolup, täzesi döremese (ýa-da tersine),
        ulanyjy "session ýitirer" ýaly ýagdaý bolar. Bu, transaction-yň
        özi (caller tarapyndan açylan) muny gorasa-da, iki operasiýany
        bir ýerde jemlemek "bular hemişe bile bolmaly" diýen niýeti
        koddan-da aýdyň görkezýär.
        """
        new_row = await self._conn.fetchrow(
            """
            INSERT INTO sessions (id, user_id, refresh_token_hash, device_info, ip_address, expires_at, created_at)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, now())
            RETURNING id
            """,
            user_id,
            new_token_hash,
            device_info,
            ip_address,
            expires_at,
        )
        if new_row is None:
            raise RuntimeError("Failed to insert new session; no ID returned.")
        new_id = new_row["id"]

        await self._conn.execute(
            """
            UPDATE sessions
            SET revoked_at = now(), revoked_reason = 'rotated', replaced_by_session_id = $2
            WHERE id = $1
            """,
            old_session_id,
            new_id,
        )
        return new_id

    async def list_active_for_user(self, user_id: UUID) -> list[SessionRecord]:
        """Geljekde SessionService-däki 'GET /users/me/sessions' üçin gerek bolar."""
        rows = await self._conn.fetch(
            """
            SELECT id, user_id, refresh_token_hash, revoked_at, expires_at,device_info, ip_address, created_at
            FROM sessions
            WHERE user_id = $1 AND revoked_at IS NULL AND expires_at > now()
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [self._to_record(r) for r in rows]


@dataclass
class VerificationTokenRecord:
    id: UUID
    user_id: UUID
    token_hash: str
    type: str
    expires_at: datetime
    used_at: datetime | None


class VerificationTokenRepository:
    """
    email_verify we password_reset ikisi-de şu bir repository-den
    geçýär - sebäbi CRUD-y edil meňzeş (token döret, tap, "ulanyldy"
    diýip belle), diňe 'type' tapawutly. Iki aýry repository ýazmak
    diňe kod gaýtalanmasyny (duplication) döreder.
    """

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    def _to_record(self, row) -> VerificationTokenRecord:
        return VerificationTokenRecord(**dict(row))

    async def create(
        self,
        user_id: UUID,
        token_hash: str,
        type: str,
        expires_at: datetime,
        ip_address: str | None = None,
    ) -> UUID:
        row = await self._conn.fetchrow(
            """
            INSERT INTO verification_tokens
            (user_id,token_hash,type,expires_at,ip_address,created_at)
            VALUES ($1,$2,$3,$4,$5,now()
            RETURNING id)
            """,
            user_id,
            token_hash,
            type,
            expires_at,
            ip_address,
        )
        if row is None:
            raise RuntimeError("Failed to insert verification token; no row returned.")
        return row["id"]

    async def get_valid_by_hash(
        self, token_hash: str, type: str
    ) -> VerificationTokenRecord | None:
        """
        Diňe entäk ulanylmadyk (used_at IS NULL) we möhleti geçmedik
        token-i tapýar. 'type' barlagy - eger kimdir biri email-verify
        token-ini password-reset endpoint-e iberip synanyşsa, bu ony
        blokirleýär (bir token diňe öz maksady üçin işlemeli).
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, user_id, token_hash, type, expires_at, used_at
            FROM verification_tokens
            WHERE token_hash = $1 AND type = $2
                AND used_at IS NULL AND expires_at > now()
            """,
            token_hash,
            type,
        )
        return self._to_record(row) if row else None

    async def mark_used(self, token_id: UUID) -> None:
        await self._conn.execute(
            "UPDATE verification_tokens SET used_at = now() WHERE id = $1",
            token_id,
        )

    async def invalidate_all_for_user(self, user_id: UUID, type_: str) -> None:
        """
        resend-verification / forgot-password gaýtadan soralanda çagyrylýar:
        öňki ulanylmadyk token-leri "öli" edýär, sebäbi bir ulanyjyda
        diňe iň soňky iberilen link işlemeli - öňki e-mail-lerdäki
        linkler entäk "valid" görünse, bu attack surface-i giňeldýär.
        """
        await self._conn.execute(
            """
            UPDATE verification_tokens
            SET used_at = now()
            WHERE user_id = $1 AND type = $2 AND used_at IS NULL
            """,
            user_id,
            type_,
        )
