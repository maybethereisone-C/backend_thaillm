# LLM Inference Gateway

FastAPI inference gateway with OpenAI-compatible endpoints, prompt-injection guardrails, and API-key auth. Proxies requests to any OpenAI-compatible upstream, or runs a built-in fake backend for local development.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Backend readiness |
| `GET` | `/version` | API version, active backend, and model |
| `POST` | `/v1/completions` | Text completion |
| `POST` | `/v1/chat/completions` | Chat completion |

## Setup

```bash
uv sync
cp .env.example .env
# edit .env: set LLM_UPSTREAM_BASE_URL and LLM_UPSTREAM_API_KEY
```

For local testing without an upstream, set `LLM_BACKEND=fake` in `.env`.

## Running

The ASGI application object is `app` in `app/main.py` (`app.main:app`).

**Local (development, hot-reload):**

```bash
make dev
# = uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

**Local (production settings, no reload):**

```bash
make run
# = uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Server (Docker, recommended):**

```bash
make docker-build
docker run --rm -p 8000:8000 --env-file .env llm-gateway
```

**Server (without Docker):**

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --loop uvloop --http httptools
```

Run behind a reverse proxy that terminates TLS. The container image already uses the multi-worker command above as its entrypoint.

## API Usage

If `LLM_API_KEYS` is set, send the key on `/v1/*` requests via either the `x-api-key` header or `Authorization: Bearer <key>`. `/health` and `/version` are always open.

**Health and version:**

```bash
curl http://localhost:8000/health
curl http://localhost:8000/version
```

**Text completion:**

```bash
curl -X POST http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_KEY" \
  -d '{
        "prompt": "Explain what an API gateway does.",
        "max_tokens": 256,
        "temperature": 0.4,
        "top_p": 0.95
      }'
```

Response:

```json
{
  "model": "default",
  "choices": [
    { "index": 0, "text": "...", "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 6, "completion_tokens": 42 }
}
```

**Chat completion:**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_KEY" \
  -d '{
        "messages": [
          { "role": "system", "content": "You are concise." },
          { "role": "user", "content": "Summarize TCP in one sentence." }
        ],
        "max_tokens": 128
      }'
```

Response:

```json
{
  "model": "default",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "..." },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 18, "completion_tokens": 20 }
}
```

`model` is optional. Omit it or set it to `"default"` and the gateway forwards `LLM_MODEL_ID` to the upstream automatically. Errors return a structured body: `{"error": {"code": ..., "message": ..., "request_id": ...}}`.

Interactive API docs are served at `/docs` (Swagger UI) and `/redoc`.

## Make Targets

| Target | What it does |
|--------|-------------|
| `make install` | Install dependencies |
| `make dev` | Dev server with hot-reload at `127.0.0.1:8000` |
| `make run` | Production-settings server |
| `make test` | Full test suite |
| `make test-unit` | Unit tests only (`tests/unit/`) |
| `make test-integration` | Integration tests only (`tests/integration/`) |
| `make cover` | Tests + coverage report |
| `make docker-build` | Build Docker image `llm-gateway` |
| `make clean` | Remove `__pycache__`, `.pytest_cache`, `.coverage`, `htmlcov` |

## Configuration

All settings use the `LLM_` prefix. Set them via `.env` or environment variables.

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_BACKEND` | `fake` | `fake` or `openai_compatible` |
| `LLM_MODEL_ID` | `default` | Model sent to upstream when request omits `model` or sends `"default"` |
| `LLM_UPSTREAM_BASE_URL` | — | Required when backend is `openai_compatible` |
| `LLM_UPSTREAM_API_KEY` | — | Bearer token for the upstream |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `60` | Upstream request timeout |
| `LLM_API_KEYS` | — | CSV or JSON list — enforces auth on `/v1` |
| `LLM_ALLOWED_ORIGINS` | — | CORS origin allowlist |
| `LLM_TRUSTED_HOSTS` | — | Request rejected if its host is not in the list |
| `LLM_MAX_TOKENS_DEFAULT` | `512` | Used when a request omits `max_tokens` |
| `LLM_PROMPT_GUARD_ENABLED` | `true` | Prompt-injection detection |

`LLM_API_KEYS`, `LLM_ALLOWED_ORIGINS`, and `LLM_TRUSTED_HOSTS` accept either CSV (`a,b`) or a JSON list (`["a","b"]`).

## Security Checklist

- [ ] Set `LLM_API_KEYS` before exposing to the internet
- [ ] Set `LLM_TRUSTED_HOSTS` to your domain
- [ ] Set `LLM_ALLOWED_ORIGINS` for browser clients
- [ ] Never commit `.env` (already gitignored)
- [ ] Run behind a reverse proxy that terminates TLS
