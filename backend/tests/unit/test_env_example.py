"""`.env.example` must stay in step with the settings class."""

from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"

# Pool tuning knobs with safe defaults; not worth a line in .env.example.
UNDOCUMENTED = {"db_pool_size", "db_max_overflow", "db_connect_timeout_s"}


def test_every_setting_is_documented() -> None:
    names = {key.lower() for key in dotenv_values(ENV_EXAMPLE)}
    missing = set(Settings.model_fields) - UNDOCUMENTED - names
    assert missing == set()


def test_example_values_parse_with_inline_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    # Real environment variables win over the file, so clear the ones tests set.
    for name in ("APP_ENV", "CORS_ORIGINS", "EMBED_DIM", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=ENV_EXAMPLE)
    assert settings.app_env == "production"
    assert settings.embed_dim == 768
    assert settings.cors_origin_list == ["https://YOUR-FRONTEND.vercel.app"]
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
