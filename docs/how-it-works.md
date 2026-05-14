# How mcp-agent Works

End-to-end guide: what every script does, how they chain together, and where git automation happens.

---

## LLM Modes

Every analysis step (release analysis, Dependabot review, new product design) can run in three modes. Choose based on what you have available:

| Mode | How to invoke | Requires |
|---|---|---|
| **1 — Claude Code CLI** | `python script.py --prepare \| claude -p` | Claude Code installed |
| **2 — Aspose LLM** | `python script_aspose.py` | `ASPOSE_LLM_TOKEN` in `.env` |
| **3 — Anthropic API** | `python script.py` (no flag) | `ANTHROPIC_API_KEY` in `.env` |

**Mode 1 is the recommended default** for anyone without an Aspose token. The `--prepare` flag fetches all context (release notes, tool-map.md, PR list) and formats it as a ready-to-use prompt. Piping to `claude -p` runs it non-interactively — no copy-paste, no API key.

Mode 2 (`*_aspose.py` scripts) is preferred for Aspose employees as it uses the internal LLM gateway and runs fully automated.

---

## Central State: `products.json`

Every script reads and writes a single file — `products.json`. It tracks per-product state:

```json
{
  "products": [
    {
      "slug": "zip",
      "display": "Aspose.ZIP",
      "nuget": "Aspose.ZIP",
      "github_repo": "aspose/aspose-zip-mcp",
      "current_version": "26.4.0",
      "previous_version": "26.3.0",
      "last_upgrade": "2026-05-07",
      "last_upgrade_version": "26.4.0",
      "last_ci_status": "PASS"
    }
  ]
}
```

Key fields:

| Field | Set by | Meaning |
|---|---|---|
| `current_version` | `check_nuget.py` | Latest version on NuGet |
| `previous_version` | `check_nuget.py` | Previous version (before current update) |
| `last_upgrade` | `upgrade_product.py` | Date the csproj was bumped and pushed |
| `last_upgrade_version` | `upgrade_product.py` | Version that was pushed |
| `last_ci_status` | `upgrade_product.py --track-ci` | PENDING / PASS / FAIL / TIMEOUT |

When `current_version == previous_version` (or `previous_version` is absent), the product is up to date — nothing to do.

---

## Workflow 1: Existing Product Version Update

```
check_nuget.py
    → updates products.json
    → opens GitHub Issue (if new version found)
         ↓
analyze_release_aspose.py
    → fetches release notes from releases.aspose.com
    → fetches tool-map.md from the product's GitHub repo
    → ReAct LLM loop (up to 3 iterations)
    → prints decision + confidence
    → opens GitHub Issue if escalated (confidence < 0.7)
    → appends one line to audit.jsonl
         ↓
upgrade_product.py
    → patches .csproj in local MCP repo
    → dotnet build + dotnet test
    → git commit + git push
    → (optionally) polls GitHub Actions CI
    → updates products.json with last_upgrade, last_ci_status
```

### Step 1 — `check_nuget.py`

Polls the NuGet v3 API for the latest version of each package. If a new version is found:

1. Sets `previous_version = current_version` and `current_version = <new>` in `products.json`
2. Creates a GitHub Issue in this tracker repo with the version diff

**Git automation:** none. Only reads/writes `products.json` and calls `gh issue create`.

**GitHub Actions:** `check-versions.yml` runs this script every Monday at 08:00 UTC. The workflow commits any `products.json` changes with message `chore: update known NuGet versions [skip ci]` and pushes them.

```yaml
# .github/workflows/check-versions.yml (key step)
- name: Commit updated products.json
  run: |
    git add products.json
    git commit -m "chore: update known NuGet versions [skip ci]" || echo "Nothing to commit"
    git push
```

The `[skip ci]` suffix prevents the push from triggering another CI run.

### Step 2 — release analysis (pick your mode)

```bash
# Mode 1 — Claude Code CLI (recommended, no token needed)
python scripts/analyze_release.py --prepare | claude -p

# Mode 2 — Aspose LLM
python scripts/analyze_release_aspose.py

# Mode 3 — Anthropic API
python scripts/analyze_release.py
```

