#!/usr/bin/env python3
"""
[CLAUDE] Lists and optionally merges Dependabot PRs across all tracked Aspose MCP repos.
Uses Claude to give a safety recommendation before merging.

Usage:
  python scripts/merge_dependabot.py              # list all open Dependabot PRs
  python scripts/merge_dependabot.py --merge      # merge PRs Claude approves
  python scripts/merge_dependabot.py --prepare    # print context (no Claude API call)
  python scripts/merge_dependabot.py --product zip
"""
import argparse
import json
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")


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


# ── Claude API call ───────────────────────────────────────────────────────────

def ask_claude(prompt: str) -> dict:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Run `pip install anthropic` first.")

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    # Strip markdown code fences if Claude wraps the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


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
        description="[CLAUDE] List/merge Dependabot PRs across Aspose MCP repos"
    )
    parser.add_argument("--product", help="Filter by product slug (zip, font, note, pub)")
    parser.add_argument("--merge", action="store_true",
                        help="Merge PRs that Claude marks as safe")
    parser.add_argument("--prepare", action="store_true",
                        help="Print context only, no Claude API call")
    args = parser.parse_args()

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

            if args.prepare:
                print(f"\n{'#'*60}")
                print(f"# PASTE INTO CLAUDE CODE — {repo} PR #{pr['number']}")
                print(f"{'#'*60}")
                print(prompt)
                print(f"{'#'*60}\n")
                continue

            print("Asking Claude...", flush=True)
            try:
                decision = ask_claude(prompt)
            except (RuntimeError, json.JSONDecodeError, KeyError) as e:
                print(f"  ERROR: {e}")
                continue

            safe = decision.get("safe_to_merge", False)
            print(f"  Safe to merge: {'YES' if safe else 'NO'}")
            print(f"  Reason: {decision.get('reason', '-')}")
            print(f"  Action: {decision.get('action', '-')}")

            if args.merge:
                if safe:
                    do_merge(repo, pr["number"])
                else:
                    print("  Skipping merge (not approved).")

    if not found_any:
        print("\nNo open Dependabot PRs found across tracked repos.")


if __name__ == "__main__":
    main()
