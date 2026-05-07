#!/usr/bin/env python3
"""
Upgrades Aspose NuGet packages in local MCP server repos, rebuilds, and runs tests.
On success: commits and pushes. On failure: restores the original .csproj.

Usage:
  python scripts/upgrade_product.py --repos-dir D:\GIT\FinishedMCPservers
  python scripts/upgrade_product.py --repos-dir D:\GIT\FinishedMCPservers --product zip
  python scripts/upgrade_product.py --repos-dir D:\GIT\FinishedMCPservers --no-push
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import time
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")


# ── Shell helpers ─────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: str) -> tuple[int, str]:
    """Run a command, stream output live, return (exit_code, combined_output)."""
    result = subprocess.run(cmd, cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.stdout:
        print(result.stdout, end="")
    return result.returncode, result.stdout or ""


# ── .csproj version bump ──────────────────────────────────────────────────────

def find_csproj_files(repo_dir: str) -> list[str]:
    return glob.glob(os.path.join(repo_dir, "**", "*.csproj"), recursive=True)


def update_csproj(path: str, nuget: str, old_version: str, new_version: str) -> bool:
    """
    Replace  Version="old"  with  Version="new"  on the line referencing {nuget}.
    Returns True if a replacement was made.
    """
    with open(path, encoding="utf-8") as f:
        original = f.read()

    # Match PackageReference with the exact package name, any attribute order
    pattern = re.compile(
        r'(<PackageReference\b[^>]*\bInclude="' + re.escape(nuget) + r'"[^>]*\bVersion=")([^"]+)(")',
        re.IGNORECASE,
    )
    updated, n = pattern.subn(lambda m: m.group(1) + new_version + m.group(3), original)

    if n == 0:
        # Try reversed attribute order (Version before Include)
        pattern2 = re.compile(
            r'(<PackageReference\b[^>]*\bVersion=")([^"]+)("[^>]*\bInclude="' + re.escape(nuget) + r'")',
            re.IGNORECASE,
        )
        updated, n = pattern2.subn(lambda m: m.group(1) + new_version + m.group(3), original)

    if n == 0:
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def restore_csproj(path: str, original_content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(original_content)


# ── Git helpers ───────────────────────────────────────────────────────────────

def git(repo_dir: str, *args) -> tuple[int, str]:
    return run(["git", "-C", repo_dir] + list(args), cwd=repo_dir)


# ── Per-product upgrade ───────────────────────────────────────────────────────

def upgrade(product: dict, from_v: str, to_v: str, repos_dir: str, push: bool) -> bool:
    repo_dir = os.path.join(repos_dir, product["name"])

    if not os.path.isdir(repo_dir):
        print(f"  ERROR: local repo not found at {repo_dir}")
        return False

    nuget = product["nuget"]
    csproj_files = find_csproj_files(repo_dir)
    if not csproj_files:
        print(f"  ERROR: no .csproj files found in {repo_dir}")
        return False

    # Save originals so we can restore on failure
    originals = {}
    for path in csproj_files:
        with open(path, encoding="utf-8") as f:
            originals[path] = f.read()

    # Update version in every .csproj that references this package
    bumped = []
    for path in csproj_files:
        if update_csproj(path, nuget, from_v, to_v):
            bumped.append(path)
            print(f"  Updated: {os.path.relpath(path, repo_dir)}")

    if not bumped:
        print(f"  ERROR: {nuget} {from_v} not found in any .csproj — already upgraded?")
        return False

    # Build
    print("\n── dotnet build ─────────────────────────────────────────────")
    code, _ = run(["dotnet", "build", "--configuration", "Release", "--nologo"], cwd=repo_dir)
    if code != 0:
        print(f"\n  BUILD FAILED — restoring .csproj")
        for path, content in originals.items():
            restore_csproj(path, content)
        return False

    # Test
    print("\n── dotnet test ──────────────────────────────────────────────")
    code, _ = run(["dotnet", "test", "--no-build", "--configuration", "Release", "--nologo"], cwd=repo_dir)
    if code != 0:
        print(f"\n  TESTS FAILED — restoring .csproj")
        for path, content in originals.items():
            restore_csproj(path, content)
        return False

    print(f"\n  Build and tests passed.")

    # Commit
    for path in bumped:
        git(repo_dir, "add", path)

    commit_msg = f"chore: bump {nuget} to {to_v}"
    code, _ = git(repo_dir, "commit", "-m", commit_msg)
    if code != 0:
        print("  Nothing to commit (version already committed?).")

    # Push
    if push:
        print("  Pulling (rebase) before push...")
        git(repo_dir, "pull", "--rebase", "origin", "main")
        code, _ = git(repo_dir, "push")
        if code != 0:
            print("  ERROR: push failed. Commit is local — push manually.")
            return False
        print(f"  Pushed.")

    return True


# ── Outcome tracking ─────────────────────────────────────────────────────────

def _update_product_fields(slug: str, fields: dict):
    """Update specific fields for one product in products.json."""
    with open(PRODUCTS_FILE) as f:
        config = json.load(f)
    for product in config["products"]:
        if product["slug"] == slug:
            product.update(fields)
            break
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _poll_ci_status(github_repo: str, timeout_seconds: int = 90) -> str:
    """
    Poll the most recent GitHub Actions run on main.
    Returns: PASS | FAIL | TIMEOUT
    """
    deadline = time.time() + timeout_seconds
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        time.sleep(10)
        try:
            result = subprocess.run(
                ["gh", "run", "list", "--repo", github_repo,
                 "--branch", "main", "--limit", "1",
                 "--json", "status,conclusion"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                continue
            runs = json.loads(result.stdout)
            if not runs:
                continue
            run = runs[0]
            status     = run.get("status", "")
            conclusion = run.get("conclusion", "")
            if status == "completed":
                ci = "PASS" if conclusion == "success" else "FAIL"
                print(f"  CI: {ci} (polled {attempt}x)")
                return ci
            print(f"  CI still running ({status})...", flush=True)
        except Exception as e:
            print(f"  CI poll error: {e}")

    print(f"  CI status timeout after {timeout_seconds}s — marked TIMEOUT")
    return "TIMEOUT"


def _create_ci_fail_issue(product: dict, to_v: str, github_repo: str):
    """Open a GitHub Issue in the tracker repo when CI fails after upgrade."""
    try:
        tracker_result = subprocess.run(
            ["git", "-C", REPO_ROOT, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        tracker_url = tracker_result.stdout.strip().rstrip(".git")
        if "github.com" not in tracker_url:
            return
        tracker_repo = tracker_url.split("github.com/")[-1]

        subprocess.run(
            ["gh", "label", "create", "ci-failed",
             "--repo", tracker_repo,
             "--color", "b91c1c",
             "--description", "CI failed after upgrade",
             "--force"],
            capture_output=True
        )
        subprocess.run(
            ["gh", "issue", "create",
             "--repo", tracker_repo,
             "--title", f"CI failed: {product['display']} upgrade to {to_v}",
             "--body", (
                 f"## CI Failure After Upgrade\n\n"
                 f"- **Product:** {product['display']}\n"
                 f"- **Version:** {to_v}\n"
                 f"- **Repo:** [{github_repo}](https://github.com/{github_repo})\n\n"
                 f"CI failed after the version bump was pushed. "
                 f"Check the [Actions tab](https://github.com/{github_repo}/actions) "
                 f"and investigate before merging.\n\n"
                 f"_Opened automatically by mcp-agent upgrade_product.py_"
             ),
             "--label", "ci-failed"],
            capture_output=True, text=True, timeout=30
        )
        print(f"  CI failure issue opened in {tracker_repo}")
    except Exception as e:
        print(f"  Could not create CI failure issue: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Upgrade Aspose NuGet in local MCP repos, rebuild, test, and push"
    )
    parser.add_argument("--repos-dir", required=True,
                        help=r"Directory containing local MCP repo clones (e.g. D:\GIT\FinishedMCPservers)")
    parser.add_argument("--product", help="Product slug (zip, font, note, pub). Default: all pending.")
    parser.add_argument("--no-push", action="store_true",
                        help="Skip git push (build and test only)")
    parser.add_argument("--track-ci", action="store_true",
                        help="After push, poll GitHub Actions CI and record result in products.json")
    args = parser.parse_args()

    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    products = config["products"]
    if args.product:
        products = [p for p in products if p["slug"] == args.product]
        if not products:
            print(f"Product '{args.product}' not found in products.json")
            return

    results = []

    for product in products:
        from_v = product.get("previous_version")
        to_v   = product.get("current_version")

        if not from_v or not to_v:
            print(f"\n{product['display']}: no version change recorded — skipping.")
            print(f"  Run check_nuget.py first, or use a different product.")
            continue

        if from_v == to_v:
            print(f"\n{product['display']}: already at {to_v} — skipping.")
            continue

        print(f"\n{'='*60}")
        print(f"  {product['display']}:  {from_v}  ->  {to_v}")
        print(f"{'='*60}")

        ok = upgrade(product, from_v, to_v, args.repos_dir, push=not args.no_push)
        results.append((product["display"], from_v, to_v, ok))

        if ok and not args.no_push:
            # Record upgrade outcome in products.json
            _update_product_fields(product["slug"], {
                "last_upgrade": str(date.today()),
                "last_upgrade_version": to_v,
                "last_ci_status": "PENDING",
            })

            if args.track_ci:
                github_repo = product.get("github_repo")
                if github_repo:
                    print("  Polling CI status...", flush=True)
                    ci_status = _poll_ci_status(github_repo)
                    _update_product_fields(product["slug"], {"last_ci_status": ci_status})
                    if ci_status == "FAIL":
                        _create_ci_fail_issue(product, to_v, github_repo)
                else:
                    print("  Skipping CI tracking (no github_repo in products.json)")

    # Summary
    if results:
        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        for display, from_v, to_v, ok in results:
            status = "OK" if ok else "FAILED"
            print(f"  [{status}] {display}: {from_v} -> {to_v}")

    if not results:
        print("\nNothing to upgrade. Run check_nuget.py first to detect version changes.")
        print(r"Or: python scripts/upgrade_product.py --repos-dir D:\GIT\FinishedMCPservers --product zip")


if __name__ == "__main__":
    main()
