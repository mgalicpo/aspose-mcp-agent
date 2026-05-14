#!/usr/bin/env python3
"""
[ASPOSE LLM] Generates tool implementations in a scaffolded C# MCP server
based on tool-map.md. Uses qwen3-next (coding model) with a build-validate-fix
ReAct loop: generate -> dotnet build -> feed errors back -> fix (up to 3x).

Usage:
  python scripts/implement_tools_aspose.py --repo-dir D:/GIT/FinishedMCPservers/aspose-drawing-mcp
  python scripts/implement_tools_aspose.py --repo-dir D:/GIT/FinishedMCPservers/aspose-drawing-mcp --no-build
  python scripts/implement_tools_aspose.py --repo-dir D:/GIT/FinishedMCPservers/aspose-drawing-mcp --commit
  python scripts/implement_tools_aspose.py --repo-dir D:/GIT/FinishedMCPservers/aspose-drawing-mcp --model experimental
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Windows consoles default to cp1250 which can't handle many Unicode chars
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# Load .env from repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env = os.path.join(REPO_ROOT, ".env")
if os.path.exists(_env):
    for _line in open(_env):
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.strip().partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

ASPOSE_LLM_BASE = "https://llm.professionalize.com"
DEFAULT_MODEL   = "qwen3-next"   # coding model per CLAUDE.md
MAX_ITERATIONS  = 3


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _llm_call(token: str, model: str, prompt: str) -> str:
    url     = f"{ASPOSE_LLM_BASE}/v1/chat/completions"
    payload = json.dumps({
        "model":      model,
        "messages":   [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def _llm_call_with_retry(token: str, model: str, prompt: str,
                         max_attempts: int = 3) -> str:
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
        except Exception as e:
            last_error = str(e)
        print(f"  [retry {attempt + 1}/{max_attempts}] {last_error}", flush=True)
        if attempt < max_attempts - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"LLM unreachable after {max_attempts} attempts: {last_error}")


# ── Response parsing ───────────────────────────────────────────────────────────

def _extract_code(raw: str) -> str:
    """Extract C# code from LLM response — handles JSON wrapper or raw code block."""
    raw = raw.strip()
    # Try JSON: {"tools_file": "..."}
    try:
        cleaned = re.sub(r"^```json\s*", "", raw)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip())
        data = json.loads(cleaned)
        if "tools_file" in data:
            return data["tools_file"]
    except Exception:
        pass
    # Try fenced code block
    m = re.search(r"```(?:csharp|cs)?\s*([\s\S]+?)```", raw)
    if m:
        return m.group(1).strip()
    return raw


# ── Repo helpers ───────────────────────────────────────────────────────────────

def _find_tools_file(repo_dir: str) -> str | None:
    matches = glob.glob(
        os.path.join(repo_dir, "src", "**", "Tools", "*.cs"), recursive=True
    )
    return matches[0] if matches else None


def _find_csproj(repo_dir: str) -> str | None:
    matches = glob.glob(
        os.path.join(repo_dir, "src", "**", "*.csproj"), recursive=True
    )
    return matches[0] if matches else None


def _dotnet_build(repo_dir: str) -> tuple[int, str]:
    result = subprocess.run(
        ["dotnet", "build", "--configuration", "Release", "--nologo"],
        cwd=repo_dir, capture_output=True, text=True
    )
    return result.returncode, result.stdout + result.stderr


# ── Prompt builder ─────────────────────────────────────────────────────────────

