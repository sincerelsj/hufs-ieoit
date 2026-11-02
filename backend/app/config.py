from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/ 폴더. 실행 위치(cwd)와 상관없이 기본 경로를 고정한다.
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # 저장소 루트(.env)와 backend/(.env) 모두 읽는다. 뒤의 파일이 우선한다.
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'local.db').as_posix()}"

    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_redirect_uri: str = ""
    instagram_api_version: str = "v26.0"
    token_encryption_key: str = ""
    state_secret: str = ""
    # 연결 링크 유효 시간(초). 운영자가 링크를 받아 학생회에 전달하는 시간을 고려해 기본 72시간.
    oauth_state_max_age: int = 259200
    admin_token: str = ""

    media_storage: Literal["local", "ncp"] = "local"
    media_local_dir: str = str(BACKEND_DIR.parent / "data" / "raw" / "media")

    ncp_object_storage_endpoint: str = "https://kr.object.ncloudstorage.com"
    ncp_access_key: str = ""
    ncp_secret_key: str = ""
    ncp_bucket_name: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
