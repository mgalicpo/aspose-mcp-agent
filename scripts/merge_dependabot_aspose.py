#!/usr/bin/env python3
"""
[ASPOSE LLM] Lists and optionally merges Dependabot PRs across all tracked Aspose MCP repos.
Uses the Aspose/Professionalize LLM gateway instead of Claude API.
Requires ASPOSE_LLM_TOKEN env var.

Usage:
  python scripts/merge_dependabot_aspose.py              # list all open Dependabot PRs
  python scripts/merge_dependabot_aspose.py --merge      # merge PRs LLM approves
  python scripts/merge_dependabot_aspose.py --product zip
  python scripts/merge_dependabot_aspose.py --model experimental
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")

ASPOSE_LLM_BASE = "https://llm.professionalize.com"
DEFAULT_MODEL = "recommended"


def _load_env():
    """Load .env from repo root into os.environ (only if key not already set)."""
    env_file = os.path.join(REPO_ROOT, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip()

_load_env()

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


# ── gh CLI wrapper ────────────────────────────────────────────────────────────

def gh(*args, check=True) -> dict | list | str:
    result = subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=30)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


def list_dependabot_prs(repo: str) -> list[dict]:
    try:
        prs = gh("pr", "list", "--repo", repo, "--author", "app/dependabot",
                 "--state", "open",
                 "--json", "number,title,body,statusCheckRollup,mergeable,headRefName")
        return prs if isinstance(prs, list) else []
    except RuntimeError:
        return []


def ci_summary(status_checks: list) -> tuple[str, list[str]]:
    """Returns (overall_status, failed_check_names). Status: PASS | FAIL | PENDING."""
    if not status_checks:
        return "PENDING", []
    failed = [c["name"] for c in status_checks
              if c.get("conclusion") in ("FAILURE", "ERROR", "TIMED_OUT")]
    pending = [c for c in status_checks
               if c.get("status") not in ("COMPLETED",) and not c.get("conclusion")]
    if failed:
        return "FAIL", failed
    if pending:
        return "PENDING", []
    return "PASS", []


# ── Prompt ────────────────────────────────────────────────────────────────────

def build_prompt(repo: str, pr: dict, ci_status: str, failed_checks: list[str]) -> str:
    failed_block = (
        f"Failed CI checks: {', '.join(failed_checks)}"
        if failed_checks else "All CI checks passed."
    )
    return f"""You are reviewing a Dependabot NuGet version bump PR for an Aspose .NET MCP server.

Repo: {repo}
PR #{pr['number']}: {pr['title']}
CI status: {ci_status}
{failed_block}

PR body (Dependabot generated):
---
{(pr.get('body') or '')[:1500]}
---

Respond with valid JSON only — no prose, no markdown:
{{"safe_to_merge": true or false, "reason": "one sentence", "action": "one concrete sentence for the developer"}}
"""


# ── Aspose LLM call with guardrails ──────────────────────────────────────────

def _llm_call(token: str, model: str, prompt: str) -> str:
    url = f"{ASPOSE_LLM_BASE}/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from response, stripping markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def ask_aspose_llm(token: str, model: str, prompt: str, max_attempts: int = 3) -> dict:
    """
    Guardrail (CLAUDE.md §1 + §2): retry with re-prompting + schema validation.
    Mid-tier models may return malformed JSON — feed the error back on retry.
    """
    last_error = None
    for attempt in range(max_attempts):
        user_prompt = prompt if attempt == 0 else (
            f"{prompt}\n\n"
            f"[Previous attempt failed: {last_error}. "
            f"Return ONLY valid JSON with keys: safe_to_merge, reason, action.]"
        )
        try:
            raw = _llm_call(token, model, user_prompt)
            decision = _parse_json_response(raw)
            # Schema validation
            if not isinstance(decision.get("safe_to_merge"), bool):
                raise ValueError(f"safe_to_merge must be boolean, got: {decision.get('safe_to_merge')!r}")
            if "reason" not in decision or "action" not in decision:
                raise ValueError(f"Missing required keys. Got: {list(decision.keys())}")
            return decision
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise RuntimeError(
                    f"[ASPOSE LLM] Client error {e.code} — check token and parameters"
                ) from e
            last_error = f"HTTP error: {e}"
        except urllib.error.URLError as e:
            last_error = f"HTTP error: {e}"
        except (json.JSONDecodeError, ValueError) as e:
            last_error = f"Invalid response: {e}"
        except Exception as e:
            last_error = str(e)
        print(f"  [retry {attempt + 1}/{max_attempts}] {last_error}", flush=True)
        if attempt < max_attempts - 1:
            time.sleep(2 ** attempt)  # 1s, 2s

    raise RuntimeError(f"[ASPOSE LLM] Failed after {max_attempts} attempts: {last_error}")


# ── Merge ─────────────────────────────────────────────────────────────────────

def do_merge(repo: str, pr_number: int):
    try:
        gh("pr", "merge", str(pr_number), "--repo", repo, "--squash", "--delete-branch")
        print("  Merged.")
    except RuntimeError as e:
        print(f"  ERROR: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="[ASPOSE LLM] List/merge Dependabot PRs across Aspose MCP repos"
    )
    parser.add_argument("--product", help="Filter by product slug (zip, font, note, pub)")
    parser.add_argument("--merge", action="store_true",
                        help="Merge PRs the LLM marks as safe")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Aspose LLM model (default: {DEFAULT_MODEL}). "
                             f"Options: recommended, experimental, qwen3-next, gpt-oss")
    args = parser.parse_args()

    token = os.environ.get("ASPOSE_LLM_TOKEN", "").strip()
    if not token:
        print("ERROR: Set the ASPOSE_LLM_TOKEN environment variable.")
        print("  Get a token at: https://sup.dynabic.com/ (category: Access token request)")
        return

    print(f"[ASPOSE LLM] Using model: {args.model} @ {ASPOSE_LLM_BASE}")

    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    products = config["products"]
    if args.product:
        products = [p for p in products if p["slug"] == args.product]

    found_any = False

    for product in products:
        repo = product.get("github_repo")
        if not repo:
            continue

        prs = list_dependabot_prs(repo)
        if not prs:
            print(f"{product['display']}: no open Dependabot PRs")
            continue

        for pr in prs:
            found_any = True
            ci_status, failed_checks = ci_summary(pr.get("statusCheckRollup") or [])

            print(f"\n{'='*60}")
            print(f"  {product['display']} | PR #{pr['number']} | CI: {ci_status}")
            print(f"  {pr['title']}")
            print(f"{'='*60}")

            prompt = build_prompt(repo, pr, ci_status, failed_checks)

            print(f"Asking {args.model}...", flush=True)
            try:
                decision = ask_aspose_llm(token, args.model, prompt)
            except RuntimeError as e:
                print(f"  ERROR: {e}")
                continue

            safe = decision["safe_to_merge"]
            print(f"  Safe to merge: {'YES' if safe else 'NO'}")
            print(f"  Reason: {decision['reason']}")
            print(f"  Action: {decision['action']}")

            if args.merge:
                if safe:
                    do_merge(repo, pr["number"])
                else:
                    print("  Skipping merge (not approved).")

    if not found_any:
        print("\nNo open Dependabot PRs found across tracked repos.")


if __name__ == "__main__":
    main()
