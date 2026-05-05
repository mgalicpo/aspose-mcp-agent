#!/usr/bin/env python3
"""
[ASPOSE LLM] Release analysis using the Aspose/Professionalize LLM gateway.
Equivalent to analyze_release.py but uses llm.professionalize.com instead
of the Anthropic API. Requires ASPOSE_LLM_TOKEN env var.

Uses a ReAct validation loop: after each LLM response, validators check the
claims against ground truth (NuGet API, release notes text). Failures are fed
back to the model for revision, up to MAX_REACT_ITERATIONS times.

Gateway docs: see CLAUDE.md
Models: recommended (default), experimental, qwen3-next, gpt-oss

Usage:
  python scripts/analyze_release_aspose.py                      # all pending
  python scripts/analyze_release_aspose.py --product zip        # specific product
  python scripts/analyze_release_aspose.py --model experimental # coding model
  python scripts/analyze_release_aspose.py --product zip --from 26.3.0 --to 26.4.0
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# Windows consoles default to cp1250 which can't handle many Unicode chars
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from html.parser import HTMLParser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS_FILE = os.path.join(REPO_ROOT, "products.json")

ASPOSE_LLM_BASE = "https://llm.professionalize.com"


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
DEFAULT_MODEL = "recommended"
MAX_REACT_ITERATIONS = 3


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

def _candidate_urls(slug: str, version: str) -> list[str]:
    major, minor, patch = (version.split(".") + ["0"])[:3]
    year = f"20{major}"
    base = f"https://releases.aspose.com/{slug}/net/release-notes/{year}"
    return [
        f"{base}/aspose-{slug}-for-net-{major}-{minor}-{patch}-release-notes/",
        f"{base}/aspose-{slug}-for-net-{major}-{minor}-release-notes/",
        f"{base}/aspose-{slug}-for-net-{major}-{minor}-0-release-notes/",
    ]


def fetch_release_notes(slug: str, version: str) -> tuple[str, str]:
    major = version.split(".")[0]
    for url in _candidate_urls(slug, version):
        try:
            text = _html_to_text(_fetch(url))
            if major in text:
                return text[:5000], url
        except Exception:
            continue

    year = f"20{major}"
    fallback = f"https://releases.aspose.com/{slug}/net/release-notes/"
    msg = (
        f"Release notes for {slug} {version} not yet published on releases.aspose.com.\n"
        f"Check manually: {fallback}{year}/ once Aspose publishes them.\n"
        f"Recommendation: bump the NuGet version, run CI, and merge if tests pass."
    )
    return msg, fallback


def _gh_token() -> str | None:
    import subprocess
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        token = result.stdout.strip()
        return token if token else None
    except Exception:
        return None


def fetch_tool_map(github_repo: str) -> str | None:
    """Fetch tool-map.md. Tries raw URL first, then GitHub API with gh token (for private repos)."""
    raw_url = f"https://raw.githubusercontent.com/{github_repo}/main/tool-map.md"
    try:
        return _fetch(raw_url)
    except Exception:
        pass

    token = _gh_token()
    if not token:
        return None
    api_url = f"https://api.github.com/repos/{github_repo}/contents/tool-map.md"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.raw+json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ── Aspose LLM call (OpenAI-compatible) ──────────────────────────────────────

def _llm_call(token: str, model: str, prompt: str) -> str:
    """Single call to the Aspose LLM gateway (/v1/chat/completions)."""
    url = f"{ASPOSE_LLM_BASE}/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def _llm_call_with_retry(token: str, model: str, prompt: str,
                         max_attempts: int = 3) -> str:
    """
    Guardrail: retry up to max_attempts times, feeding the error back to the
    model on each retry (as recommended in CLAUDE.md for mid-tier models).
    """
    last_error = None
    for attempt in range(max_attempts):
        user_prompt = prompt if attempt == 0 else (
            f"{prompt}\n\n"
            f"[Previous attempt failed: {last_error}. "
            f"Please provide a complete, well-structured answer.]"
        )
        try:
            return _llm_call(token, model, user_prompt)
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            last_error = str(e)
        print(f"  [retry {attempt + 1}/{max_attempts}] Error: {last_error}")

    raise RuntimeError(
        f"[ASPOSE LLM] Failed after {max_attempts} attempts. Last error: {last_error}"
    )


# ── Analysis ──────────────────────────────────────────────────────────────────

def _build_prompt(product: dict, from_version: str, to_version: str,
                  release_notes: str, notes_url: str, tool_map: str | None) -> str:
    tool_map_block = (
        f"Current tool-map.md:\n---\n{tool_map}\n---"
        if tool_map
        else "tool-map.md not available (repo not published yet)."
    )
    return f"""You are reviewing an Aspose .NET library update to decide if an MCP server needs changes.

