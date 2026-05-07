#!/usr/bin/env python3
"""
[CLAUDE] Analyze a new Aspose product and generate a tool map for its MCP server.
Fetches official Aspose docs, asks Claude to design the tool set, and saves
a ready-to-use tool-map.md.

Use --prepare to print context without calling the Claude API (paste into Claude Code).

Usage:
  python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words"
  python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words" --output tool-map.md
  python scripts/analyze_new_product.py --slug words --nuget "Aspose.Words" --prepare
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── HTML → plain text ─────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "aside"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._depth == 0 and data.strip():
            self.parts.append(data.strip())

    def result(self):
        return "\n".join(self.parts)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    p = _TextExtractor()
    p.feed(html)
    return p.result()


# ── Docs fetcher ──────────────────────────────────────────────────────────────

def fetch_docs(slug: str) -> dict[str, str]:
    sources = {
        "Features":        f"https://docs.aspose.com/{slug}/net/features/",
        "Developer Guide": f"https://docs.aspose.com/{slug}/net/developer-guide/",
        "Product Page":    f"https://products.aspose.com/{slug}/net/",
    }
    result = {}
    for label, url in sources.items():
        try:
            text = _fetch(url)[:4000]
            if len(text) > 200:
                result[label] = text
                print(f"  {label}: {len(text)} chars from {url}")
            else:
                print(f"  {label}: skipped (too short)")
        except Exception as e:
            print(f"  {label}: failed — {e}")
    return result


# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(slug: str, nuget: str, docs: dict[str, str]) -> str:
    docs_block = "\n\n".join(
        f"--- {label} ---\n{text}\n---" for label, text in docs.items()
    )
    return f"""You are designing an MCP (Model Context Protocol) server for {nuget} .NET library.

Product slug: {slug}
NuGet package: {nuget}

{docs_block}

Design a tool map: a list of MCP tools that expose the most useful capabilities of this library.

Respond with ONLY valid JSON — no prose, no markdown fences:
{{
  "summary": "one sentence: what this library does",
  "tools": [
    {{
      "name": "{slug}_<action>",
      "api_class": "ExactCSharpClassName",
      "description": "one-line description of what the tool does",
      "input": "key input parameters (brief)",
      "output": "what the tool returns"
    }}
  ],
  "limitations": ["things the library cannot do or evaluation mode restrictions"],
  "notes": "important implementation notes (e.g. required dependencies, evaluation watermarks)"
}}

Rules:
- tool names MUST start with "{slug}_" (all lowercase)
- api_class: the primary Aspose C# class used by that tool (exact name)
- Only include capabilities realistic based on the docs above
- 4-12 tools is the right range for most products
- limitations: be specific (read-only? no creation from scratch? evaluation watermarks?)
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
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()  # type: ignore[union-attr]
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Output ────────────────────────────────────────────────────────────────────

def _print_result(result: dict, slug: str):
    print(f"\nSummary: {result.get('summary', '')}")
    print(f"\nTools ({len(result.get('tools', []))}):")
    for t in result.get("tools", []):
        print(f"  {t['name']:35s} [{t.get('api_class','?')}]")
        print(f"    {t.get('description','')}")
    lims = result.get("limitations") or []
    if lims:
        print("\nLimitations:")
        for lim in lims:
            print(f"  - {lim}")
    notes = result.get("notes", "")
    if notes:
        print(f"\nNotes: {notes}")


def _to_tool_map(result: dict, slug: str, nuget: str) -> str:
    lines = [
        f"# Tool Map — {nuget} MCP Server\n",
        f"> {result.get('summary', '')}\n",
        "## Tools\n",
        "| Tool | API Class | Description |",
        "|---|---|---|",
    ]
    for t in result.get("tools", []):
        lines.append(f"| `{t['name']}` | `{t.get('api_class','?')}` | {t.get('description','')} |")

    lines += [
        "\n## Input / Output\n",
        "| Tool | Input | Output |",
        "|---|---|---|",
    ]
    for t in result.get("tools", []):
        lines.append(f"| `{t['name']}` | {t.get('input','')} | {t.get('output','')} |")

    lims = result.get("limitations") or []
    if lims:
        lines += ["\n## Limitations\n"]
        for lim in lims:
            lines.append(f"- {lim}")

    notes = result.get("notes", "")
    if notes:
        lines += ["\n## Implementation Notes\n", notes]

    lines += [
        "\n## Reference",
        f"- Developer Guide: https://docs.aspose.com/{slug}/net/developer-guide/",
        f"- API Reference:   https://reference.aspose.com/{slug}/net/",
        f"- GitHub Examples: https://github.com/aspose-{slug}/Aspose.{slug.capitalize()}-for-.NET",
    ]
    return "\n".join(lines) + "\n"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="[CLAUDE] Analyze a new Aspose product and generate tool-map.md"
    )
    parser.add_argument("--slug",    required=True, help="Product slug, lowercase (e.g. words, imaging)")
    parser.add_argument("--nuget",   required=True, help="NuGet package name (e.g. Aspose.Words)")
    parser.add_argument("--output",  default=None,
                        help="Save tool-map.md to this path (default: print only)")
    parser.add_argument("--prepare", action="store_true",
                        help="Print context only — no Claude API call. Paste into Claude Code.")
    args = parser.parse_args()

    print(f"Fetching docs for {args.nuget} ({args.slug})...")
    docs = fetch_docs(args.slug)

    if not docs:
        print("ERROR: Could not fetch any docs. Check the slug is correct.")
        return

    prompt = _build_prompt(args.slug, args.nuget, docs)

    if args.prepare:
        print(f"\n{'#'*60}")
        print("# PASTE INTO CLAUDE CODE")
        print(f"{'#'*60}\n")
        print(prompt)
        print(f"\n{'#'*60}")
        print("# After Claude responds, save the JSON and run:")
        print(f"# python scripts/new_product.py --slug {args.slug} --nuget \"{args.nuget}\" --version X.Y.Z --output-dir ...")
        print(f"{'#'*60}")
        return

    print("\nAsking Claude...", flush=True)
    try:
        result = ask_claude(prompt)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return

    _print_result(result, args.slug)

    tool_map = _to_tool_map(result, args.slug, args.nuget)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(tool_map)
        print(f"\nSaved: {args.output}")
    else:
        print(f"\n{'─'*60}")
        print("tool-map.md preview (use --output to save):")
        print('─'*60)
        print(tool_map)


if __name__ == "__main__":
    main()
