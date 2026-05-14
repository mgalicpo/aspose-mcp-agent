# Security Policy

## Reporting a Vulnerability

If you discover a security issue in mcp-agent, please report it privately.

- **Email:** galic.marijan@gmail.com
- **Subject:** `[SECURITY] mcp-agent — <short description>`
- **Response:** within 5 business days
- **Fix target:** within 14 business days for confirmed issues

Please include a description of the issue, steps to reproduce, and the affected
script or component. Do not include real tokens or credentials in your report —
redact them with `***`.

---

## Sensitive Data Handled

| Data | Location | Notes |
|---|---|---|
| `ASPOSE_LLM_TOKEN` | `.env` (gitignored) | Never logged, never committed |
| `ANTHROPIC_API_KEY` | `.env` (gitignored) | Never logged, never committed |
| `GITHUB_TOKEN` | GitHub Actions secret | Never echoed in CI job logs |
| NuGet version state | `products.json` (committed) | No credentials — safe to commit |
| Audit decisions | `audit.jsonl` (gitignored) | Logs metadata only, never token values |

---

## Secrets Handling

- `.env` is gitignored. Only `.env.example` (placeholder values) is committed.
- `ASPOSE_LLM_TOKEN` and `ANTHROPIC_API_KEY` are read from environment variables
  and are never written to logs, output files, or `audit.jsonl`.
- GitHub Actions credentials use repository secrets marked **Masked** — never
  echoed via `echo`, `env`, or `printenv` in workflow steps.
- `audit.jsonl` records only decision metadata (confidence, safe_to_merge,
  iteration count). It never records token values, prompt content, or raw LLM
  responses.

### Token handling pattern used in all scripts

```python
# Correct — log presence, not value
token = os.getenv("ASPOSE_LLM_TOKEN")
if not token:
    raise SystemExit("ASPOSE_LLM_TOKEN not set. See .env.example.")
# token is passed directly to HTTP headers, never logged
```

### Contributor checklist before opening a PR

- [ ] No real tokens in `.env`, test fixtures, scripts, or `audit.jsonl` entries
- [ ] `.env` and `.env.local` are not staged (only `.env.example` is tracked)
- [ ] `git grep -nE "Bearer [A-Za-z0-9._-]{20,}"` returns empty
- [ ] No `ASPOSE_LLM_TOKEN` or `ANTHROPIC_API_KEY` values appear in committed files
- [ ] CI workflow steps do not echo secrets to job logs

---

## Supported Versions

Only the latest commit on `main` receives fixes. This is a developer automation
tool with a single maintainer — no versioned release branches are maintained.

---

## Disclosure

Once a fix is released, the vulnerability and its mitigation are documented in
`CHANGELOG.md` under a `### Security` heading of the corresponding release.
