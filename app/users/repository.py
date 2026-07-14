from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg


@dataclass
class UserRecord:
    id: UUID
    username: str
    email: str
    password_hash: str
    failed_login_count: int
    locked_until: datetime | None
    totp_enabled: bool
    totp_secret_encrypted: str | None


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
            INSERT INTO users (id, username, email, password_hash, created_at)
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
            SELECT id, username, email, password_hash, failed_login_count,
                    locked_until, totp_enabled, totp_secret_encrypted
            FROM users WHERE id = $1
            """,
            user_id,
        )
        return self._to_record(row) if row else None

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await self._conn.fetchrow(
            """
            SELECT id, username, email, password_hash, failed_login_count,
                    locked_until, totp_enabled, totp_secret_encrypted
            FROM users WHERE email = $1
            """,
            email,
        )
        return self._to_record(row) if row else None

    async def get_by_username(self, username: str) -> UserRecord | None:
        row = await self._conn.fetchrow(
            """
            SELECT id, username, email, password_hash, failed_login_count,
                    locked_until, totp_enabled, totp_secret_encrypted
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
            "UPDATE users SET password_hash = $2 WHERE id = $1",
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


@dataclass
class SessionRecord:
    id: UUID
    user_id: UUID
    refresh_token_hash: str
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
            revoked_at=row["revoked_at"],
            expires_at=row["expires_at"],
        )

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
            SELECT id, user_id, refresh_token_hash, revoked_at, expires_at
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
            SELECT id, user_id, refresh_token_hash, revoked_at, expires_at
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
        if  new_row is None:
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
            SELECT id, user_id, refresh_token_hash, revoked_at, expires_at
            FROM sessions
            WHERE user_id = $1 AND revoked_at IS NULL AND expires_at > now()
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [self._to_record(r) for r in rows]
