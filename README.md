# ThaiLLM Backend API

FastAPI inference gateway for ThaiLLM. OpenAI-compatible endpoints, prompt-injection guardrails, API key auth, rate limiting, and a read-only MCP surface.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Backend readiness |
| `GET` | `/version` | API version + active backend + model |
| `POST` | `/v1/completions` | Text completion |
| `POST` | `/v1/chat/completions` | Chat completion |
| `*` | `/mcp/` | MCP server (requires MCP client) |

## Setup

```bash
uv sync
cp .env.example .env
# edit .env: set THAILLM_UPSTREAM_BASE_URL and THAILLM_UPSTREAM_API_KEY
make dev
```

For local testing without an upstream: set `THAILLM_BACKEND=fake` in `.env`.

## Make Targets

| Target | What it does |
|--------|-------------|
| `make install` | Install dependencies |
| `make dev` | Dev server with hot-reload at `127.0.0.1:8000` |
| `make run` | Production server |
| `make test` | Full test suite |
| `make test-unit` | Unit tests only (`tests/unit/`) |
| `make test-integration` | Integration tests only (`tests/integration/`) |
| `make cover` | Tests + coverage report |
| `make docker-build` | Build Docker image `thaillm-backend` |
| `make clean` | Remove `__pycache__`, `.pytest_cache`, `.coverage`, `htmlcov` |

## Docker

```bash
make docker-build
docker run --rm -p 8000:8000 --env-file .env thaillm-backend
```

## Configuration

All settings use `THAILLM_` prefix. Set via `.env` or environment variables.

| Variable | Default | Notes |
|----------|---------|-------|
| `THAILLM_BACKEND` | `fake` | `fake` or `openai_compatible` |
| `THAILLM_MODEL_ID` | `ThaiLLM/ThaiLLM-8B-SFT-IQ` | Passed to upstream |
| `THAILLM_UPSTREAM_BASE_URL` | — | Required when backend is `openai_compatible` |
| `THAILLM_UPSTREAM_API_KEY` | — | Bearer token for upstream |
| `THAILLM_API_KEYS` | — | CSV or JSON list — enforces auth on `/v1` and `/mcp` |
| `THAILLM_ALLOWED_ORIGINS` | — | CORS + MCP origin allowlist |
| `THAILLM_TRUSTED_HOSTS` | — | Rejected if request host not in list |
| `THAILLM_REQUEST_BODY_LIMIT_BYTES` | `64000` | |
| `THAILLM_RATE_LIMIT_PER_MINUTE` | `60` | Per client, in-memory, single-process |
| `THAILLM_MAX_TOKENS_DEFAULT` | `512` | Used when request omits `max_tokens` |
| `THAILLM_MAX_TOKENS_LIMIT` | `2048` | Hard ceiling, enforced server-side |
| `THAILLM_PROMPT_GUARD_ENABLED` | `true` | Prompt-injection detection |
| `THAILLM_PROMPT_MAX_CHARS` | `20000` | |
| `THAILLM_RESPONSE_TEXT_LIMIT_CHARS` | `20000` | |
| `THAILLM_MCP_ENABLED` | `true` | Mount MCP server at `/mcp` |
| `THAILLM_MCP_MANIFEST_SIGNING_KEY` | — | HMAC key for tool manifest signature |

`THAILLM_API_KEYS`, `THAILLM_ALLOWED_ORIGINS`, `THAILLM_TRUSTED_HOSTS` accept CSV (`a,b`) or JSON list (`["a","b"]`).

## Security Checklist

- [ ] Set `THAILLM_API_KEYS` before exposing to the internet
- [ ] Set `THAILLM_TRUSTED_HOSTS` to your domain
- [ ] Set `THAILLM_ALLOWED_ORIGINS` if browser clients use MCP
- [ ] Store `THAILLM_MCP_MANIFEST_SIGNING_KEY` in a secret manager — never commit it
- [ ] Never commit `.env` (already gitignored)
- [ ] Run behind a reverse proxy that handles TLS
