## Project

**LLM Inference Gateway** — thin, stateless FastAPI proxy in front of an OpenAI-compatible
upstream model server. Adds API-key auth, prompt/output guardrails, structured error
handling, and a competition back-test endpoint that runs a ReAct agent against a DuckDB
database.

## Setup

```bash
uv sync                  # install all deps (including dev)
cp .env.example .env     # fill in upstream URL + API keys
make dev                 # start server with hot-reload on :8000
make test                # full test suite
make test-unit           # unit tests only
make test-integration    # integration tests only
make cover               # tests + coverage report
```

## Key env vars (LLM_ prefix)

| Variable | Required | Purpose |
|---|---|---|
| `LLM_MODEL_ID` | no | Model ID forwarded to upstream |
| `LLM_API_KEYS` | no | Comma-separated gateway API keys |
| `LLM_TRUSTED_HOSTS` | no | Comma-separated allowed hostnames |
| `LLM_ALLOWED_ORIGINS` | no | Comma-separated CORS origins |
| `LLM_PROMPT_GUARD_ENABLED` | no | Default `true` |
| `LLM_AGENT_SRC_PATH` | competition | Dir containing `agent.py`, `tools.py`, `ollama_client.py` |
| `LLM_AGENT_DB_PATH` | competition | Path to `fahmai.duckdb` |
| `LLM_AUDIT_TRAIL_DIR` | competition | Writable dir for per-request trace JSON |
| `LLM_THAILLM_BASE_URL` | competition | ThaiLLM OpenAI-compatible endpoint |
| `LLM_THAILLM_MODEL_ID` | competition | Model ID for ThaiLLM calls |
| `LLM_THAILLM_API_KEY` | competition | Bearer token for ThaiLLM endpoint |

## Layout

```
app/
  main.py                    # create_app(); ASGI entry point
  core/
    settings.py              # Settings (pydantic-settings, LLM_ prefix)
    security.py              # PromptInjectionGuard, OutputGuard, API-key check
    audit.py                 # structured logging config
    errors.py                # AppError base class
  api/
    routes_health.py         # GET /health
    routes_inference.py      # POST /v1/chat/completions  (API-key protected)
    routes_competition.py    # POST /agent/thaillm        (no auth)
  backends/
    base.py                  # Backend protocol
    fake.py                  # Stub backend for tests
    openai_compatible.py     # Real upstream backend
    factory.py               # Selects backend from settings
  services/
    inference_service.py     # Applies guards, calls backend
    agent_service.py         # Bridges ReAct pipeline; patches agent.chat at runtime
    audit_service.py         # Writes per-request audit trail JSON
  schemas/
    inference.py             # Chat request/response schemas
    health.py                # Health response schema
    competition.py           # AgentRequest / AgentResponse
  middleware.py              # RequestId, AuditLog, SecurityHeaders, ApiKeyAuth
agent_src/                   # ReAct agent modules (loaded via LLM_AGENT_SRC_PATH)
  agent.py                   # run_agent() entry point + system prompt
  tools.py                   # DuckDB tool wrappers
  ollama_client.py           # chat() shim (patched at runtime by agent_service)
  refusal.py                 # Refusal helpers
scripts/
  benchmark_thaillm.py       # Offline benchmark harness (not part of the server)
tests/
  unit/                      # Isolated unit tests
  integration/               # Full-stack integration tests (TestClient)
```

## Middleware stack (outer → inner)

RequestId → AuditLog → SecurityHeaders → ApiKeyAuth  
(add_middleware prepends, so last-added runs outermost inbound)

Optional: CORSMiddleware (if `LLM_ALLOWED_ORIGINS` set), TrustedHostMiddleware (if `LLM_TRUSTED_HOSTS` set).

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness check |
| GET | `/version` | none | Service version |
| POST | `/agent/thaillm` | none | ReAct agent back-test (competition scoring) |

## Rules

- Names stay generic: `LLM_` prefix, `llm-gateway` image, "LLM Inference Gateway" title. No product/vendor names.
- Secrets live in `.env` only. Never log full keys — mask to `key_prefix`.
- No rate limiting or request-size caps here (serving team owns those).
- No MCP server (removed by design).
- Run guards (`PromptInjectionGuard` / `OutputGuard`) on any path carrying user or model text.
- `make test` must stay green before merging.
- When adding a setting: update `settings.py`, `README.md` config table, and `.env.example` together.
- Docker entrypoint calls the venv binary directly — not `uv run` (non-root user cannot write uv cache).

## Code style

- Python + FastAPI + pydantic-settings
- Type annotations on all function signatures
- Async endpoints for I/O; blocking work in `asyncio.to_thread`
- Functional patterns where possible; immutable data structures preferred
