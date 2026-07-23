from dataclasses import dataclass
from uuid import UUID

import asyncpg

from app.core.audit import log_audit_event
from app.core.outbox import OutboxRepository
from app.users.exception import (
    EmailAlreadyExistsError,
    IncorrectCurrentPasswordError,
    SamePasswordError,
    UserAlreadyDeactivatedError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from app.users.repository import UserRepository
from app.users.security import hash_password, verify_password


@dataclass(frozen=True)
class ProfileUpdateFields:
    """Router-dan gelen, exclude_unset bilen süzülen 'ne üýtgär' konteýneri."""

    username: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class RequestContext:
    """
    Her mutating operasiýa audit üçin şu ikisini talap edýär.
    Aýratyn dataclass edilmegi sebäbi: 4 metodyň hersinde
    (ip, user_agent) diýip iki param gaýtalamak ýerine, bir ýerden
    geçirmek - router-de-de Depends() bilen aňsat ýygnalýar.
    """

    ip_address: str | None
    user_agent: str | None


class ProfileService:
    """
    'users' bounded context-iniň profile amallary. Her mutating
    operasiýa ÜÇ zady bir transaction-yň içinde ätomik edýär:
    1) DB üýtgeşmesi (repo)
    2) audit_logs ýazgysy (compliance - "kim, näme, haçan")
    3) outbox_events ýazgysy (worker muny alyp reaksiýa bildirer -
        mysal: password_changed -> ähli session-lary revoke et)

    Outbox transaction içinde ýazylýar (dual-write problemasyny çözýär -
    DB üýtgeşi-de, event-de bile ýa-da ikisi-de ýok bolar), audit_logs-y-da
    şol transaction-a goşýarys, sebäbi audit ýazgysyz mutation bolmaly däl.
    """

    def __init__(
        self,
        conn: asyncpg.Connection,
        user_repo: UserRepository,
        outbox_repo: OutboxRepository,
    ) -> None:
        self._conn = conn
        self._user_repo = user_repo
        self._outbox = outbox_repo

    async def get_profile(self, user_id: UUID):
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    async def update_profile(
        self, user_id: UUID, fields: ProfileUpdateFields, ctx: RequestContext
    ) -> None:
        update_data = {
            k: v
            for k, v in {"username": fields.username, "email": fields.email}.items()
            if v is not None
        }
        if not update_data:
            return

        async with self._conn.transaction():
            try:
                await self._user_repo.update_profile(user_id, **update_data)
            except asyncpg.UniqueViolationError as e:
                constraint = getattr(e, "constraint_name", None)
                if constraint == "users_email_key":
                    assert fields.email is not None
                    raise EmailAlreadyExistsError(email=fields.email) from e
                if constraint == "users_username_key":
                    assert fields.username is not None
                    raise UsernameAlreadyExistsError(username=fields.username) from e
                raise

            await log_audit_event(
                self._conn,
                user_id=user_id,
                event_type="profile_updated",
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
                metadata={"fields": list(update_data.keys())},
            )
            await self._outbox.enqueue(
                "user.profile_updated",
                {"user_id": str(user_id), "fields": list(update_data.keys())},
            )

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        ctx: RequestContext,
    ) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        if not verify_password(current_password, user.hashed_password):
            # Bu ýazgy transaction daşynda - başarnyksyz synanyşyk hem
            # üýtgeşmesiz-de ýazgylanmaly, "rollback bilen bile ýitmesin"
            # diýip aýratyn saklaýarys.
            await log_audit_event(
                self._conn,
                user_id=user_id,
                event_type="password_change_failed",
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
                metadata={"reason": "incorrect_current_password"},
            )
            raise IncorrectCurrentPasswordError()

        if verify_password(new_password, user.hashed_password):
            raise SamePasswordError()

        new_hash = hash_password(new_password)

        async with self._conn.transaction():
            await self._user_repo.update_password_hash(user_id, new_hash)
            await log_audit_event(
                self._conn,
                user_id=user_id,
                event_type="password_changed",
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
            # Worker muny alyp ähli session-lary revoke eder - parol
            # üýtgände açyk galan session-lar howp.
            await self._outbox.enqueue(
                "user.password_changed",
                {"user_id": str(user_id)},
            )

    async def deactivate_account(self, user_id: UUID, ctx: RequestContext) -> None:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if not user.is_active:
            raise UserAlreadyDeactivatedError()

        async with self._conn.transaction():
            await self._user_repo.deactivate(user_id)
            await log_audit_event(
                self._conn,
                user_id=user_id,
                event_type="account_deactivated",
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
            )
            await self._outbox.enqueue(
                "user.account_deactivated",
                {"user_id": str(user_id)},
            )
