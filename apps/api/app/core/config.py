from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str = "postgresql+psycopg://lial:lial@localhost:5432/lial_energy"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_documents: str = "lial-documents"
    # Separate PUBLIC-read bucket for profile/product photos -- never the
    # same bucket as documents, which must stay private. See core/storage.py.
    s3_bucket_media: str = "lial-media"
    s3_region: str = "eu-central-1"
    s3_use_ssl: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]

    # /backend/docs, /backend/redoc and /backend/openapi.json are reachable
    # directly from the internet (see infrastructure/nginx/nginx.conf) --
    # convenient for development but a full API-surface disclosure in a real
    # production deployment. Defaults to enabled here because this project's
    # only environment today IS the dev/demo one and docs/user-guide.md
    # already documents /backend/docs as a real, relied-upon feature; set
    # ENABLE_API_DOCS=false in .env for a real production deployment (see
    # docs/server-migration-guide.md).
    enable_api_docs: bool = True

    # SMTP for password-reset emails (see auth/service.py::request_password_reset).
    # Left unset (smtp_host empty) falls back to logging the reset link via the
    # audit trail instead of failing -- see docs/business-rules.md §Password reset.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "no-reply@lialenergy.demo"
    smtp_use_tls: bool = True

    # Bank account customers wire the 3% redemption payment to (see
    # invoice_redemptions/router.py's GET /payment-info). Left empty on
    # purpose until a real company account is provided -- the redemption
    # wizard shows "contact administration" instead of a fake IBAN when
    # unset, same "safe empty default, functional once configured" pattern
    # as SMTP_HOST above.
    company_bank_iban: str = ""
    company_bank_holder: str = "Lial Energy"

    # Base URL the dashboard is reachable at, used to build the link inside a
    # password-reset email (the API has no other way to know its own public
    # hostname -- it's never addressed directly by end users, see nginx.conf).
    public_app_base_url: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
