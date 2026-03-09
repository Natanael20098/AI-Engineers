import os
from datetime import timedelta


class Config:
    """Base configuration for the Authentication Service."""

    # Flask
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG: bool = False
    TESTING: bool = False

    # JWT
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "jwt-secret-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
    )

    # Database (PostgreSQL)
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/authdb",
    )

    # OAuth2 / third-party provider
    OAUTH2_CLIENT_ID: str = os.environ.get("OAUTH2_CLIENT_ID", "")
    OAUTH2_CLIENT_SECRET: str = os.environ.get("OAUTH2_CLIENT_SECRET", "")
    OAUTH2_AUTHORIZE_URL: str = os.environ.get(
        "OAUTH2_AUTHORIZE_URL", "https://accounts.google.com/o/oauth2/v2/auth"
    )
    OAUTH2_TOKEN_URL: str = os.environ.get(
        "OAUTH2_TOKEN_URL", "https://oauth2.googleapis.com/token"
    )
    OAUTH2_USERINFO_URL: str = os.environ.get(
        "OAUTH2_USERINFO_URL", "https://www.googleapis.com/oauth2/v3/userinfo"
    )
    OAUTH2_REDIRECT_URI: str = os.environ.get(
        "OAUTH2_REDIRECT_URI", "http://localhost:5000/auth/oauth2/callback"
    )
    OAUTH2_SCOPES: str = os.environ.get("OAUTH2_SCOPES", "openid email profile")

    # Token blacklist backend (in-memory by default; swap to Redis in production)
    TOKEN_BLACKLIST_BACKEND: str = os.environ.get("TOKEN_BLACKLIST_BACKEND", "memory")
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class DevelopmentConfig(Config):
    DEBUG: bool = True


class TestingConfig(Config):
    TESTING: bool = True
    DATABASE_URL: str = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(minutes=5)


class ProductionConfig(Config):
    pass


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config() -> Config:
    env = os.environ.get("FLASK_ENV", "development")
    return _CONFIG_MAP.get(env, DevelopmentConfig)()
