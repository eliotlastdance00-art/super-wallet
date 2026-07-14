# app/core/audit.py

import json
from uuid import UUID

import asyncpg


async def log_audit_event(
    conn: asyncpg.Connection,
    user_id: UUID | None,
    event_type: str,
    ip_address: str | None,
    user_agent: str | None,
    metadata: dict | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO audit_logs (user_id, event_type, ip_address, user_agent, metadata, created_at)
        VALUES ($1, $2, $3, $4, $5, now())
        """,
        user_id,
        event_type,
        ip_address,
        user_agent,
        json.dumps(metadata) if metadata is not None else None,
    )