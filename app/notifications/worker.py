# notifications/worker.py
import asyncio
import logging

from core.database import db, get_connection
from core.outbox import OutboxRepository
from notifications.handlers.email_handler import handle_email_event
from core.config import settings

logger = logging.getLogger("notifications.worker")

HANDLERS = {
    "email": handle_email_event,
}

MAX_ATTEMPTS = 5
POLL_INTERVAL_SECONDS = 2


async def _process_one(conn, repo: OutboxRepository, event) -> None:
    handler = HANDLERS.get(event.event_type)
    if handler is None:
        logger.warning("No handler for event_type=%s, marking failed", event.event_type)
        await repo.mark_failed(event.id, "no_handler", event.attempts + 1)
        return

    try:
        await handler(event.payload)
        await repo.mark_done(event.id)
    except Exception as exc:  # noqa: BLE001
        new_attempts = event.attempts + 1
        logger.exception("Event %s failed (attempt %d)", event.id, new_attempts)
        if new_attempts >= MAX_ATTEMPTS:
            await repo.mark_failed(event.id, str(exc), new_attempts)
        else:
            await repo.reset_to_pending(event.id, new_attempts)


async def run_worker() -> None:
    await db.connect(dsn=settings.DATABASE_URL)
    logger.info("Notification worker started.")

    try:
        while True:
            async with get_connection() as conn:
                async with conn.transaction():
                    repo = OutboxRepository(conn)
                    events = await repo.fetch_pending(limit=50)
                    for event in events:
                        await _process_one(conn, repo, event)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(run_worker())