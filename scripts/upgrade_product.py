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
