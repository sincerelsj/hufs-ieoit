import logging
from pathlib import Path

from app.config import BACKEND_DIR, Settings
from app.main import create_app


def test_default_paths_are_anchored_to_backend_dir():
    settings = Settings(_env_file=None)
    assert BACKEND_DIR.name == "backend"
    assert settings.database_url == f"sqlite:///{(BACKEND_DIR / 'local.db').as_posix()}"
    assert Path(settings.media_local_dir) == BACKEND_DIR.parent / "data" / "raw" / "media"
    assert Path(settings.media_local_dir).is_absolute()


def test_default_paths_do_not_depend_on_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.database_url == f"sqlite:///{(BACKEND_DIR / 'local.db').as_posix()}"
    assert Path(settings.media_local_dir).is_absolute()


def test_oauth_state_max_age_default_is_72_hours():
    assert Settings(_env_file=None).oauth_state_max_age == 259200


def test_create_app_quiets_httpx_logger(settings):
    logging.getLogger("httpx").setLevel(logging.INFO)
    create_app(settings)
    assert logging.getLogger("httpx").level == logging.WARNING
