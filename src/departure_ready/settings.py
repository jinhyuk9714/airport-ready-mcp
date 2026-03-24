from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEPARTURE_READY_",
        env_file=".env",
        extra="ignore",
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    http_host: str = "127.0.0.1"
    http_port: int = 8000
    http_timeout_sec: float = 15.0
    http_max_retries: int = 2

    cache_ttl_live_sec: int = 30
    cache_ttl_forecast_sec: int = 300
    cache_ttl_static_sec: int = 86400

    kac_service_key: str | None = None
    iiac_service_key: str | None = None

    supported_airports: str = Field(default="ICN,GMP,CJU,PUS,CJJ,TAE")

    public_http_url: str | None = None
    public_mcp_url: str | None = None

    @property
    def supported_airport_list(self) -> list[str]:
        return [x.strip().upper() for x in self.supported_airports.split(",") if x.strip()]

    @property
    def resolved_public_http_url(self) -> str | None:
        if not self.public_http_url:
            return None
        return self.public_http_url.rstrip("/")

    @property
    def resolved_public_mcp_url(self) -> str | None:
        if self.public_mcp_url:
            return self.public_mcp_url.rstrip("/")
        if self.resolved_public_http_url:
            return f"{self.resolved_public_http_url}/mcp"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
