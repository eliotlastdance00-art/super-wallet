# service.py
from pydantic import SecretStr

from app.core.security import hash_password

from .repository import UserRepository


class UserService:
    def __init__(self, connection):
        self.connection = connection

    async def register_user(self, username: str, email: str, password: SecretStr):
        async with self.connection.transaction():
            user_repo = UserRepository(self.connection)

            existing_user = await user_repo.get_by_email(email)
            if existing_user:
                raise ValueError("Email already has created!")

            hashed = hash_password(password.get_secret_value())
            new_user = await user_repo.create(username, email, hashed)
            return new_user
