from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("./data")
    qwen_base_url: str = ""
    qwen_api_key: str = ""
    qwen_model: str = "Qwen3.6-35B-A3B"
    rar_executable: str = ""
    max_upload_mb: int = 100
    max_archive_files: int = 2000
    max_archive_bytes: int = 1024 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    def model_post_init(self, __context):
        aliases = {
            "FUNDTRACE_DATA_DIR": "data_dir",
            "QWEN_BASE_URL": "qwen_base_url",
            "QWEN_API_KEY": "qwen_api_key",
            "QWEN_MODEL": "qwen_model",
            "RAR_EXECUTABLE": "rar_executable",
        }
        import os
        for env, field in aliases.items():
            if os.getenv(env) and field not in self.model_fields_set:
                object.__setattr__(self, field, Path(os.getenv(env)) if field == "data_dir" else os.getenv(env))


@lru_cache
def get_settings() -> Settings:
    return Settings()

