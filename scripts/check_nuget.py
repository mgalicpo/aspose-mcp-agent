#!/usr/bin/env python3
"""
Checks NuGet for latest stable versions of tracked Aspose packages.
Writes results to GITHUB_OUTPUT for use in GitHub Actions.
Also updates products.json with new versions.
"""
import json
import os
import urllib.request
import urllib.error

# Always resolve paths relative to repo root, not cwd
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")


def get_latest_stable(package_id: str) -> str:
    url = f"https://api.nuget.org/v3-flatcontainer/{package_id.lower()}/index.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            versions = json.loads(r.read())["versions"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"NuGet API error for {package_id}: {e.code}")

    stable = [v for v in versions if not any(x in v for x in ["-alpha", "-beta", "-preview", "-rc"])]
    return stable[-1] if stable else versions[-1]


def build_issue_body(updates: list) -> str:
    lines = ["## Aspose NuGet Updates Detected\n"]
    for u in updates:
        lines.append(f"### {u['display']}")
        lines.append(f"- Version: `{u['current']}` -> `{u['latest']}`")
        lines.append(f"- Release notes: https://releases.aspose.com/{u['slug']}/net/")
        lines.append(f"- NuGet: https://www.nuget.org/packages/{u['nuget']}/")
        lines.append("")
    lines.append("---")
    lines.append("**Next steps:**")
    lines.append("1. Review release notes for new APIs or breaking changes")
    lines.append("2. Check if new MCP tools are needed (see tool-map.md in each repo)")
    lines.append("3. Merge the Dependabot PR in each affected repo")
    return "\n".join(lines)


def main():
    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    updates = []
    for product in config["products"]:
        print(f"Checking {product['nuget']}...", flush=True)
        latest = get_latest_stable(product["nuget"])
        current = product["current_version"]

        if latest != current:
            print(f"  UPDATE: {current} -> {latest}")
            updates.append({**product, "current": current, "latest": latest})
            product["previous_version"] = current  # remember what we had before
            product["current_version"] = latest
        else:
            print(f"  OK: {current}")

    # Save updated versions back to products.json
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(config, f, indent=2)

    # Write to GitHub Actions output
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if output_path:
        with open(output_path, "a") as f:
            if updates:
                body = build_issue_body(updates)
                delimiter = "EOF_ISSUE_BODY"
                f.write(f"updates_found=true\n")
                f.write(f"update_count={len(updates)}\n")
                f.write(f"issue_body<<{delimiter}\n{body}\n{delimiter}\n")
            else:
                f.write("updates_found=false\n")
                f.write("update_count=0\n")
    else:
        # Local run - just print
        if updates:
            print("\n" + build_issue_body(updates))

    print(f"\nDone. {len(updates)} update(s) found.")


if __name__ == "__main__":
    main()
