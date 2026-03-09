"""config.py – Environment-driven configuration for auth-service."""

import os
from datetime import timedelta


class Config:
    """Base configuration parameterised via environment variables."""

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG: bool = False
    TESTING: bool = False

    JWT_SECRET_KEY: str = os.environ.get(
        "JWT_SECRET_KEY", "jwt-secret-change-in-production"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
    )
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(
        days=int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))
    )

    AUTH_SERVICE_HOST: str = os.environ.get("AUTH_SERVICE_HOST", "0.0.0.0")
    AUTH_SERVICE_PORT: int = int(os.environ.get("AUTH_SERVICE_PORT", "5000"))


class DevelopmentConfig(Config):
    DEBUG: bool = True


class TestingConfig(Config):
    TESTING: bool = True
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(minutes=5)
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(minutes=10)


class ProductionConfig(Config):
    pass


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config() -> Config:
    """Return a Config instance based on FLASK_ENV."""
    env = os.environ.get("FLASK_ENV", "development")
    return _CONFIG_MAP.get(env, DevelopmentConfig)()
