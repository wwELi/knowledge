from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://kb:kb@localhost:5433/kb"
    LLM_BASE_URL: str = "https://api.nofude.xyz/v1"
    LLM_API_KEY: str
    LLM_MODEL: str = "deepseek-v4-flash"
    EMBED_MODEL: str = "BAAI/bge-small-zh-v1.5"
    EMBED_DIM: int = 512
    TOP_K: int = 5
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 80
    UPLOAD_DIR: Path = _REPO_ROOT / "backend" / "data" / "uploads"

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        extra="ignore",
    )


@lru_cache
def get_config() -> Settings:
    return Settings()


config = get_config()
