import hashlib
import hmac
import json
from dataclasses import asdict, dataclass

from app.core.settings import Settings


@dataclass(frozen=True)
class ToolManifest:
    name: str
    version: str
    description: str
    permissions: tuple[str, ...]
    input_schema: dict
    output_schema: dict

    def payload(self) -> dict:
        return asdict(self)


TOOL_MANIFESTS = (
    ToolManifest(
        name="version_info",
        version="1.0.0",
        description="Return public API version and active inference backend.",
        permissions=("read:version",),
        input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        output_schema={
            "type": "object",
            "required": ["api_version", "backend", "model"],
            "properties": {
                "api_version": {"type": "string"},
                "backend": {"type": "string"},
                "model": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    ToolManifest(
        name="llm_security_policy",
        version="1.0.0",
        description="Return request guardrail limits exposed to MCP clients.",
        permissions=("read:security-policy",),
        input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        output_schema={
            "type": "object",
            "required": [
                "prompt_guard_enabled",
                "prompt_max_chars",
                "max_tokens_limit",
                "request_body_limit_bytes",
                "response_text_limit_chars",
            ],
            "properties": {
                "prompt_guard_enabled": {"type": "boolean"},
                "prompt_max_chars": {"type": "integer"},
                "max_tokens_limit": {"type": "integer"},
                "request_body_limit_bytes": {"type": "integer"},
                "response_text_limit_chars": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    ),
    ToolManifest(
        name="mcp_tool_manifest",
        version="1.0.0",
        description="Return signed manifest metadata for exposed MCP tools.",
        permissions=("read:tool-manifest",),
        input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        output_schema={
            "type": "object",
            "required": ["tools", "sha256", "signature"],
            "properties": {
                "tools": {"type": "array"},
                "sha256": {"type": "string"},
                "signature": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
    ),
)


def manifest_payload(settings: Settings) -> dict:
    tools = [manifest.payload() for manifest in TOOL_MANIFESTS]
    canonical = json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    signature = None
    if settings.mcp_manifest_signing_key:
        signature = hmac.new(
            settings.mcp_manifest_signing_key.get_secret_value().encode(),
            canonical,
            hashlib.sha256,
        ).hexdigest()
    return {"tools": tools, "sha256": digest, "signature": signature}
