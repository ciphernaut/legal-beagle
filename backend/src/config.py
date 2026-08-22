from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://legal:legal@localhost:5432/legal"
    llm_model: str = "qwen3.8-27b-fp8"
    llm_api_base: str = "http://localhost:7080/v1"
    embed_model: str = "BAAI/bge-small-en-v1.5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
