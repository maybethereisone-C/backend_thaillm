from functools import lru_cache
import json
from typing import Annotated

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    api_version: str = "0.1.0"
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    prompt_guard_enabled: bool = True

    audit_trail_dir: str = "audit_trails"
    results_log_dir: str = "logs"
    agent_db_path: str = ""
    agent_src_path: str = ""
    # Local OpenAI-compatible model server (e.g. llama.cpp llama-server) that
    # serves the same model as the upstream. No API key: the server is local.
    thaillm_base_url: AnyHttpUrl | None = Field(default="http://127.0.0.1:8080/v1")
    thaillm_model_id: str = "typhoon-s-thaillm-8b-instruct"

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