All three run the same logic. `analyze_release_aspose.py` runs it fully automated;
`analyze_release.py --prepare` fetches the context and pipes it to Claude Code.

**What happens internally:**

Fetches the Aspose release notes page (truncated to 5000 chars before sending to LLM) and runs a ReAct analysis loop:

**ReAct loop (ACT → OBSERVE → re-prompt, up to 3 iterations):**

1. **ACT** — sends release notes + tool-map.md to the LLM, asks for structured JSON decision
2. **OBSERVE** — validates the JSON schema, checks that any claimed `api_class` names actually appear in the release notes text
3. If validation fails, feeds the failure reason back to the LLM and tries again

**HTTP retry behaviour (applies to all `*_aspose.py` scripts):**

| Error type | Behaviour |
|---|---|
| 4xx (incl. 401 Unauthorized) | Fail immediately — client error, retrying won't help |
| 5xx / network error | Retry up to 3 times with exponential backoff (1s, 2s) |
| Invalid JSON / schema error | Retry up to 3 times, feeding the error back to the model |

**Output decision schema:**
```json
{
  "safe_to_merge": true,
  "reason": "Only bug fixes, no API changes",
  "confidence": 0.92,
  "new_tools": [],
  "breaking_changes": [],
  "next_step": "Run upgrade_product.py"
}
```

**Escalation triggers (HITL):**
- `confidence < 0.7` — LLM is uncertain
- ReAct loop hit max iterations without converging
- `safe_to_merge = false` — breaking changes detected

On escalation (unless `--no-hitl`): opens a GitHub Issue in this tracker repo so a human can review before upgrading.

**Audit log:** appends one JSON line to `audit.jsonl` at the repo root:
```json
{"timestamp": "2026-05-07T10:00:00Z", "product": "Aspose.ZIP", "from_version": "26.3.0", "to_version": "26.4.0", "confidence": 0.92, "safe_to_merge": true, "escalated": false, ...}
```

**Git automation:** none. Reads-only; all output goes to stdout and `audit.jsonl`.

### Step 3 — `upgrade_product.py`

Runs entirely against the **local MCP repo clone** (e.g., `/path/to/repos/aspose-zip-mcp`).

**What it does:**

1. Finds all `.csproj` files in the repo
2. Patches `Version="<old>"` → `Version="<new>"` for the target NuGet package using regex
3. Runs `dotnet build --configuration Release`
4. Runs `dotnet test --no-build --configuration Release`
5. On failure: restores original `.csproj` content and exits
6. On success:

```python
# Git automation sequence
git(repo_dir, "add", *bumped_csproj_files)
git(repo_dir, "commit", "-m", f"chore: bump {nuget} to {to_v}")
git(repo_dir, "pull", "--rebase", "origin", "main")   # avoid conflicts
git(repo_dir, "push")
```

7. Writes `last_upgrade`, `last_upgrade_version`, `last_ci_status = "PENDING"` to `products.json`

**CI polling (`--track-ci` flag):**

After push, polls `gh run list` every 10 seconds for up to 90 seconds:
```python
gh run list --repo <github_repo> --branch main --limit 1 --json status,conclusion
```
- `status == "completed"` + `conclusion == "success"` → **PASS**
- `status == "completed"` + anything else → **FAIL** → opens a GitHub Issue
- 90s timeout → **TIMEOUT**

Updates `last_ci_status` in `products.json` with the result.

---

## Workflow 2: Dependabot PR Merge

```bash
# Mode 1 — Claude Code CLI
python scripts/merge_dependabot.py --prepare | claude -p

# Mode 2 — Aspose LLM
python scripts/merge_dependabot_aspose.py

# Mode 3 — Anthropic API
python scripts/merge_dependabot.py
```

Lists open Dependabot PRs (`gh pr list --repo <github_repo> --author app/dependabot`), asks the LLM whether each is safe to merge, and optionally merges with `gh pr merge --squash`.

Decision is made per PR. Merges only if LLM returns `safe_to_merge: true` and user confirms (or `--auto` flag is set).

