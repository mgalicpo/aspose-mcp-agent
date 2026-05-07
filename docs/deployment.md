# Deployment & CI

## CI pipeline (GitHub Actions)

Two workflows run automatically:

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push / PR to main | Syntax check, --help flags, pytest (65 tests) |
| `check-versions.yml` | Every Monday 08:00 UTC | Poll NuGet, update products.json, open GitHub Issue |

### CI steps (ci.yml)

```
1. Syntax check all scripts (py_compile)
2. Verify --help on each script
3. pip install pytest
4. pytest tests/ -v   (65 tests, ~2s)
5. python scripts/check_nuget.py  (read-only NuGet API call)
```

No secrets needed for CI — all checks are read-only or offline.

## Manual run order

For a full weekly update cycle:

```bash
# 1. Detect new versions
bash scripts/run.sh check

# 2. Analyze what changed
bash scripts/run.sh analyze

# 3a. If safe to merge — upgrade local repos
bash scripts/run.sh upgrade --repos-dir D:\GIT\FinishedMCPservers

# 3b. If new tools needed — implement in Claude Code, then upgrade
```

## Adding a new product

```bash
# Generate tool map
bash scripts/run.sh new --slug words --nuget "Aspose.Words"

# Scaffold project
bash scripts/run.sh scaffold \
  --slug words --nuget "Aspose.Words" --version "25.1.0" \
  --output-dir D:\GIT\FinishedMCPservers \
  --github-user mgalicpo --create-repo
```

## Rollback

`products.json` is committed on every NuGet version bump by GitHub Actions.
To rollback:

```bash
git log --oneline -- products.json   # find the commit to rollback to
git checkout <sha> -- products.json
git commit -m "revert: rollback products.json to <sha>"
git push
```

## Secrets rotation

If `ASPOSE_LLM_TOKEN` is compromised:
1. Request a new token at https://sup.dynabic.com/
2. Update `.env` locally
3. Update the GitHub Actions secret `ASPOSE_LLM_TOKEN` in repo Settings → Secrets
