from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Use Field or provide default/None if you want to silence IDE type-checking warnings
    DATABASE_URL: str
    Alembic_URL: str
    TOKEN_SIGNING_KEY: str
    ENCRYPTION_KEY: str
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    EMAIL_FROM_ADDRESS: str

    # Modern Pydantic v2 Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # This prevents "extra_forbidden" errors from unexpected inputs in your .env
        env_file_encoding="utf-8"
    )


# To completely quiet type checkers that complain about missing arguments during instantiation:
settings = Settings()  # type: ignore