from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("./data")
    qwen_base_url: str = ""
    qwen_api_key: str = ""
    qwen_model: str = "Qwen3.6-35B-A3B"
    qwen_domain_concurrency: int = Field(default=6, ge=1, le=32)
    qwen_schema_retries: int = Field(default=2, ge=0, le=5)
    rar_executable: str = ""
    max_upload_mb: int = 100
    max_archive_files: int = 2000
    max_archive_bytes: int = 1024 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    def model_post_init(self, __context):
        """
        模型初始化后的后处理函数，用于处理环境变量并设置模型字段。
        该函数会检查一系列预定义的环境变量别名，如果环境变量存在且对应的模型字段未被设置，
        则将该环境变量的值赋给模型字段。如果字段是"data_dir"，则将值转换为Path对象。
        参数:
            self: 模型实例
            __context: 初始化上下文（未使用）
        """
        # 定义环境变量与模型字段的映射关系
        aliases = {
            "FUNDTRACE_DATA_DIR": "data_dir",
            "QWEN_BASE_URL": "qwen_base_url",
            "QWEN_API_KEY": "qwen_api_key",
            "QWEN_MODEL": "qwen_model",
            "QWEN_DOMAIN_CONCURRENCY": "qwen_domain_concurrency",
            "QWEN_SCHEMA_RETRIES": "qwen_schema_retries",
            "RAR_EXECUTABLE": "rar_executable",
        }
        # 导入os模块以访问环境变量
        import os
        # 遍历环境变量与字段的映射关系
        for env, field in aliases.items():
            # 检查环境变量是否存在且字段未被设置
            if os.getenv(env) and field not in self.model_fields_set:
                # 如果是data_dir字段，将值转换为Path对象；否则直接使用环境变量值
                object.__setattr__(self, field, Path(os.getenv(env)) if field == "data_dir" else os.getenv(env))


@lru_cache
def get_settings() -> Settings:
    return Settings()
