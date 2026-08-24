import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default: str = "", required: bool = True) -> str:
    value = os.getenv(key, default).strip()
    if required and not value:
        raise RuntimeError(f"Required environment variable '{key}' is not set. App cannot start.")
    return value


def get_bool_env(key: str, default: bool = False) -> bool:
    value = os.getenv(key, "").strip().lower()
    if not value:
        return default
    return value == "true"


@dataclass
class DatabaseConfig:
    url: str


@dataclass
class AuthConfig:
    jwt_secret: str
    access_token_expiry_minutes: int
    refresh_token_expiry_days: int
    cookie_secure: bool  # false only for local http dev


@dataclass
class ServicesConfig:
    cors_origins: list
    frontend_base_url: str
    enable_docs: bool = False  # exposes the full API surface with no auth of its own
    # True in every real deployment (behind Render's proxy) - only disable if
    # this app ever receives connections directly from the internet, where
    # trusting a client-supplied header would make IP-based rate limits spoofable.
    trust_proxy_headers: bool = True
    # Defaults to "production" deliberately - a deployment that forgets to set
    # this should get the safe behavior (no OTPs/reset links in logs), not the
    # dev-convenience one. Set to "development" explicitly in local .env files.
    environment: str = "production"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@dataclass
class EmailConfig:
    sendgrid_api_key: str
    from_email: str

    @property
    def is_configured(self) -> bool:
        return bool(self.sendgrid_api_key and self.from_email)


@dataclass
class SecretsConfig:
    email_encryption_key: str
    email_hash_secret: str
    otp_hash_secret: str


@dataclass
class SigningServiceConfig:
    base_url: str  # endpoint/auth contract not finalized yet - placeholders
    api_key: str

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)


@dataclass
class PaymentConfig:
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    currency: str

    @property
    def is_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret and self.razorpay_webhook_secret)


@dataclass
class StorageConfig:
    # Linode Object Storage (S3-compatible) — the SAME bucket/credentials as the
    # Infollion backend, so transcript files uploaded there (private, under
    # infollion-v2/) can be read here. Used read-only: we only mint short-lived
    # presigned GET URLs (get_object); never upload/delete.
    access_key: str
    secret_key: str
    region: str
    bucket: str
    endpoint: str

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key and self.secret_key and self.bucket and self.endpoint)


@dataclass
class IngestConfig:
    # Shared secret for the Infollion backend's server-to-server transcript ingest
    # (POST/PATCH /api/internal/transcripts). Must match Infollion's SYNDICATE_SERVICE_API_KEY.
    api_key: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class Settings:
    database: DatabaseConfig
    auth: AuthConfig
    services: ServicesConfig
    email: EmailConfig
    secrets: SecretsConfig
    signing_service: SigningServiceConfig
    payment: PaymentConfig
    ingest: IngestConfig
    storage: StorageConfig

    @classmethod
    def from_env(cls) -> "Settings":
        raw_origins = get_env("CORS_ALLOWED_ORIGINS")
        cors_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        if not cors_origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS must contain at least one origin. App cannot start.")

        return cls(
            database=DatabaseConfig(
                url=get_env("DATABASE_URL"),
            ),
            auth=AuthConfig(
                jwt_secret=get_env("JWT_SECRET"),
                access_token_expiry_minutes=int(get_env("ACCESS_TOKEN_EXPIRY_MINUTES", default="15", required=False)),
                refresh_token_expiry_days=int(get_env("REFRESH_TOKEN_EXPIRY_DAYS", default="30", required=False)),
                cookie_secure=get_bool_env("COOKIE_SECURE", default=True),
            ),
            services=ServicesConfig(
                cors_origins=cors_origins,
                frontend_base_url=get_env("FRONTEND_BASE_URL"),
                enable_docs=get_bool_env("ENABLE_DOCS", default=False),
                trust_proxy_headers=get_bool_env("TRUST_PROXY_HEADERS", default=True),
                environment=get_env("ENVIRONMENT", default="production", required=False).lower(),
            ),
            email=EmailConfig(
                sendgrid_api_key=get_env("SENDGRID_API_KEY", default="", required=False),
                from_email=get_env("FROM_EMAIL", default="", required=False),
            ),
            secrets=SecretsConfig(
                email_encryption_key=get_env("EMAIL_ENCRYPTION_KEY"),
                email_hash_secret=get_env("EMAIL_HASH_SECRET"),
                otp_hash_secret=get_env("OTP_HASH_SECRET"),
            ),
            signing_service=SigningServiceConfig(
                base_url=get_env("SIGNING_SERVICE_URL", default="", required=False),
                api_key=get_env("SIGNING_SERVICE_API_KEY", default="", required=False),
            ),
            payment=PaymentConfig(
                razorpay_key_id=get_env("RAZORPAY_KEY_ID", default="", required=False),
                razorpay_key_secret=get_env("RAZORPAY_KEY_SECRET", default="", required=False),
                razorpay_webhook_secret=get_env("RAZORPAY_WEBHOOK_SECRET", default="", required=False),
                currency=get_env("PAYMENT_CURRENCY", default="USD", required=False),
            ),
            ingest=IngestConfig(
                api_key=get_env("SYNDICATE_INBOUND_API_KEY", default="", required=False),
            ),
            storage=StorageConfig(
                access_key=get_env("LINODE_ACCESS_KEY", default="", required=False),
                secret_key=get_env("LINODE_SECRET_KEY", default="", required=False),
                region=get_env("LINODE_REGION", default="", required=False),
                bucket=get_env("LINODE_BUCKET", default="", required=False),
                endpoint=get_env("LINODE_ENDPOINT", default="", required=False),
            ),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