**Git automation:** none in this repo. The merge itself is done via GitHub API through the `gh` CLI — it runs in the remote MCP repo, not locally.

---

## Workflow 3: New Product Onboarding

```
analyze_new_product_aspose.py
    → fetches Aspose docs HTML pages
    → LLM generates tool-map.md
         ↓
new_product.py
    → scaffolds local project structure
    → git init + initial commit
    → gh repo create --private --push
    → registers product in products.json
```

### Step 1 — tool map generation (pick your mode)

```bash
# Mode 1 — Claude Code CLI
python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words" --prepare | claude -p

# Mode 2 — Aspose LLM
python scripts/analyze_new_product_aspose.py --slug words --nuget "Aspose.Words" --output tool-map.md

# Mode 3 — Anthropic API
python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words" --output tool-map.md
```

Fetches Aspose product documentation and uses the LLM to design a `tool-map.md` — a structured mapping of Aspose API sections to MCP tool names, parameters, and return types. Writes the file to disk.

**Git automation:** none.

### Step 2 — `new_product.py`

Scaffolds the full C# project structure in a local directory, then:

```python
# Git automation sequence
git(["git", "init"], cwd=repo_dir)
git(["git", "add", "."], cwd=repo_dir)
git(["git", "commit", "-m", "chore: initial scaffold"], cwd=repo_dir)

# Create private GitHub repo and push
subprocess.run([
    "gh", "repo", "create", repo_name,
    "--private", "--source", repo_dir, "--push"
])
```

Then registers the new product in `products.json` with `current_version` set and no `previous_version` (so `check_nuget.py` will track it from next week).

---

## GitHub Actions Workflows

### `ci.yml` — runs on every push and PR

```
ruff check scripts/ tests/     ← lint + import order
mypy scripts/ --config-file pyproject.toml  ← type checking
pip-audit --desc               ← security vulnerabilities in dependencies
pytest tests/ -v --cov=scripts ← 99 unit tests, ≥35% coverage required
```

Protects main branch from broken code, bad imports, or known-vulnerable packages.

### `check-versions.yml` — runs every Monday 08:00 UTC

```
python scripts/check_nuget.py
git add products.json
git commit -m "chore: update known NuGet versions [skip ci]"
git push
```

This is the only automated git commit that this agent makes to its own repo. All other git operations happen in the MCP product repos (via `upgrade_product.py` or `new_product.py`).

---

## Git Operations Summary

| Script | Target repo | Git operations |
|---|---|---|
| `check_nuget.py` (via CI) | `mcp-agent` | commit + push `products.json` |
| `upgrade_product.py` | each MCP repo | add + commit + pull --rebase + push |
| `new_product.py` | new MCP repo | init + add + commit + gh repo create + push |
| `merge_dependabot_aspose.py` | remote via GitHub API | `gh pr merge --squash` |
| All others | — | no git operations |

---

## Audit Trail

Every analysis run writes one line to `audit.jsonl` (gitignored):

```
{"timestamp":"2026-05-07T10:00:00Z","product":"Aspose.ZIP","from_version":"26.3.0","to_version":"26.4.0","model":"recommended","react_iterations":1,"confidence":0.92,"safe_to_merge":true,"new_tools_count":0,"breaking_changes":0,"escalated":false}
```

Useful for reviewing history of decisions without touching GitHub.

---

## Environment Variables

| Variable | Used by | Purpose |
|---|---|---|
| *(none)* | Mode 1 — `--prepare \| claude -p` | Claude Code CLI; no env var needed |
| `ASPOSE_LLM_TOKEN` | Mode 2 — `*_aspose.py` scripts | Bearer token for `llm.professionalize.com` |
| `ANTHROPIC_API_KEY` | Mode 3 — non-aspose scripts without `--prepare` | Anthropic API direct access |
| `GH_TOKEN` / `GITHUB_TOKEN` | GitHub Actions | `gh` CLI authentication |
| `ASPOSE_LICENSE_PATH` | MCP server processes | Path to `.lic` file; omit for evaluation mode |
