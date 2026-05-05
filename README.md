# mcp-agent

Central version tracker and upgrade automation for Aspose .NET MCP servers.
Detects new NuGet releases, analyzes them with an LLM, and upgrades local repos.

## Architecture

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
   upgrade_product.py   implement
   (bump .csproj,        new MCP tools
    dotnet build,        manually
    dotnet test,
    git push)
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

```bash
# 1. Copy and fill in credentials
cp .env.example .env

# 2. Check for new NuGet versions
python scripts/check_nuget.py

# 3. Analyze what changed (ReAct + confidence scoring)
python scripts/analyze_release_aspose.py

# 4. Upgrade, build, test, push
python scripts/upgrade_product.py --repos-dir D:\GIT\FinishedMCPservers
```

## Scripts

| Script | Purpose |
|---|---|
| `check_nuget.py` | Poll NuGet API, update `products.json`, create GitHub Issue |
| `analyze_release_aspose.py` | Fetch release notes, ReAct LLM analysis, confidence scoring |
| `analyze_release.py` | Same, using Anthropic API (`--prepare` for no-key mode) |
| `merge_dependabot_aspose.py` | Find Dependabot PRs, LLM safe/unsafe decision, optional auto-merge |
| `upgrade_product.py` | Bump `.csproj`, `dotnet build`, `dotnet test`, commit, push |

## Configuration

| File | Purpose |
|---|---|
| `products.json` | Tracked products with NuGet package names and version state |
| `.env` | `ASPOSE_LLM_TOKEN` — gitignored, see `.env.example` |

## Tracked Products

| Product | NuGet | MCP Repo |
|---|---|---|
| Aspose.Font | `Aspose.Font` | `mgalicpo/aspose-font-mcp` |
| Aspose.ZIP  | `Aspose.ZIP`  | `mgalicpo/aspose-zip-mcp`  |
| Aspose.Note | `Aspose.Note` | `mgalicpo/aspose-note-mcp` |
| Aspose.PUB  | `Aspose.PUB`  | `mgalicpo/aspose-pub-mcp`  |

## Adding a New Product

1. Add entry to `products.json`:
```json
{
  "name": "aspose-words-mcp",
  "display": "Aspose.Words",
  "nuget": "Aspose.Words",
  "slug": "words",
  "github_repo": "mgalicpo/aspose-words-mcp",
  "current_version": "25.1.0"
}
```
2. Run `check_nuget.py` — future updates are tracked automatically.

## CI

GitHub Actions runs two workflows:
- **`ci.yml`** — syntax checks + script startup tests (on every push/PR)
- **`check-versions.yml`** — NuGet version polling (every Monday 08:00 UTC)
