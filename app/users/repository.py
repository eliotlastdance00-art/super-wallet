from typing import Any

import asyncpg


class UserRepository:
    def __init__(self, connection: asyncpg.Connection):
        self.connection = connection

    async def create(
        self, username: str, email: str, hashed_password: str
    ) -> dict[str, Any]:
        row = await self.connection.fetchrow(
            """
            INSERT INTO users (username, email, hashed_password)
            VALUES ($1, $2, $3)
            RETURNING id, username, email, created_at
            """,
            username,
            email,
            hashed_password,
        )
        assert row is not None, "User could not be created"
        return dict(row)

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        row = await self.connection.fetchrow(
            "SELECT id FROM users WHERE email = $1", email
        )
        return dict(row) if row else None

    async def get_by_username(self, username: str) -> dict[str, Any] | None:
        row = await self.connection.fetchrow(
            "SELECT id FROM users WHERE username = $1", username
        )
        return dict(row) if row else None
