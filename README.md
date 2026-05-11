# mcp-agent

Central version tracker and upgrade automation for Aspose .NET MCP servers.
Detects new NuGet releases, analyzes them with an LLM, and upgrades local repos.

## Architecture

### Existing product — version update flow

> Scripts shown with `_aspose` suffix. Drop the suffix and set `ANTHROPIC_API_KEY` to use Claude API instead.

```
                        ┌─────────────────────────────────────────────┐
                        │              GitHub Actions (weekly)         │
                        └──────────────────┬──────────────────────────┘
                                           │
                                    check_nuget.py
                                           │ polls NuGet API
                                           ▼
                                    products.json  ◄─── state (current/previous version)
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                     new version detected?         no change
                              │                         │
                              ▼                         ▼
                  analyze_release_aspose.py           (done)
                              │
                    ┌─────────┴──────────┐
                    │   ReAct loop       │
                    │  ACT → OBSERVE     │
                    │  (up to 3 iters)   │
                    └─────────┬──────────┘
                              │
                   confidence ≥ 0.7?
                    ┌─────────┴──────────┐
                    YES                  NO
                    │                    │
                    ▼                    ▼
           safe_to_merge?        ⚠ ESCALATE
          ┌──────┴──────┐       (manual review)
         YES             NO
          │               │
   upgrade_product.py   implement new MCP tools
   (bump .csproj,        then upgrade_product.py
    dotnet build,
    dotnet test,
    git push)
```

### New product — onboarding flow

```
   analyze_new_product_aspose.py
   (fetches Aspose docs, LLM designs tool map)
                  │
                  ▼
            tool-map.md
                  │
                  ▼
        new_product.py
        (scaffold project, create GitHub repo,
         register in products.json)
                  │
                  ▼
        implement tools in Claude Code
        (using tool-map.md as spec)
                  │
                  ▼
        version tracking starts automatically
        (check_nuget.py picks it up next Monday)
```

## State Model

`products.json` tracks per-product state:

```
(no previous_version)          ← up to date, nothing to do
          │
          │  check_nuget.py detects new version
          ▼
previous_version ≠ current_version   ← PENDING analysis
          │
          │  analyze_release_aspose.py
          ▼
    safe_to_merge + confidence        ← ANALYZED
          │
     ┌────┴────┐
  safe        not safe / low confidence
     │              │
     ▼              ▼
 upgrade_product  manual review → implement tools
     │
     ▼
  pushed → previous_version cleared  ← DONE
```

## Quick Start

### Choose your LLM mode

**Mode 1 — Claude Code CLI** �recommended if you don't have an Aspose token
```bash
# No API key needed — pipes the prepared prompt directly into Claude Code
python scripts/analyze_release.py --prepare | claude -p
python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words" --prepare | claude -p
```

**Mode 2 — Aspose LLM** (recommended for Aspose employees)
```bash
# .env
ASPOSE_LLM_TOKEN=your-token

python scripts/analyze_release_aspose.py
python scripts/analyze_new_product_aspose.py --slug words --nuget "Aspose.Words" --output tool-map.md
```

**Mode 3 — Anthropic API** (if you have an ANTHROPIC_API_KEY)
```bash
# .env
ANTHROPIC_API_KEY=your-key

python scripts/analyze_release.py
python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words" --output tool-map.md
```

---

### Full workflow

```bash
# ── Existing product: version update ──────────────────────────────
python scripts/check_nuget.py                  # detect new versions
python scripts/analyze_release_aspose.py       # analyze what changed (pick your mode above)
python scripts/upgrade_product.py \
    --repos-dir /path/to/repos                 # build, test, push

# ── New product: onboarding ────────────────────────────────────────
python scripts/analyze_new_product_aspose.py \
    --slug words --nuget "Aspose.Words" \
    --output tool-map.md                       # generate tool map (pick your mode above)

python scripts/new_product.py \
    --slug words --nuget "Aspose.Words" --version "25.1.0" \
    --output-dir /path/to/repos \
    --github-user <your-org> --create-repo     # scaffold + push
```

## Scripts

### Existing product — version updates