def _build_prompt(tool_map: str, scaffold: str, csproj: str,
                  nuget: str, build_error: str | None) -> str:
    error_block = ""
    if build_error:
        error_block = f"""
## Build errors from previous attempt — fix ALL of them
```
{build_error[:3000]}
```
"""
    return f"""You are a C# developer implementing an Aspose .NET MCP server.

## Task
Implement all MCP tools listed in the tool-map below.
Return ONLY a JSON object in this exact format:
{{"tools_file": "<complete compilable C# file content>"}}

## Tool Map
{tool_map}

## Existing scaffold — follow this pattern exactly
```csharp
{scaffold}
```

## Project file — use the NuGet package shown here
```xml
{csproj}
```

## Rules
- Keep [McpServerToolType] on the class and [McpServerTool] on every tool method
- Every tool returns: {{"success": true, "data": {{...}}}} or {{"success": false, "error": {{"code": "...", "message": "..."}}}}
- Use the static Success(object) and Error(string, string) helpers from the scaffold
- Wrap all Aspose calls in try/catch — return Error on any exception
- Use {nuget} API classes exactly as named in the tool-map api_class column
- No TODO comments — every tool must be fully implemented
- File must compile without errors against .NET 8 and {nuget}{error_block}"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="[ASPOSE LLM] Implement MCP tools from tool-map.md using qwen3-next"
    )
    parser.add_argument("--repo-dir", required=True,
                        help="Path to local MCP repo (e.g. D:/GIT/FinishedMCPservers/aspose-drawing-mcp)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"LLM model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-build", action="store_true",
                        help="Skip dotnet build validation")
    parser.add_argument("--commit", action="store_true",
                        help="git commit the generated Tools.cs after successful build")
    args = parser.parse_args()

    token = os.getenv("ASPOSE_LLM_TOKEN")
    if not token:
        raise SystemExit("ASPOSE_LLM_TOKEN not set. See .env.example.")

    repo_dir = os.path.abspath(args.repo_dir)
    if not os.path.isdir(repo_dir):
        raise SystemExit(f"Repo not found: {repo_dir}")

    # Read context
    tool_map_path = os.path.join(repo_dir, "tool-map.md")
    if not os.path.exists(tool_map_path):
        raise SystemExit(f"tool-map.md not found in {repo_dir}")
    tool_map = open(tool_map_path, encoding="utf-8").read()

    tools_file = _find_tools_file(repo_dir)
    if not tools_file:
        raise SystemExit("Tools/*.cs not found under src/ — is this a valid scaffold?")
    scaffold = open(tools_file, encoding="utf-8").read()

    csproj = _find_csproj(repo_dir)
    csproj_content = open(csproj, encoding="utf-8").read() if csproj else ""

    m = re.search(r'Include="(Aspose\.[^"]+)"', csproj_content)
    nuget = m.group(1) if m else "Aspose library"

    print(f"[ASPOSE LLM] Using model: {args.model} @ {ASPOSE_LLM_BASE}")
    print(f"\nRepo:       {repo_dir}")
    print(f"Tools file: {os.path.relpath(tools_file, repo_dir)}")
    print(f"NuGet:      {nuget}")
    print(f"Tool map:   {len([ln for ln in tool_map.splitlines() if ln.strip()])} lines")

    build_error = None
    success = False

    for iteration in range(1, MAX_ITERATIONS + 1):
        label = "Generating" if iteration == 1 else f"Fixing (attempt {iteration}/{MAX_ITERATIONS})"
        print(f"\n-- {label} " + "-" * max(0, 48 - len(label)), flush=True)

        prompt = _build_prompt(tool_map, scaffold, csproj_content, nuget, build_error)
        raw    = _llm_call_with_retry(token, args.model, prompt)
        code   = _extract_code(raw)

        with open(tools_file, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"  Written {len(code.splitlines())} lines to "
              f"{os.path.relpath(tools_file, repo_dir)}")

        if args.no_build:
            print("  Skipping build (--no-build).")
            success = True
            break

        print("\n-- dotnet build " + "-" * 44)
        exit_code, output = _dotnet_build(repo_dir)
        # Print last 40 lines of build output
        lines = output.splitlines()
        for line in lines[-40:]:
            print(" ", line)

        if exit_code == 0:
            print("\n  Build successful.")
            success = True
            break

        build_error = output
        if iteration < MAX_ITERATIONS:
            print(f"\n  Build failed -- feeding errors back to LLM (iteration {iteration}/{MAX_ITERATIONS})...")
        else:
            print(f"\n  Build failed after {MAX_ITERATIONS} attempts -- manual fix needed.")

    if not success:
        print("\nResult: FAILED")
        sys.exit(1)

    print("\nResult: OK")

    if args.commit:
        subprocess.run(["git", "-C", repo_dir, "add", tools_file], check=True)
        code_out, _ = subprocess.Popen(
            ["git", "-C", repo_dir, "commit", "-m",
             f"feat: implement {nuget} MCP tools via implement_tools_aspose.py"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        ).communicate()
        print(f"  {code_out.strip()}")


if __name__ == "__main__":
    main()