Product: {product['display']}
Version: {from_version} -> {to_version}
Release notes source: {notes_url}

Release notes (excerpt):
---
{release_notes}
---

{tool_map_block}

Respond with ONLY valid JSON — no prose, no markdown fences:
{{
  "safe_to_merge": true or false,
  "reason": "one sentence explaining the safe_to_merge decision",
  "confidence": 0.0 to 1.0,
  "new_tools": [
    {{"name": "tool_name", "api_class": "ExactCSharpClassName", "description": "one-line description"}}
  ],
  "breaking_changes": ["description of each breaking change"],
  "next_step": "one concrete sentence: what the developer should do right now"
}}

Rules:
- confidence: your certainty in the safe_to_merge decision. Use < 0.7 when release notes are missing, incomplete, or ambiguous.
- new_tools: only APIs explicitly listed in the release notes above. "api_class" must be the exact C# class name as written in the release notes.
- If no new tools, use: "new_tools": []
- If no breaking changes, use: "breaking_changes": []
"""


# ── ReAct validators ──────────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


CONFIDENCE_THRESHOLD = 0.7

def _validate_schema(decision: dict):
    """Raise ValueError if required fields are missing or wrong type."""
    if not isinstance(decision.get("safe_to_merge"), bool):
        raise ValueError(f"'safe_to_merge' must be bool, got: {decision.get('safe_to_merge')!r}")
    for field in ("reason", "next_step"):
        if not isinstance(decision.get(field), str):
            raise ValueError(f"'{field}' must be a string")
    if not isinstance(decision.get("new_tools"), list):
        raise ValueError("'new_tools' must be an array")
    if not isinstance(decision.get("breaking_changes"), list):
        raise ValueError("'breaking_changes' must be an array")
    confidence = decision.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise ValueError(f"'confidence' must be a number, got: {confidence!r}")


def _version_exists_on_nuget(nuget: str, version: str) -> bool:
    """Check that the target version actually exists on NuGet."""
    url = f"https://api.nuget.org/v3-flatcontainer/{nuget.lower()}/index.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            versions = json.loads(r.read())["versions"]
        return version in versions
    except Exception:
        return True  # Don't block analysis on network error


def _validate_analysis(decision: dict, to_version: str, nuget: str,
                        release_notes: str) -> list[str]:
    """
    Run ground-truth checks on the LLM's claims.
    Returns a list of failure messages (empty = all passed).
    """
    failures = []

    # Check 1: if safe_to_merge, the target version must exist on NuGet
    if decision["safe_to_merge"] and not _version_exists_on_nuget(nuget, to_version):
        failures.append(
            f"Version {to_version} of {nuget} was not found on NuGet. "
            f"This version may not exist — reconsider safe_to_merge."
        )

    # Check 2: each suggested new tool's api_class must appear in the release notes
    for tool in decision.get("new_tools", []):
        api_class = (tool.get("api_class") or "").strip()
        if api_class and api_class not in release_notes:
            failures.append(
                f"New tool '{tool.get('name')}' references api_class '{api_class}' "
                f"but this class name was not found in the release notes text. "
                f"Only suggest tools for APIs explicitly listed in the release notes."
            )

    return failures


# ── ReAct loop ────────────────────────────────────────────────────────────────

def analyze_with_react(token: str, model: str, product: dict, from_version: str,
                       to_version: str, release_notes: str, notes_url: str,
                       tool_map: str | None) -> tuple[dict, int]:
    """
    ReAct loop: ACT (LLM call) → OBSERVE (validate claims) → feed failures back.
    Returns (decision, iterations_used).
    """
    base_prompt = _build_prompt(product, from_version, to_version,
                                release_notes, notes_url, tool_map)
    current_prompt = base_prompt
    decision = None

    for iteration in range(MAX_REACT_ITERATIONS):
        # ACT
        try:
            raw = _llm_call_with_retry(token, model, current_prompt)
            decision = _parse_json_response(raw)
            _validate_schema(decision)
        except (json.JSONDecodeError, ValueError) as e:
            msg = f"Response was not valid JSON: {e}"
            print(f"  [ReAct {iteration + 1}/{MAX_REACT_ITERATIONS}] {msg}")
            current_prompt = base_prompt + (
                f"\n\nOBSERVE: {msg}. Return ONLY valid JSON, no prose."
            )
            continue

        # OBSERVE
        failures = _validate_analysis(decision, to_version, product["nuget"], release_notes)

        if not failures:
            if iteration > 0:
                print(f"  [ReAct] Validation passed on iteration {iteration + 1}.")
            return decision, iteration + 1

        failures_text = "\n".join(f"  - {f}" for f in failures)
        print(f"  [ReAct {iteration + 1}/{MAX_REACT_ITERATIONS}] "
              f"{len(failures)} validation failure(s), revising...")
        current_prompt = base_prompt + (
            f"\n\nOBSERVE — Validation checks found issues with your previous analysis:\n"
            f"{failures_text}\n\n"
            f"Revise your analysis based on these findings. Return only valid JSON."
        )

    print(f"  [ReAct] Returning best-effort result after {MAX_REACT_ITERATIONS} iterations.")
    return decision, MAX_REACT_ITERATIONS


def _check_escalation(decision: dict, react_iterations: int) -> list[str]:
    """
    Returns escalation warnings if confidence is low or ReAct didn't converge.
    These are surfaced to the developer — not fed back to the model.
    """
    warnings = []
    confidence = decision.get("confidence")
    if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        warnings.append(
            f"Low confidence ({confidence:.2f} < {CONFIDENCE_THRESHOLD}). "
            f"Release notes may be missing or ambiguous — recommend manual review before merging."
        )
    if react_iterations >= MAX_REACT_ITERATIONS:
        warnings.append(
            f"ReAct did not converge after {MAX_REACT_ITERATIONS} iterations. "
            f"Result is best-effort — recommend manual verification."
        )
    return warnings


# ── Output formatting ─────────────────────────────────────────────────────────

def _print_result(decision: dict, escalation_warnings: list[str]):
    safe = decision.get("safe_to_merge", False)
    confidence = decision.get("confidence")
    conf_str = f"  [confidence: {confidence:.2f}]" if confidence is not None else ""

    print(f"1. SAFE TO MERGE: {'YES' if safe else 'NO'}{conf_str}")
    print(f"   {decision.get('reason', '')}")

    new_tools = decision.get("new_tools") or []
    print(f"\n2. NEW TOOLS: {'None' if not new_tools else ''}")
    for t in new_tools:
        print(f"   - {t.get('name')}: {t.get('description', '')}  [API: {t.get('api_class', '?')}]")

    breaking = decision.get("breaking_changes") or []
    print(f"\n3. BREAKING CHANGES: {'None' if not breaking else ''}")
    for b in breaking:
        print(f"   - {b}")

    print(f"\n4. NEXT STEP:")
    print(f"   {decision.get('next_step', '')}")

    if escalation_warnings:
        print(f"\n{'!'*60}")
        print("  ESCALATION — manual review recommended:")
        for w in escalation_warnings:
            print(f"  ! {w}")
        print(f"{'!'*60}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="[ASPOSE LLM] Analyze Aspose release notes via llm.professionalize.com"
    )
    parser.add_argument("--product", help="Product slug (zip, font, note, pub). Default: all pending.")
    parser.add_argument("--from", dest="from_version", help="Old version (overrides products.json)")
    parser.add_argument("--to",   dest="to_version",   help="New version (overrides products.json)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Aspose LLM model to use (default: {DEFAULT_MODEL}). "
                             f"Options: recommended, experimental, qwen3-next, gpt-oss")
    args = parser.parse_args()

    token = os.environ.get("ASPOSE_LLM_TOKEN", "").strip()
    if not token:
        print("ERROR: Set the ASPOSE_LLM_TOKEN environment variable.")
        print("  Get a token at: https://sup.dynabic.com/ (category: Access token request)")
        print("  Contacts: danil.ivanov@aspose.com, hasan.jamal@aspose.com")
        return

    print(f"[ASPOSE LLM] Using model: {args.model} @ {ASPOSE_LLM_BASE}")

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
        github_repo = product.get("github_repo")
        tool_map = fetch_tool_map(github_repo) if github_repo else None
        if not github_repo:
            print("  Skipped (no github_repo in products.json)")
        else:
            print(f"  {'Found' if tool_map else f'Not found at {github_repo}'}")

        print(f"Asking {args.model} (ReAct validation enabled)...\n", flush=True)
        try:
            decision, iterations = analyze_with_react(token, args.model, product,
                                                      from_v, to_v, notes,
                                                      notes_url, tool_map)
            warnings = _check_escalation(decision, iterations)
            _print_result(decision, warnings)
        except RuntimeError as e:
            print(f"ERROR: {e}")

        analyzed_any = True

    if not analyzed_any:
        print("\nNothing to analyze. Run check_nuget.py first to detect version changes.")
        print("Or use: python scripts/analyze_release_aspose.py --product zip --from 26.3.0 --to 26.4.0")


if __name__ == "__main__":
    main()
