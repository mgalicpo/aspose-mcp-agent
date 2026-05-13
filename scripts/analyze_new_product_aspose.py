#!/usr/bin/env python3
"""
[ASPOSE LLM] Analyze a new Aspose product and generate a tool map for its MCP server.
Fetches official Aspose docs, asks the LLM to design the tool set, validates the
response, and saves a ready-to-use tool-map.md.

Usage:
  python scripts/analyze_new_product_aspose.py --slug words --nuget "Aspose.Words"
  python scripts/analyze_new_product_aspose.py --slug words --nuget "Aspose.Words" --output tool-map.md
  python scripts/analyze_new_product_aspose.py --slug words --nuget "Aspose.Words" --model experimental
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASPOSE_LLM_BASE = "https://llm.professionalize.com"
DEFAULT_MODEL   = "recommended"
MAX_REACT_ITERATIONS = 3

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def _load_env():
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
    """Fetch key Aspose docs pages. Returns {label: text}."""
    sources = {
        "Features":       f"https://docs.aspose.com/{slug}/net/features/",
        "Developer Guide": f"https://docs.aspose.com/{slug}/net/developer-guide/",
        "Product Page":   f"https://products.aspose.com/{slug}/net/",
    }
    result = {}
    for label, url in sources.items():
        try:
            text = _fetch(url)[:4000]
            if len(text) > 200:
                result[label] = text
                print(f"  {label}: {len(text)} chars from {url}")
            else:
                print(f"  {label}: skipped (too short) — {url}")
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
- Only include capabilities that are realistic based on the docs above
- 4-12 tools is the right range for most products
- limitations: be specific (read-only? no creation from scratch? evaluation watermarks?)
"""


# ── Aspose LLM call ───────────────────────────────────────────────────────────

def _llm_call(token: str, model: str, prompt: str) -> str:
    url = f"{ASPOSE_LLM_BASE}/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def _llm_call_with_retry(token: str, model: str, prompt: str,
                         max_attempts: int = 3) -> str:
    """
    Network-level retry: transparently retries on timeout/HTTP errors.
    Does NOT modify the prompt — these are transient failures, not semantic ones.
    """
    last_error = None
    for attempt in range(max_attempts):
        try:
            return _llm_call(token, model, prompt)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise RuntimeError(
                    f"[ASPOSE LLM] Client error {e.code} — check token and parameters"
                ) from e
            last_error = str(e)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_error = str(e)
        except Exception as e:
            last_error = str(e)
        print(f"  [network retry {attempt+1}/{max_attempts}] {last_error}", flush=True)
        if attempt < max_attempts - 1:
            time.sleep(2 ** attempt)  # 1s, 2s
    raise RuntimeError(f"LLM unreachable after {max_attempts} attempts: {last_error}")


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _validate_schema(result: dict, slug: str) -> list[str]:
    """Returns list of validation failures."""
    failures = []
    if not isinstance(result.get("tools"), list) or len(result["tools"]) < 2:
        failures.append("'tools' must be a non-empty array with at least 2 tools.")
    for tool in result.get("tools", []):
        name = tool.get("name", "")
        if not name.startswith(f"{slug}_"):
            failures.append(f"Tool name '{name}' must start with '{slug}_'.")
        if not tool.get("api_class"):
            failures.append(f"Tool '{name}' is missing 'api_class'.")
    if not result.get("summary"):
        failures.append("'summary' field is required.")
    return failures


def analyze_with_react(token: str, model: str, slug: str, nuget: str,
                       docs: dict[str, str]) -> dict:
    base_prompt = _build_prompt(slug, nuget, docs)
    current_prompt = base_prompt

    for iteration in range(MAX_REACT_ITERATIONS):
        # ACT — network errors retried transparently, not fed to LLM
        try:
            raw = _llm_call_with_retry(token, model, current_prompt)
        except RuntimeError:
            raise  # network completely unreachable, give up

        # Parse JSON — semantic error, feed back as OBSERVE
        try:
            result = _parse_json(raw)
        except json.JSONDecodeError as e:
            msg = f"Response was not valid JSON: {e}"
            print(f"  [ReAct {iteration+1}/{MAX_REACT_ITERATIONS}] {msg}")
            current_prompt = base_prompt + f"\n\nOBSERVE: {msg}. Return ONLY valid JSON."
            continue

        # OBSERVE
        failures = _validate_schema(result, slug)
        if not failures:
            if iteration > 0:
                print(f"  [ReAct] Passed on iteration {iteration+1}.")
            return result

        failures_text = "\n".join(f"  - {f}" for f in failures)
        print(f"  [ReAct {iteration+1}/{MAX_REACT_ITERATIONS}] {len(failures)} issue(s), revising...")
        current_prompt = base_prompt + (
            f"\n\nOBSERVE — Issues found:\n{failures_text}\n\nRevise and return only valid JSON."
        )

    print(f"  [ReAct] Best-effort result after {MAX_REACT_ITERATIONS} iterations.")
    return result


# ── Output ────────────────────────────────────────────────────────────────────

def _print_result(result: dict, slug: str, nuget: str):
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
        description="[ASPOSE LLM] Analyze a new Aspose product and generate tool-map.md"
    )
    parser.add_argument("--slug",   required=True, help="Product slug, lowercase (e.g. words, imaging)")
    parser.add_argument("--nuget",  required=True, help="NuGet package name (e.g. Aspose.Words)")
    parser.add_argument("--output", default=None,
                        help="Save tool-map.md to this path (default: print only)")
    parser.add_argument("--model",  default=DEFAULT_MODEL,
                        help=f"Aspose LLM model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    token = os.environ.get("ASPOSE_LLM_TOKEN", "").strip()
    if not token:
        print("ERROR: Set ASPOSE_LLM_TOKEN in .env or environment.")
        return

    print(f"[ASPOSE LLM] {args.model} @ {ASPOSE_LLM_BASE}")
    print(f"\nFetching docs for {args.nuget} ({args.slug})...")
    docs = fetch_docs(args.slug)

    if not docs:
        print("ERROR: Could not fetch any docs. Check the slug is correct.")
        return

    print(f"\nAsking {args.model} (ReAct enabled)...", flush=True)
    result = analyze_with_react(token, args.model, args.slug, args.nuget, docs)

    _print_result(result, args.slug, args.nuget)

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
