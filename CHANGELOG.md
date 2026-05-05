# Changelog

All notable changes to mcp-agent are documented here.

## [Unreleased]

## [0.3.0] — 2026-05

### Added
- ReAct validation loop in `analyze_release_aspose.py`: LLM claims are validated
  against NuGet API (version existence) and release notes text (API class names).
  Failures are fed back to the model for revision, up to 3 iterations.
- Structured JSON output from LLM analysis (replaces free-text responses).

## [0.2.0] — 2026-04

### Added
- `analyze_release_aspose.py` — release analysis via Aspose LLM gateway
  (llm.professionalize.com), as an alternative to the Anthropic API variant.
- `merge_dependabot.py` / `merge_dependabot_aspose.py` — lists open Dependabot
  PRs across all tracked repos, asks LLM for a safe/unsafe decision, optionally
  merges approved PRs.
- `upgrade_product.py` — updates `.csproj` NuGet version locally, runs
  `dotnet build` + `dotnet test`, commits and pushes on success, restores on failure.
- `.env` support: `ASPOSE_LLM_TOKEN` auto-loaded from repo root `.env` file.
- Private repo support: `tool-map.md` fetched via GitHub API with `gh auth token`
  as fallback when raw URL returns 404.
- `per-product github_repo` field in `products.json` for multi-account support.

## [0.1.0] — 2026-03

### Added
- `check_nuget.py` — polls NuGet API for latest stable versions of all tracked
  Aspose packages, updates `products.json`, writes GitHub Actions output variables.
- `analyze_release.py` — fetches Aspose release notes and `tool-map.md`, sends
  to Claude API for analysis. `--prepare` flag for zero-API-key usage.
- GitHub Actions workflow (`check-versions.yml`) — runs `check_nuget.py` every
  Monday at 08:00 UTC, creates a GitHub Issue when updates are found, commits
  updated `products.json`.
- `products.json` — central registry of tracked Aspose MCP products with version
  state (`current_version`, `previous_version`).
