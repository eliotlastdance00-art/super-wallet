import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg


@dataclass
class OutboxEventRecord:
    id: UUID
    event_type: str
    payload: dict
    status: str
    attempts: int


class OutboxRepository:
    """
    Umumy 'event ýazgy' tablisasy - islendik domen (users, fiat, cards)
    muny ulanyp biler. Repository diňe CRUD bilýär, "haýsy event_type
    näme edýär" diýen logika bu ýerde ÝOK - ol worker/handler-lerde.
    """

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    async def enqueue(self, event_type: str, payload: dict) -> UUID:
        """
        Caller-iň AÇYK transaction-y içinde çagyrylmaly - beýleki DB
        üýtgeşmeleri (parol täzelenmesi, ş.m.) bilen ATOMIK bolmagy
        üçin. Aýratyn "auto-commit" ýok bu ýerde bilkastlaýyn.
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO outbox_events (id, event_type, payload, created_at)
            VALUES (gen_random_uuid(), $1, $2, now())
            RETURNING id
            """,
            event_type,
            json.dumps(payload),
        )
        if row is None:
            raise RuntimeError("Failed to enqueue outbox event.")
        return row["id"]

    async def fetch_pending(self, limit: int = 50) -> list[OutboxEventRecord]:
        """
        FOR UPDATE SKIP LOCKED - eger geljekde birden köp worker
        process işlese (horizontal scale), ikisi ARALARYNDA bir
        ýazgyny "eýelemek" üçin dawalaşmaz - biri alsa, beýlekisi
        awtomatik indiki ýazgyny alýar, garaşmaýar.
        """
        rows = await self._conn.fetch(
            """
            SELECT id, event_type, payload, status, attempts
            FROM outbox_events
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT $1
            FOR UPDATE SKIP LOCKED
            """,
            limit,
        )
        return [
            OutboxEventRecord(
                id=r["id"],
                event_type=r["event_type"],
                payload=json.loads(r["payload"]),
                status=r["status"],
                attempts=r["attempts"],
            )
            for r in rows
        ]

    async def mark_done(self, event_id: UUID) -> None:
        await self._conn.execute(
            "UPDATE outbox_events SET status = 'done', processed_at = now() WHERE id = $1",
            event_id,
        )

    async def mark_failed(self, event_id: UUID, error: str, new_attempts: int) -> None:
        await self._conn.execute(
            """
            UPDATE outbox_events
            SET status = 'failed', last_error = $2, attempts = $3
            WHERE id = $1
            """,
            event_id,
            error,
            new_attempts,
        )

    async def reset_to_pending(self, event_id: UUID, new_attempts: int) -> None:
        """
        Retry üçin: 'failed' -> gaýtadan 'pending' diýip belläp, worker
        ony indiki tapgyrda gaýtadan synanyşar. Attempts sany bilen
        çäklendirmek (max retry) - caller (worker) jogapkär.
        """
        await self._conn.execute(
            "UPDATE outbox_events SET status = 'pending', attempts = $2 WHERE id = $1",
            event_id,
            new_attempts,
        )
