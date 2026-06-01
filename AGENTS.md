## Setup commands

```bash
uv sync                  # install all deps (including dev)
cp .env.example .env     # configure upstream URL + API key
make dev                 # start server with hot-reload on :8000
make test                # run full test suite
```

For unit tests only: `make test-unit`
For integration tests only: `make test-integration`
Coverage report: `make cover`

## Code style
- Python with pydantic
- Use functional patterns where possible
- Create API for inference backend model that can plug new and switch
- Version Check and Health Check