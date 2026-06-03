"""Chat client: local Ollama by default; OpenRouter when the model id contains '/'.
The API key is read from the OPENROUTER_API_KEY env var (never stored on disk)."""
import json
import os
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _openrouter(messages, model, temperature, timeout):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": 1500}
    req = urllib.request.Request(
        OPENROUTER_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data["choices"][0]["message"].get("content") or "").strip()


def chat(messages, model="gemma3:4b", temperature=0.0, num_ctx=8192, timeout=240):
    if "/" in model:  # OpenRouter-style id, e.g. "qwen/qwen3.5-27b"
        return _openrouter(messages, model, temperature, timeout)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    req = urllib.request.Request(
        OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"]
