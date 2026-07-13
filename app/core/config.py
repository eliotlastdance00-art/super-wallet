from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://superwallet:superwallet@localhost:5432/superwallet"
    Alembic_URL: str = "postgresql+asyncpg://superwallet:superwallet@localhost:5432/superwallet"


    class Config:
        env_file = ".env"

settings = Settings()
