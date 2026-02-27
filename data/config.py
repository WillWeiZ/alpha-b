# Alpha B 量化系统配置

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """系统配置"""

    # QMT Gateway
    qmt_base_url: str = "http://192.168.31.147:8080"
    qmt_api_key: str = "iloveyou"
    qmt_timeout: int = 30

    # QuestDB
    questdb_host: str = "localhost"
    questdb_port: int = 9019
    questdb_user: str = "admin"
    questdb_password: str = "quest"
    questdb_database: str = "alphab"

    # Parquet 存储路径
    parquet_path: str = "/Users/willbot/projects/00_Alapha_B/data/parquet"

    # 交易参数
    trading_account_id: str = "40304296"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
