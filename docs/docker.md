# Docker — mcp-agent

## Run locally (single command)

```bash
# Build image
docker compose build

# Check NuGet versions
docker compose run --rm check-versions

# Analyze pending releases
docker compose run --rm analyze
```

## Environment variables

All secrets are passed via `.env` (never hardcoded). Copy the template:

```bash
cp .env.example .env
# fill in ASPOSE_LLM_TOKEN
```

| Variable | Required | Description |
|---|---|---|
| `ASPOSE_LLM_TOKEN` | Yes (Aspose scripts) | Aspose LLM gateway token |
| `ANTHROPIC_API_KEY` | No | Only for `analyze_release.py` (non-Aspose variant) |

## Volume behavior

`products.json` is bind-mounted from the host into the container:
```yaml
volumes:
  - ./products.json:/app/products.json
```

This means changes made by `check_nuget.py` inside the container are written back to
the host file immediately. No data is lost when the container exits.

## Healthcheck

The default service checks that `products.json` is valid JSON every 30 seconds:
```
python -c "import json; json.load(open('products.json')); print('ok')"
```

## Run without Docker

```bash
cp .env.example .env
# fill in tokens
bash scripts/run.sh check       # check NuGet versions
bash scripts/run.sh analyze     # analyze releases
bash scripts/run.sh test        # run pytest
```

## Run tests in container

```bash
docker compose run --rm mcp-agent python -m pytest tests/ -v
```
