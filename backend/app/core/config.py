"""Application settings, read from environment variables.

Every name here matches `.env.example` at the repository root. Secrets use
`SecretStr`, so they never appear in logs, reprs or error messages.

Phase 0 needs only `DATABASE_URL`. The other secrets are optional until the
feature that uses them exists, so a missing Gemini key cannot stop the API
from starting.

In production, `DATABASE_URL` and `CORS_ORIGINS` must be set explicitly. Their
defaults point at localhost, which would fail later with a confusing error, so
startup stops at once and names the missing variable. Validation errors never
echo input values, because those can hold secrets.
"""

from decimal import Decimal
from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Never print input values in errors: DATABASE_URL holds a password.
        hide_input_in_errors=True,
    )

    # Must be set explicitly when APP_ENV=production (their defaults are for local use).
    REQUIRED_IN_PRODUCTION: ClassVar[tuple[str, ...]] = ("database_url", "cors_origins")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Database. Use the Supabase session pooler string on Render (IPv4).
    database_url: SecretStr = SecretStr("postgresql+psycopg://localhost:5432/docintel")
    db_pool_size: int = Field(default=3, ge=1, le=20)
    db_max_overflow: int = Field(default=2, ge=0, le=20)
    db_connect_timeout_s: int = Field(default=5, ge=1, le=60)

    # Files only, through the Supabase Storage API. The Data API is disabled and the
    # database is reached only through SQLAlchemy (DECISIONS.md D17). The private
    # bucket already exists with a 50 MB file limit; code never creates buckets.
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_bucket: str = "documents"
    # Where uploaded files live: "supabase" (Storage API) or "local" (a folder on disk,
    # for docker-compose and tests). Unset means supabase in production, local elsewhere.
    storage_backend: Literal["local", "supabase"] | None = None
    local_storage_dir: str = "uploads"
    storage_timeout_s: float = Field(default=60, gt=0)

    # Gemini. Model names are configuration, never code.
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    gemini_vision_model: str | None = None
    gemini_embed_model: str | None = None
    embed_dim: int = Field(default=768, ge=1, le=16000)
    llm_max_concurrency: int = Field(default=2, ge=1, le=32)
    llm_timeout_s: float = Field(default=90, gt=0)
    llm_max_retries: int = Field(default=4, ge=0, le=10)  # on 429, 5xx and timeouts
    llm_calls_per_minute: int | None = Field(default=12, ge=1)  # stay under free-tier quotas

    # Auth for the single demo account (Phase 4).
    jwt_secret: SecretStr | None = None
    jwt_ttl_minutes: int = Field(default=120, ge=5, le=1440)
    demo_username: str = "reviewer"
    demo_password: SecretStr | None = None
    login_rate_per_minute: int = Field(default=5, ge=1)  # per client IP
    upload_rate_per_minute: int = Field(default=10, ge=1)  # upload requests per client IP

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    # Upload and processing limits.
    max_file_mb: int = Field(default=50, ge=1)  # keep at or below the bucket limit (50 MB)
    max_files_per_batch: int = Field(default=20, ge=1)
    max_pdf_pages: int = Field(default=1500, ge=1)
    ocr_confidence_threshold: float = Field(default=60, ge=0, le=100)
    field_confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    money_tolerance: Decimal = Field(default=Decimal("0.01"), ge=0)
    # Validation (Phase 3).
    supplier_similarity: float = Field(default=0.5, gt=0, le=1)  # pg_trgm score for "same"
    max_invoice_age_years: int = Field(default=10, ge=1)  # older dates get a warning

    # Ingestion (Phase 1).
    max_unzipped_mb: int = Field(default=200, ge=1)  # guard against .xlsx zip bombs
    pdf_page_batch_size: int = Field(default=20, ge=1, le=500)
    scanned_page_min_chars: int = Field(default=25, ge=0)  # fewer letters/digits means OCR
    ocr_dpi: int = Field(default=300, ge=72, le=600)
    ocr_timeout_s: int = Field(default=120, ge=5)

    # Extraction (Phase 2).
    segment_window_pages: int = Field(default=8, ge=1, le=50)  # pages per LLM call
    segment_overlap_pages: int = Field(default=1, ge=0, le=10)  # shared with the next window
    vision_dpi: int = Field(default=200, ge=72, le=400)
    date_day_first: bool = True  # 03/04/2026 is 3 April unless the day is over 12

    # Worker loop and job queue (Phase 4).
    worker_poll_interval_s: float = Field(default=2.0, gt=0)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_backoff_s: float = Field(default=30, ge=0)  # first retry delay; doubles each time
    heartbeat_interval_s: float = Field(default=10, gt=0)
    stale_job_s: float = Field(default=120, gt=0)  # a running job silent this long is re-queued

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return ",".join(part.strip().rstrip("/") for part in value.split(",") if part.strip())

    @model_validator(mode="after")
    def _require_production_settings(self) -> "Settings":
        if self.is_production:
            missing = [n for n in self.REQUIRED_IN_PRODUCTION if n not in self.model_fields_set]
            if missing:
                names = ", ".join(name.upper() for name in missing)
                raise ValueError(f"{names} must be set when APP_ENV=production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin for origin in self.cors_origins.split(",") if origin]

    @property
    def resolved_storage_backend(self) -> Literal["local", "supabase"]:
        if self.storage_backend is not None:
            return self.storage_backend
        return "supabase" if self.is_production else "local"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings. Tests clear the cache to change them."""
    return Settings()
