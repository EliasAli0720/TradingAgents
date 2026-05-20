# Web Development

## Services

- React frontend: `apps/web`
- FastAPI backend: `tradingagents.api.app:app`
- Worker: `python -m tradingagents.worker.runner`
- Queue: Redis

## Local Development

Install Python dependencies:

```bash
uv sync --python /usr/local/bin/python3.13
```

Run API:

```bash
uv run uvicorn tradingagents.api.app:app --reload --port 8000
```

Run worker:

```bash
uv run python -m tradingagents.worker.runner
```

Run frontend:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173`.

## Docker Compose

Run the web stack:

```bash
TRADINGAGENTS_API_TOKEN=dev-token docker compose up redis api worker web
```

The existing CLI Docker services remain available:

```bash
docker compose run --rm tradingagents
docker compose --profile ollama run --rm tradingagents-ollama
```

## Authentication

Set `TRADINGAGENTS_API_TOKEN` in `.env`. Use that token in the web login screen.

## Safe Defaults

Use `TRADINGBOT_BROKER=mock` while developing. Do not enable live broker credentials until manual trade and approval audit paths have been verified.
