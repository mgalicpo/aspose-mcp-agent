#!/usr/bin/env python3
"""
Fetches Aspose release notes for a new version and uses Claude to analyze
whether the MCP server needs new tools or changes to existing ones.

Usage:
  python scripts/analyze_release.py                    # analyze all pending updates
  python scripts/analyze_release.py --product zip      # specific product
  python scripts/analyze_release.py --product zip --from 26.2.0 --to 26.3.0  # explicit versions
"""
import argparse
import json
import os
import urllib.request
import urllib.error
from html.parser import HTMLParser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")


# ── HTML → plain text ────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "aside"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data.strip())

    def result(self):
        return "\n".join(self.parts)


def _html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return p.result()


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


# ── Release notes ─────────────────────────────────────────────────────────────

def _release_notes_url(slug: str, version: str) -> str:
    """
    Constructs Aspose release notes URL.
    Aspose uses YY.M.patch versioning, e.g. 26.3.0 = year 2026, month 3.
    URL pattern: https://releases.aspose.com/{slug}/net/release-notes/{year}/aspose-{slug}-for-net-{major}-{minor}-release-notes/
    """
    major, minor = version.split(".")[:2]
    year = f"20{major}"
    return (
        f"https://releases.aspose.com/{slug}/net/release-notes/"
        f"{year}/aspose-{slug}-for-net-{major}-{minor}-release-notes/"
    )


def fetch_release_notes(slug: str, version: str) -> tuple[str, str]:
    """Returns (text, url). Falls back to main releases page if specific URL fails."""
    url = _release_notes_url(slug, version)
    try:
        text = _html_to_text(_fetch(url))
        return text[:5000], url  # cap to avoid token overload
    except Exception:
        fallback = f"https://releases.aspose.com/{slug}/net/"
        text = _html_to_text(_fetch(fallback))
        return text[:3000], fallback


# ── tool-map.md from GitHub ───────────────────────────────────────────────────

def fetch_tool_map(github_repo: str) -> str | None:
    """Fetch tool-map.md using full repo path, e.g. 'mgalicpo/aspose-zip-mcp'."""
    url = f"https://raw.githubusercontent.com/{github_repo}/main/tool-map.md"
    try:
        return _fetch(url)
    except Exception:
        return None


# ── Claude analysis ───────────────────────────────────────────────────────────

def analyze(product: dict, from_version: str, to_version: str,
            release_notes: str, notes_url: str, tool_map: str | None) -> str:
    try:
        import anthropic
    except ImportError:
        return "ERROR: Run `pip install anthropic` first."

    tool_map_block = (
        f"Current tool-map.md:\n---\n{tool_map}\n---"
        if tool_map
        else "tool-map.md not available (repo not published yet)."
    )

    prompt = f"""You are reviewing an Aspose .NET library update to decide if an MCP server needs changes.

Product: {product['display']}
Version: {from_version} -> {to_version}
Release notes source: {notes_url}

Release notes (excerpt):
---
{release_notes}
---

{tool_map_block}

Answer these 4 questions concisely:

1. SAFE TO MERGE? Can the Dependabot PR be merged without touching MCP server code?
2. NEW TOOLS? List any new Aspose APIs/capabilities that should become new MCP tools (name + one-line description each).
3. BREAKING CHANGES? Any existing MCP tools affected by API changes or deprecations?
4. NEXT STEP? One concrete sentence: what should the developer do right now.
"""

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


# ── Prepare context for manual Claude Code analysis ──────────────────────────

def _print_context_for_claude(product, from_v, to_v, notes, notes_url, tool_map):
    tool_map_block = (
        f"Current tool-map.md:\n---\n{tool_map}\n---"
        if tool_map
        else "tool-map.md: not available"
    )
    print(f"""
{'#'*60}
# PASTE THIS INTO CLAUDE CODE
{'#'*60}

Analiziraj ovu Aspose promjenu i reci mi:
1. SAFE TO MERGE? Mogu li mergeat Dependabot PR bez izmjena u MCP server kodu?
2. NOVI TOOLOVI? Postoje li nove API metode koje bi trebale postati novi MCP toolovi?
3. BREAKING CHANGES? Jesu li postojeći toolovi zahvaćeni promjenama?
4. SLJEDECI KORAK? Jedna konkretna rečenica što trebam napraviti.

Produkt: {product['display']}
Verzija: {from_v} -> {to_v}
Release notes: {notes_url}

Release notes:
---
{notes}
---

{tool_map_block}

{'#'*60}
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analyze Aspose release notes with Claude")
    parser.add_argument("--product", help="Product slug (zip, font, note, pub). Default: all pending.")
    parser.add_argument("--from", dest="from_version", help="Old version (overrides products.json)")
    parser.add_argument("--to",   dest="to_version",   help="New version (overrides products.json)")
    parser.add_argument("--github-user", default=None,
                        help="Fallback GitHub username if github_repo not set in products.json")
    parser.add_argument("--prepare", action="store_true",
                        help="Only fetch and print context (no Claude API call). Paste output into Claude Code.")
    args = parser.parse_args()

    with open(PRODUCTS_FILE) as f:
        config = json.load(f)

    products = config["products"]
    if args.product:
        products = [p for p in products if p["slug"] == args.product]
        if not products:
            print(f"Product '{args.product}' not found in products.json")
            return

    analyzed_any = False

    for product in products:
        from_v = args.from_version or product.get("previous_version")
        to_v   = args.to_version   or product.get("current_version")

        if not from_v or not to_v:
            print(f"{product['display']}: no version change recorded, skipping. Use --from / --to to force.")
            continue

        if from_v == to_v:
            print(f"{product['display']}: already up-to-date at {to_v}, skipping.")
            continue

        print(f"\n{'='*60}")
        print(f"  {product['display']}:  {from_v}  ->  {to_v}")
        print(f"{'='*60}")

        print("Fetching release notes...", flush=True)
        notes, notes_url = fetch_release_notes(product["slug"], to_v)
        print(f"  Source: {notes_url}")

        print("Fetching tool-map.md from GitHub...", flush=True)
        github_repo = product.get("github_repo") or (
            f"{args.github_user}/{product['name']}" if args.github_user else None
        )
        tool_map = fetch_tool_map(github_repo) if github_repo else None
        if not github_repo:
            print("  Skipped (no github_repo in products.json and no --github-user given)")
        else:
            print(f"  {'Found' if tool_map else f'Not found at {github_repo}'}")

        if args.prepare:
            _print_context_for_claude(product, from_v, to_v, notes, notes_url, tool_map)
        else:
            print("Asking Claude...\n", flush=True)
            result = analyze(product, from_v, to_v, notes, notes_url, tool_map)
            print(result)

        analyzed_any = True

    if not analyzed_any:
        print("\nNothing to analyze. Run check_nuget.py first to detect version changes.")
        print("Or use: python scripts/analyze_release.py --product zip --from 26.2.0 --to 26.3.0")


if __name__ == "__main__":
    main()
