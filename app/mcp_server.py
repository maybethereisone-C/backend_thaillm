from fastmcp import FastMCP

from app.core.settings import Settings
from app.mcp_manifest import manifest_payload


def create_mcp_server(settings: Settings) -> FastMCP:
    mcp = FastMCP("ThaiLLM Backend")

    @mcp.tool
    def version_info() -> dict[str, str]:
        """Return public API version and active inference backend."""
        return {
            "api_version": settings.api_version,
            "backend": settings.backend,
            "model": settings.model_id,
        }

    @mcp.tool
    def llm_security_policy() -> dict[str, int | bool]:
        """Return request guardrail limits exposed to MCP clients."""
        return {
            "prompt_guard_enabled": settings.prompt_guard_enabled,
            "prompt_max_chars": settings.prompt_max_chars,
            "max_tokens_limit": settings.max_tokens_limit,
            "request_body_limit_bytes": settings.request_body_limit_bytes,
            "response_text_limit_chars": settings.response_text_limit_chars,
        }

    @mcp.tool
    def mcp_tool_manifest() -> dict:
        """Return signed manifest metadata for exposed MCP tools."""
        return manifest_payload(settings)

    return mcp
