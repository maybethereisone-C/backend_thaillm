from functools import lru_cache
import json
from typing import Annotated

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    api_version: str = "0.1.0"
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    prompt_guard_enabled: bool = True

    audit_trail_dir: str = "audit_trails"
    agent_db_path: str = ""
    agent_src_path: str = ""
    thaillm_base_url: AnyHttpUrl | None = None
    thaillm_model_id: str = ""
    thaillm_api_key: SecretStr | None = None

    @field_validator("allowed_origins", "trusted_hosts", mode="before")
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

    @field_validator("allowed_origins")
    @classmethod
    def no_wildcard_with_credentials(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("Wildcard origin cannot be combined with credentialed CORS")
        return value

    @field_validator("thaillm_base_url", mode="before")
    @classmethod
    def blank_url_to_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
