from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults_need_no_secrets() -> None:
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key is None
    assert settings.jwt_secret is None
    assert settings.embed_dim == 768
    assert settings.money_tolerance == Decimal("0.01")
    assert isinstance(settings.money_tolerance, Decimal)


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins=" https://a.vercel.app/ , http://localhost:3000,, ",
    )
    assert settings.cors_origin_list == ["https://a.vercel.app", "http://localhost:3000"]


def test_secrets_never_appear_in_repr() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pppppppppppp@db:5432/x",
        gemini_api_key="gggggggggggggggg",
        jwt_secret="jjjjjjjjjjjjjjjj",
    )
    text = repr(settings) + str(settings.model_dump())
    assert "pppppppppppp" not in text
    assert "gggggggggggggggg" not in text
    assert "jjjjjjjjjjjjjjjj" not in text


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_DIM", "1536")
    monkeypatch.setenv("MONEY_TOLERANCE", "0.05")
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings(_env_file=None)
    assert settings.embed_dim == 1536
    assert settings.money_tolerance == Decimal("0.05")
    assert settings.is_production


def test_rejects_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")


def test_rejects_out_of_range_thresholds() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, field_confidence_threshold=1.5)