| Script | Purpose |
|---|---|
| `check_nuget.py` | Poll NuGet API, update `products.json`, create GitHub Issue |
| `analyze_release_aspose.py` | Fetch release notes, ReAct LLM analysis + confidence scoring — **Mode 2** |
| `analyze_release.py` | Same — **Mode 1** (`--prepare \| claude -p`) or **Mode 3** (Anthropic API) |
| `merge_dependabot_aspose.py` | Find Dependabot PRs, LLM safe/unsafe decision, optional auto-merge — **Mode 2** |
| `merge_dependabot.py` | Same — **Mode 1** (`--prepare \| claude -p`) or **Mode 3** |
| `upgrade_product.py` | Bump `.csproj`, `dotnet build`, `dotnet test`, commit, push |

### New product — onboarding

| Script | Purpose |
|---|---|
| `analyze_new_product_aspose.py` | Fetch Aspose docs, generate tool-map.md via Aspose LLM — **Mode 2** |
| `analyze_new_product.py` | Same — **Mode 1** (`--prepare \| claude -p`) or **Mode 3** (Anthropic API) |
| `new_product.py` | Scaffold full project structure, create GitHub repo, register in `products.json` |

## Configuration

| File | Purpose |
|---|---|
| `products.json` | Tracked products with NuGet package names and version state |
| `.env` | `ASPOSE_LLM_TOKEN` — gitignored, see `.env.example` |

## Tracked Products

| Product | NuGet | MCP Repo |
|---|---|---|
| Aspose.Font | `Aspose.Font` | `aspose/aspose-font-mcp` |
| Aspose.ZIP  | `Aspose.ZIP`  | `aspose/aspose-zip-mcp`  |
| Aspose.Note | `Aspose.Note` | `aspose/aspose-note-mcp` |
| Aspose.PUB  | `Aspose.PUB`  | `aspose/aspose-pub-mcp`  |

## Adding a New Product

```bash
# Step 1 — generate tool map from Aspose docs
python scripts/analyze_new_product_aspose.py \
    --slug words --nuget "Aspose.Words" --output tool-map.md
# alternative: python scripts/analyze_new_product.py ... (uses ANTHROPIC_API_KEY)

# Step 2 — scaffold project, create GitHub repo, register in products.json
python scripts/new_product.py \
    --slug words --nuget "Aspose.Words" --version "25.1.0" \
    --output-dir /path/to/repos \
    --github-user <your-org> --create-repo

# Step 3 — implement tools in Claude Code (use tool-map.md as spec)
# Step 4 — version tracking starts automatically next Monday
```

See `docs/how-it-works.md` for a full walkthrough of every script, git automation, and CI workflows.
See `docs/new-product-analysis-template.md` for the full analysis guide.
See `docs/mcp-server-standards.md` for MCP protocol rules, error contract, and the quality checklist.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v          # 99 tests, ~3s
```

Four test modules — all pure unit tests, no network or filesystem:

| Module | Covers |
|---|---|
| `tests/test_check_nuget.py` | Issue body formatting, bold versions, no backticks |
| `tests/test_analyze_release.py` | URL generation, HTML parser, JSON validation, ReAct schema |
| `tests/test_hitl_and_outcomes.py` | Escalation logic, `_print_result`, `_update_product_fields`, csproj patching |
| `tests/test_new_product.py` | Naming conventions, csproj/sln templates, scaffold, gitignore, CI template |

## Docker

```bash
docker compose build

# Run specific tasks
docker compose run --rm check-versions   # check NuGet versions
docker compose run --rm analyze          # analyze pending releases
```

See `docs/docker.md` for volume behavior, env vars, and healthcheck details.

## One-command runner (local)

```bash
bash scripts/run.sh check                            # check NuGet versions
bash scripts/run.sh analyze                          # analyze releases
bash scripts/run.sh analyze --product zip            # specific product
bash scripts/run.sh upgrade --repos-dir /path/to/repos  # upgrade local repos
bash scripts/run.sh new --slug svg --nuget "Aspose.SVG"  # generate tool map
bash scripts/run.sh test                             # run pytest
```

## CI

GitHub Actions runs two workflows:
- **`ci.yml`** — ruff lint, mypy type check, pip-audit, **99 pytest tests** (on every push/PR)
- **`check-versions.yml`** — NuGet version polling (every Monday 08:00 UTC)

See `docs/deployment.md` for manual run order and rollback instructions.
