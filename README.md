# LLM Inference Gateway

FastAPI service exposing a ReAct agent endpoint for the ThaiLLM competition. Wraps the FahMai DuckDB agent with an HTTP API, prompt-injection sanitization, and per-request audit trails.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Service liveness |
| `GET` | `/version` | none | API version and configured model |
| `POST` | `/agent/thaillm` | none | Run the ReAct agent (competition scoring endpoint) |

## Requirements

- Python 3.11 and [uv](https://docs.astral.sh/uv/)
- Docker (for containerized deployment)
- A DuckDB database file (mounted at runtime)
- The agent source modules in `agent_src/`

## Setup

```bash
uv sync
cp .env.example .env
# edit .env: set LLM_THAILLM_BASE_URL, LLM_THAILLM_MODEL_ID, LLM_THAILLM_API_KEY
# set LLM_AGENT_SRC_PATH and LLM_AGENT_DB_PATH to local paths
```

## Running

```bash
make dev    # development server with hot-reload (127.0.0.1:8000)
make run    # production-settings server
```

**Docker (recommended for deployment):**

```bash
make docker-build
docker run -d --name llm-gateway -p 8000:8000 \
  -e LLM_THAILLM_BASE_URL=https://your-thaillm-host/v1 \
  -e LLM_THAILLM_MODEL_ID=your-model-id \
  -e LLM_THAILLM_API_KEY=YOUR_KEY \
  -v /path/to/your.duckdb:/data/agent.duckdb:ro \
  llm-gateway
```

`LLM_AGENT_SRC_PATH` (`/agent/src`), `LLM_AGENT_DB_PATH` (`/data/agent.duckdb`), and `LLM_AUDIT_TRAIL_DIR` (`/data/audit_trails`) default to in-image paths via the Dockerfile.

## Competition Endpoint

`POST /agent/thaillm` — no API key required; the scoring server calls this directly.

**Request:**
```json
{"question": "ราคา MSRP ของ NT-LT-001 คือเท่าไหร่"}
```

**Response:**
```json
{"id": "550e8400-e29b-41d4-a716-446655440000", "answer": "45900", "total_output_token_count": 312}
```

- `id` — UUID generated per request; used as the audit trail filename
- `answer` — agent answer in Thai or English
- `total_output_token_count` — output tokens consumed

Each request writes `{id}.txt` (the agent reasoning trace) to `LLM_AUDIT_TRAIL_DIR`.

## Configuration

All settings use the `LLM_` prefix. Set via `.env` or environment variables.

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_THAILLM_BASE_URL` | — | ThaiLLM upstream base URL (OpenAI-compatible) |
| `LLM_THAILLM_MODEL_ID` | `""` | Model name |
| `LLM_THAILLM_API_KEY` | — | Bearer token for the upstream |
| `LLM_AGENT_SRC_PATH` | `""` | Directory containing `agent.py`, `tools.py`, … |
| `LLM_AGENT_DB_PATH` | `""` | Path to the DuckDB database file |
| `LLM_AUDIT_TRAIL_DIR` | `audit_trails` | Directory for `{id}.txt` audit files |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `60` | Upstream request timeout |
| `LLM_ALLOWED_ORIGINS` | — | CORS origin allowlist |
| `LLM_TRUSTED_HOSTS` | — | Reject requests whose `Host` is not in this list |
| `LLM_PROMPT_GUARD_ENABLED` | `true` | Prompt-injection detection |
| `PORT` | `8000` | Container listen port |

`LLM_ALLOWED_ORIGINS` and `LLM_TRUSTED_HOSTS` accept CSV (`a,b`) or JSON list (`["a","b"]`).

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

## Project Layout

```
app/
  main.py            create_app(); ASGI object `app`
  core/settings.py   all settings (LLM_ prefix)
  api/               routers: /health /version /agent/thaillm
  services/          agent bridge (agent_service), audit trail
  schemas/           request/response models
  middleware.py      request-id, audit logging, security headers
agent_src/           ReAct agent (agent.py, tools.py, …); copied to /agent/src in the image
scripts/             benchmark harnesses (gitignored)
tests/               unit + integration
Dockerfile           multi-worker image; bundles agent_src, creates writable /data
```

## Security

- Run behind a reverse proxy that terminates TLS
- Set `LLM_TRUSTED_HOSTS` to your domain
- Set `LLM_ALLOWED_ORIGINS` for browser clients
- Never commit `.env` (already gitignored)

> **Build prerequisite:** `agent_src/` is gitignored (competition code). Place `agent.py`, `tools.py`, `ollama_client.py`, and `refusal.py` into `agent_src/` before `make docker-build`.
