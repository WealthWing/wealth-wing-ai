from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.logging_config import configure_logging


class Settings(BaseSettings):
    app_name: str = "Wealth Wing AI API"
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    enable_docs: bool = Field(default=False, alias="ENABLE_DOCS")

    fe_url: Optional[str] = Field(default=None, alias="FE_URL")
    cors_origins_raw: Optional[str] = Field(default=None, alias="CORS_ORIGINS")
    allowed_hosts_raw: Optional[str] = Field(default=None, alias="ALLOWED_HOSTS")
    cognito_jwks_url: Optional[str] = Field(default=None, alias="COGNITO_JWKS_URL")
    cognito_user_pool_id: Optional[str] = Field(
        default=None, alias="COGNITO_USER_POOL_ID"
    )
    aws_region: Optional[str] = Field(default=None, alias="AWS_REGION")
    cognito_issuer: Optional[str] = Field(default=None, alias="COGNITO_ISSUER")
    cognito_client_id: Optional[str] = Field(default=None, alias="COGNITO_CLIENT_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    model: str = Field(default="openai/gpt-oss-120b", alias="MODEL")

    together_api_key: SecretStr = Field(alias="TOGETHER_API_KEY", default="")
    wealth_wing_data_health_url: Optional[str] = Field(
        default=None, alias="WEALTH_WING_DATA_HEALTH_URL"
    )

    @property
    def cors_origins(self) -> List[str]:
        origins = self._split_csv(self.cors_origins_raw) or [
            "https://localhost:3000",
            "http://localhost:3000",
            "https://localhost:3001",
            "http://localhost:3001",
        ]

        if self.fe_url:
            origins.append(self.fe_url)

        return origins

    @property
    def allowed_hosts(self) -> List[str]:
        return self._split_csv(self.allowed_hosts_raw) or [
            "localhost",
            "127.0.0.1",
            "testserver",
        ]

    @property
    def public_paths(self) -> List[str]:
        paths = ["/health", "/health/ping"]

        if self.enable_docs:
            paths.extend(
                [
                    "/docs",
                    "/docs/oauth2-redirect",
                    "/redoc",
                    "/openapi.json",
                ]
            )

        return paths

    @property
    def is_auth_configured(self) -> bool:
        return all(
            [
                self.cognito_jwks_url,
                self.cognito_issuer,
                self.cognito_client_id,
            ]
        )

    def configure_logging(self) -> None:
        configure_logging(
            log_level=self.log_level,
            json_logs=self.log_format.lower() == "json",
        )

    @staticmethod
    def _split_csv(value: Optional[str]) -> List[str]:
        if not value:
            return []

        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
