from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 저장소 루트(.env)와 backend/(.env) 모두 읽는다. 뒤의 파일이 우선한다.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./local.db"

    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_redirect_uri: str = ""
    instagram_api_version: str = "v26.0"
    token_encryption_key: str = ""
    state_secret: str = ""
    admin_token: str = ""

    media_storage: Literal["local", "ncp"] = "local"
    media_local_dir: str = "../data/raw/media"

    ncp_object_storage_endpoint: str = "https://kr.object.ncloudstorage.com"
    ncp_access_key: str = ""
    ncp_secret_key: str = ""
    ncp_bucket_name: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
