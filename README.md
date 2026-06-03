# LLM Inference Gateway

FastAPI inference gateway with OpenAI-compatible endpoints, prompt-injection guardrails, and API-key auth. Proxies requests to any OpenAI-compatible upstream, or runs a built-in fake backend for local development.

## Requirements

- Python 3.11 and [uv](https://docs.astral.sh/uv/)
- Docker (for containerized deployment)
- For the agent back-test endpoint: a DuckDB database file (mounted at runtime) and the bundled agent code in `agent_src/`

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

## Competition Endpoint (ThaiLLM back-test)

`POST /agent/thaillm` — no API key required; the scoring server calls this directly.

**Request**
```json
{"question": "ราคา MSRP ของ NT-LT-001 คือเท่าไหร่"}
```

**Response**
```json
{"id": "550e8400-e29b-41d4-a716-446655440000", "answer": "45900", "total_output_token_count": 312}
```

- `id` — UUID generated per request; used as the audit trail filename
- `answer` — agent answer in Thai or English
- `total_output_token_count` — output tokens consumed (used in cost scoring)

Each request writes `{id}.txt` (the agent reasoning trace) to `LLM_AUDIT_TRAIL_DIR`.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_AUDIT_TRAIL_DIR` | `audit_trails` | Directory for `{id}.txt` audit files (set to a writable path, e.g. `/data/audit_trails`) |
| `LLM_AGENT_DB_PATH` | `""` | Path to the DuckDB database file the agent queries |
| `LLM_AGENT_SRC_PATH` | `""` | Path to the directory containing the agent modules (`agent.py`, `tools.py`, …) |
| `LLM_THAILLM_BASE_URL` | — | ThaiLLM upstream base URL (OpenAI-compatible) |
| `LLM_THAILLM_MODEL_ID` | `""` | ThaiLLM model name |
| `LLM_THAILLM_API_KEY` | — | ThaiLLM API key |
| `PORT` | `8000` | Container listen port; the deploy platform maps host:`YOUR_PORT` → this port |

### Running the agent back-test

The `/agent/thaillm` endpoint runs a ReAct SQL agent (bundled in `agent_src/`, copied into the image at `/agent/src`) against a DuckDB database. The database is **not** part of the image — mount it read-only at runtime:

```bash
make docker-build
docker run -d --name llm-gateway -p 8000:8000 \
  -e LLM_BACKEND=openai_compatible \
  -e LLM_UPSTREAM_BASE_URL=https://your-thaillm-host/v1 \
  -e LLM_UPSTREAM_API_KEY=YOUR_KEY \
  -e LLM_MODEL_ID=your-model-id \
  -e LLM_THAILLM_BASE_URL=https://your-thaillm-host/v1 \
  -e LLM_THAILLM_MODEL_ID=your-model-id \
  -e LLM_THAILLM_API_KEY=YOUR_KEY \
  -v /path/to/your.duckdb:/data/agent.duckdb:ro \
  llm-gateway
```

`LLM_AGENT_SRC_PATH` (`/agent/src`), `LLM_AGENT_DB_PATH` (`/data/agent.duckdb`), and `LLM_AUDIT_TRAIL_DIR` (`/data/audit_trails`) already default to in-image paths via the Dockerfile, so only the upstream/model/key env and the database mount are required.

> **Build prerequisite:** `agent_src/` is intentionally excluded from version control (competition code), so a fresh clone has no agent modules. Place `agent.py`, `tools.py`, `ollama_client.py`, and `refusal.py` into `agent_src/` before `make docker-build`, or the `COPY agent_src/` step will fail.

**Evaluator connectivity:** the scoring server POSTs to `http(s)://<host>:<port>/agent/thaillm`. Host and port are assigned by the deployment platform's port mapping — set `PORT` (or keep the default `8000`) to match the in-container port the platform maps, and expose `/agent/thaillm`. No external URL is hardcoded in the code.

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

## Project Layout

```
app/
  main.py            create_app(); ASGI object `app`
  core/settings.py   all settings (LLM_ prefix)
  api/               routers: /v1 inference + /agent/thaillm
  services/          inference, agent bridge, audit trail
  backends/          fake + openai_compatible (factory-selected)
  schemas/           request/response models
  middleware.py      request-id, logging, guards
agent_src/           bundled ReAct agent (agent.py, tools.py, ...); DuckDB, copied to /agent/src in the image
scripts/             benchmark_thaillm.py (evaluation harness)
tests/               unit + integration (112 tests)
Dockerfile           multi-worker image; bundles agent_src, creates writable /data
```

## Security Checklist

- [ ] Set `LLM_API_KEYS` before exposing to the internet
- [ ] Set `LLM_TRUSTED_HOSTS` to your domain
- [ ] Set `LLM_ALLOWED_ORIGINS` for browser clients
- [ ] Never commit `.env` (already gitignored)
- [ ] Run behind a reverse proxy that terminates TLS
