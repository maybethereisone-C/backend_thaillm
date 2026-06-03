FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system llm && useradd --system --gid llm --home-dir /app llm

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY agent_src/ /agent/src/

ENV LLM_AGENT_SRC_PATH=/agent/src \
    LLM_AGENT_DB_PATH=/data/agent.duckdb \
    LLM_AUDIT_TRAIL_DIR=/data/audit_trails

RUN mkdir -p /data/audit_trails && chown -R llm:llm /data

USER llm

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('PORT', '8000'))"

# Shell form so ${PORT} is honored at runtime; defaults to 8000. The deploy platform
# maps an external host port to this in-container port.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4 --loop uvloop --http httptools
