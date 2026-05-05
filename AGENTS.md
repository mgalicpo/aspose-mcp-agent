# AGENTS.md — mcp-agent Architecture

## Overview

mcp-agent is a multi-script automation pipeline for tracking and upgrading
Aspose .NET MCP servers. Each script maps to a logical agent role.

## Agent Roles

```
NuGet API ──→ LoopAgent ──→ products.json ──→ LLMAgent ──→ UpgradePlan
                  │                               │
         GitHub Issue created            ReAct validation loop
                                         (NuGet + release notes)
                                                  │
                                         [safe to merge?]
                                          ↙          ↘
                                   MergeAgent    UpgradeAgent
                                  (Dependabot)   (local .csproj)
```

## Scripts

| Script | Role | Auth required |
|---|---|---|
| `scripts/check_nuget.py` | **LoopAgent** — polls NuGet API, updates `products.json`, creates GitHub Issue | `GITHUB_TOKEN` (CI only) |
| `scripts/analyze_release_aspose.py` | **LLMAgent** — fetches release notes, runs ReAct validation loop, returns upgrade plan | `ASPOSE_LLM_TOKEN` |
| `scripts/analyze_release.py` | **LLMAgent (Claude variant)** — same as above, uses Anthropic API or `--prepare` mode | `ANTHROPIC_API_KEY` (optional) |
| `scripts/merge_dependabot_aspose.py` | **MergeAgent** — finds Dependabot PRs, asks LLM if safe to merge | `ASPOSE_LLM_TOKEN`, `gh` CLI |
| `scripts/merge_dependabot.py` | **MergeAgent (Claude variant)** | `ANTHROPIC_API_KEY`, `gh` CLI |
| `scripts/upgrade_product.py` | **UpgradeAgent** — updates `.csproj`, runs `dotnet build` + `dotnet test`, commits and pushes | `gh` CLI |

## State Model

State is stored in `products.json` per product:

```
not_tracked
    │
    ▼
current_version set (no previous_version)
    │  check_nuget.py detects new version
    ▼
previous_version = old, current_version = new   ← PENDING
    │  analyze_release_aspose.py runs
    ▼
analysis result: safe_to_merge? new_tools?      ← ANALYZED
    │
    ├─ safe, no new tools → upgrade_product.py  ← UPGRADED → push → done
    │
    └─ new tools needed → implement manually → push → done
```

## ReAct Validation Loop (LLMAgent)

```
ACT    → LLM analyzes release notes, returns JSON
OBSERVE → Validator 1: target version exists on NuGet?
          Validator 2: each suggested api_class appears in release notes text?
         ↙ pass                    ↘ fail (up to 3 iterations)
   return result          feed failures back → ACT again
```

## Extension Points

**Add a new product:**
1. Add entry to `products.json` with `slug`, `nuget`, `github_repo`, `current_version`
2. Run `check_nuget.py` to detect future updates automatically

**Add a new validator to LLMAgent:**
Extend `_validate_analysis()` in `scripts/analyze_release_aspose.py`.
Each validator returns a list of failure strings fed back to the model.

**Switch LLM backend:**
Both `analyze_release_aspose.py` (Aspose gateway) and `analyze_release.py`
(Anthropic) use the same prompt and produce the same output format.
Set the appropriate env var and run either script.

## Configuration

All runtime config is in `products.json` (committed) and `.env` (gitignored).
See `.env.example` for required variables.

## Scheduled Automation

`check_nuget.py` runs every Monday at 08:00 UTC via GitHub Actions
(`.github/workflows/check-versions.yml`). All other scripts are run manually.
