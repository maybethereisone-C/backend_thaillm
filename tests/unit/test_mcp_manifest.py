from app.core.settings import Settings
from app.mcp_manifest import manifest_payload


def test_mcp_manifest_has_hash_and_tool_permissions() -> None:
    payload = manifest_payload(Settings())

    assert payload["sha256"]
    assert payload["signature"] is None
    assert {tool["name"] for tool in payload["tools"]} == {
        "version_info",
        "llm_security_policy",
        "mcp_tool_manifest",
    }
    assert all(tool["permissions"] for tool in payload["tools"])


def test_mcp_manifest_signature_when_key_configured() -> None:
    payload = manifest_payload(Settings(mcp_manifest_signing_key="signing-secret"))

    assert payload["signature"]
