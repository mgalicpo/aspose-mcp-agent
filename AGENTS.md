# AGENTS.md — mcp-agent Architecture

## Overview

mcp-agent is a multi-script automation pipeline for tracking and upgrading
Aspose .NET MCP servers. Each script maps to a logical agent role.

## Agent Roles

```
                    ┌─────────────────────────────────────────┐
                    │         EXISTING PRODUCT FLOW            │
                    └─────────────────────────────────────────┘

NuGet API ──→ LoopAgent ──→ products.json ──→ LLMAgent ──→ UpgradePlan
                  │                               │
         GitHub Issue created            ReAct validation loop
                                         (NuGet + release notes)
                                                  │
                                         [safe to merge?]
                                          ↙          ↘
                                   MergeAgent    UpgradeAgent
                                  (Dependabot)   (local .csproj)


                    ┌─────────────────────────────────────────┐
                    │           NEW PRODUCT FLOW               │
                    └─────────────────────────────────────────┘

Aspose Docs ──→ AnalysisAgent ──→ tool-map.md ──→ ScaffoldAgent
                 (LLM designs                    (creates project,
                  tool set)                       GitHub repo,
                                                  products.json entry)
                                                        │
                                                  Claude Code session
                                                  (implements tools)
                                                        │
                                                  LoopAgent picks up
                                                  next Monday
```

## Scripts

### Existing product — version updates

| Script | Role | Auth required |
|---|---|---|
| `scripts/check_nuget.py` | **LoopAgent** — polls NuGet API, updates `products.json`, creates GitHub Issue | `GITHUB_TOKEN` (CI only) |
| `scripts/analyze_release_aspose.py` | **LLMAgent** — fetches release notes, ReAct loop, confidence scoring | `ASPOSE_LLM_TOKEN` |
| `scripts/analyze_release.py` | **LLMAgent (Claude)** — same, `--prepare` for no-key mode | `ANTHROPIC_API_KEY` (optional) |
| `scripts/merge_dependabot_aspose.py` | **MergeAgent** — finds Dependabot PRs, LLM safe/unsafe decision | `ASPOSE_LLM_TOKEN`, `gh` CLI |
| `scripts/merge_dependabot.py` | **MergeAgent (Claude)** | `ANTHROPIC_API_KEY`, `gh` CLI |
| `scripts/upgrade_product.py` | **UpgradeAgent** — bumps `.csproj`, builds, tests, pushes | `gh` CLI |

### New product — onboarding

| Script | Role | Auth required |
|---|---|---|
| `scripts/analyze_new_product_aspose.py` | **AnalysisAgent** — fetches Aspose docs, LLM generates tool-map.md (ReAct + network retry) | `ASPOSE_LLM_TOKEN` |
| `scripts/analyze_new_product.py` | **AnalysisAgent (Claude)** — same, `--prepare` for no-key mode | `ANTHROPIC_API_KEY` (optional) |
| `scripts/new_product.py` | **ScaffoldAgent** — creates project structure, GitHub repo, registers in `products.json` | `gh` CLI |

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

## ReAct Validation Loop (LLMAgent — release analysis)

```
ACT    → LLM analyzes release notes, returns JSON
OBSERVE → Validator 1: target version exists on NuGet?
          Validator 2: each suggested api_class appears in release notes text?
         ↙ pass                    ↘ fail (up to 3 iterations)
   return result          feed failures back → ACT again
```

## ReAct Validation Loop (AnalysisAgent — new product)

```
Network retry (transparent, up to 3x)
          │
          ▼
ACT    → LLM fetches Aspose docs, designs tool set, returns JSON
OBSERVE → Validator 1: tool names start with "{slug}_"?
          Validator 2: each tool has api_class?
          Validator 3: at least 2 tools suggested?
         ↙ pass                    ↘ fail (up to 3 iterations)
   return result          feed failures back → ACT again
```

## Extension Points

**Add a new product (full onboarding):**
```bash
python scripts/analyze_new_product_aspose.py --slug words --nuget "Aspose.Words" --output tool-map.md
python scripts/new_product.py --slug words --nuget "Aspose.Words" --version "25.1.0" \
    --output-dir D:\GIT\FinishedMCPservers --github-user mgalicpo --create-repo
```

**Add an existing product to tracking only:**
Add entry to `products.json` with `slug`, `nuget`, `github_repo`, `current_version`.

**Add a new release validator:**
Extend `_validate_analysis()` in `scripts/analyze_release_aspose.py`.

**Add a new tool-map validator:**
Extend `_validate_schema()` in `scripts/analyze_new_product_aspose.py`.

**Switch LLM backend:**
All `*_aspose.py` scripts use the Aspose gateway; all `*.py` counterparts use
Anthropic API or `--prepare` mode. Prompts and output format are identical.

## Configuration

All runtime config is in `products.json` (committed) and `.env` (gitignored).
See `.env.example` for required variables.

## Scheduled Automation

`check_nuget.py` runs every Monday at 08:00 UTC via GitHub Actions
(`.github/workflows/check-versions.yml`). All other scripts are run manually.
