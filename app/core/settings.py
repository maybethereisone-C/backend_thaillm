from functools import lru_cache
import json
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    api_version: str = "0.1.0"
    backend: Literal["fake", "openai_compatible"] = "fake"
    model_id: str = "default"
    upstream_base_url: AnyHttpUrl | None = None
    upstream_api_key: SecretStr | None = None
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    max_tokens_default: int = Field(default=512, gt=0)
    api_keys: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    prompt_guard_enabled: bool = True

    # competition endpoints
    audit_trail_dir: str = "audit_trails"
    agent_db_path: str = ""
    agent_src_path: str = ""
    thaillm_base_url: AnyHttpUrl | None = None
    thaillm_model_id: str = ""
    thaillm_api_key: SecretStr | None = None

    @field_validator("api_keys", "allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def parse_csv(cls, value: list[str] | str | None) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            if value.strip().startswith("["):
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("upstream_base_url", "thaillm_base_url", mode="before")
    @classmethod
    def blank_url_to_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_backend_config(self) -> "Settings":
        if self.backend == "openai_compatible" and self.upstream_base_url is None:
            raise ValueError("LLM_UPSTREAM_BASE_URL is required when LLM_BACKEND=openai_compatible")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
