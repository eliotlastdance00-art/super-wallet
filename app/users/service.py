import asyncpg

from app.users.repository import UserRepository


class UserService:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def register_user(self, username: str, email: str, hashed_password: str):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                user_repo = UserRepository(connection)
                existing_user = await user_repo.get_by_email(email)
                if existing_user:
                    raise ValueError("Email already has created!")
                new_user = await user_repo.create(username, email, hashed_password)
                return new_user
