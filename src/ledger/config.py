from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://ledger:ledger@localhost:5432/ledger"
    echo_sql: bool = False

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
