"""Agent service: bridges the fahmai_db_agent ReAct pipeline into the gateway.

The agent package lives outside this project. Its source directory is added
to sys.path at runtime, then the ``agent`` and ``ollama_client`` modules are
imported once and cached. Per call, ``agent.chat`` is replaced with a
closure that calls the configured ThaiLLM endpoint and accumulates output
tokens. The original binding is restored in a finally block.

Runs are serialized by a lock because ``agent.chat`` is a single shared
module-level name that cannot be safely overwritten by concurrent callers.
"""
import asyncio
import json
import threading
import types
from dataclasses import dataclass

_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_MAX_TOKENS = 1500
_DEFAULT_NUM_CTX = 8192

_IMPORT_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()

_AGENT_MODULE: types.ModuleType | None = None
_OLLAMA_MODULE: types.ModuleType | None = None


@dataclass
class AgentConfig:
    model_id: str
    base_url: str
    api_key: str | None = None
    agent_db_path: str = ""
    agent_src_path: str = ""
    timeout: float = 300.0


def _load_agent_modules(agent_src_path: str) -> tuple[types.ModuleType, types.ModuleType]:
    global _AGENT_MODULE, _OLLAMA_MODULE
    if _AGENT_MODULE is not None and _OLLAMA_MODULE is not None:
        return _AGENT_MODULE, _OLLAMA_MODULE
    with _IMPORT_LOCK:
        if _AGENT_MODULE is None or _OLLAMA_MODULE is None:
            import sys
            if agent_src_path not in sys.path:
                sys.path.insert(0, agent_src_path)
            import agent
            import ollama_client
            _AGENT_MODULE = agent
            _OLLAMA_MODULE = ollama_client
    return _AGENT_MODULE, _OLLAMA_MODULE


def _sanitize_question(question: str) -> str:
    """Strip encoding obfuscation artifacts before passing to the agent.

    Removes null bytes and zero-width characters that can be used to smuggle
    prompt injection payloads past text-based filters (OWASP LLM cheat sheet,
    encoding/obfuscation attack vector).
    """
    return (
        question
        .replace("\x00", "")
        .replace("​", "")
        .replace("‌", "")
        .replace("‍", "")
        .replace("﻿", "")
        .strip()
    )


def _make_chat(config: AgentConfig, token_counter: list[int]):
    """Return a chat function that calls the ThaiLLM OpenAI-compatible endpoint."""
    url = f"{config.base_url.rstrip('/')}/chat/completions"

    def chat(messages, model=config.model_id, temperature=_DEFAULT_TEMPERATURE,
             num_ctx=_DEFAULT_NUM_CTX, timeout=config.timeout):
        import urllib.request as _req

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": _DEFAULT_MAX_TOKENS,
        }
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        req = _req.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with _req.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        usage = data.get("usage") or {}
        token_counter[0] += int(usage.get("completion_tokens", 0) or 0)
        choices = data.get("choices") or [{}]
        message = (choices[0] if isinstance(choices[0], dict) else {}).get("message") or {}
        return (message.get("content") or "").strip()

    return chat


async def run_agent(question: str, config: AgentConfig) -> tuple[str, int, str]:
    """Run the ReAct agent and return (answer, total_output_token, trace_json)."""
    if not config.agent_src_path:
        raise ValueError(
            "AgentConfig.agent_src_path is empty; "
            "set LLM_AGENT_SRC_PATH to the directory containing agent.py"
        )

    sanitized = _sanitize_question(question)
    if not sanitized:
        raise ValueError("question is empty after sanitization")

    agent_module, ollama_module = _load_agent_modules(config.agent_src_path)
    token_counter: list[int] = [0]
    patched = _make_chat(config, token_counter)

    def _invoke() -> dict:
        with _RUN_LOCK:
            orig_agent = agent_module.chat
            orig_client = ollama_module.chat
            agent_module.chat = patched
            ollama_module.chat = patched
            try:
                return agent_module.run_agent(
                    sanitized,
                    config.agent_db_path,
                    model=config.model_id,
                )
            finally:
                agent_module.chat = orig_agent
                ollama_module.chat = orig_client

    result = await asyncio.to_thread(_invoke)
    answer = str(result.get("answer", ""))
    trace_text = json.dumps(result.get("trace", []), ensure_ascii=False)
    return answer, token_counter[0], trace_text
