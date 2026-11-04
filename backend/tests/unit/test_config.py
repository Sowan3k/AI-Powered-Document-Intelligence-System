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
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:pppppppppppp@db:5432/x")
    monkeypatch.setenv("CORS_ORIGINS", "https://front.example")
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


PROD_DB = "postgresql+psycopg://u:pppppppppppp@db:5432/x"


@pytest.mark.parametrize(
    ("given", "missing"),
    [
        ({}, "DATABASE_URL, CORS_ORIGINS"),
        ({"cors_origins": "https://front.example"}, "DATABASE_URL"),
        ({"database_url": PROD_DB}, "CORS_ORIGINS"),
    ],
)
def test_production_names_missing_settings(
    given: dict[str, str], missing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # conftest exports CORS_ORIGINS; a real environment variable counts as "set".
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, app_env="production", **given)
    message = str(error.value)
    assert f"{missing} must be set when APP_ENV=production" in message
    assert "pppppppppppp" not in message  # input values are never echoed


def test_production_accepts_values_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", PROD_DB)
    monkeypatch.setenv("CORS_ORIGINS", "https://front.example")
    assert Settings(_env_file=None).is_production


def test_development_keeps_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None, app_env="development")
    assert "localhost" in settings.database_url.get_secret_value()


def test_invalid_values_never_echo_secrets() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=PROD_DB, embed_dim="not-a-number")
    assert "pppppppppppp" not in str(error.value)
