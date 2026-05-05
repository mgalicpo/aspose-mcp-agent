# mcp-agent — Project Overview

This repo is a **central version tracker and upgrade automation tool** for a suite of Aspose .NET MCP servers.

## What This Repo Does

We maintain 4 MCP servers for Aspose .NET libraries, each in its own GitHub repo:

| Product | Local path | GitHub |
|---|---|---|
| Aspose.Font | `D:\GIT\FinishedMCPservers\aspose-font-mcp` | `mgalicpo/aspose-font-mcp` |
| Aspose.ZIP  | `D:\GIT\FinishedMCPservers\aspose-zip-mcp`  | `mgalicpo/aspose-zip-mcp`  |
| Aspose.Note | `D:\GIT\FinishedMCPservers\aspose-note-mcp` | `mgalicpo/aspose-note-mcp` |
| Aspose.PUB  | `D:\GIT\FinishedMCPservers\aspose-pub-mcp`  | `mgalicpo/aspose-pub-mcp`  |

All repos are **private**. Canonical version state is tracked in `products.json`.

## Scripts

### Existing product — version updates
| Script | What it does |
|---|---|
| `scripts/check_nuget.py` | Polls NuGet API for new versions, updates `products.json`, creates GitHub Issue |
| `scripts/analyze_release_aspose.py` | Fetches release notes + `tool-map.md`, ReAct LLM analysis, confidence scoring |
| `scripts/analyze_release.py` | Same but uses Anthropic API (`--prepare` for no-key mode) |
| `scripts/merge_dependabot_aspose.py` | Lists Dependabot PRs, asks LLM if safe to merge, optionally merges |
| `scripts/merge_dependabot.py` | Same but uses Anthropic API |
| `scripts/upgrade_product.py` | Bumps `.csproj`, `dotnet build` + `dotnet test`, commits and pushes |

### New product — onboarding
| Script | What it does |
|---|---|
| `scripts/analyze_new_product_aspose.py` | Fetches Aspose docs, generates tool-map.md via Aspose LLM |
| `scripts/analyze_new_product.py` | Same but uses Anthropic API (`--prepare` for no-key mode) |
| `scripts/new_product.py` | Scaffolds full C# project, creates GitHub repo, registers in `products.json` |

## Typical Workflows

**Version update:**
```
check_nuget.py → analyze_release_aspose.py → upgrade_product.py
```

**New product:**
```
analyze_new_product_aspose.py → new_product.py → implement tools in Claude Code
```

`check_nuget.py` runs automatically every Monday via GitHub Actions and opens a GitHub Issue when updates are found.

## Key Files

- `products.json` — canonical state: current and previous NuGet version per product
- `.env` — `ASPOSE_LLM_TOKEN` (gitignored, never commit)
- `tool-map.md` in each MCP repo — maps Aspose API sections to MCP tool names; fetched by analyze scripts

## MCP Server Architecture (C# / .NET 8)

Each MCP server follows the same pattern:
- `[McpServerToolType]` class with `[McpServerTool]` static methods
- Returns JSON: `{"success": true, "data": {...}}` or `{"success": false, "error": {"code": "...", "message": "..."}}`
- `WithToolsFromAssembly()` auto-discovers all tools — no manual registration
- License via `ASPOSE_LICENSE_PATH` env var, graceful fallback to evaluation mode
- Tests: xUnit, `IDisposable` for temp file cleanup, Arrange-Act-Assert pattern

---

# Aspose / Professionalize — LLM Infrastructure

## Backend

All models are served through a single LiteLLM-powered gateway:

```
Base URL:  https://llm.professionalize.com/
Auth:      Authorization: Bearer <access_token>
```

Access tokens are requested at https://sup.dynabic.com/ (tracker: Support/Helpdesk, category: Access token request).
Contacts: danil.ivanov@aspose.com, hasan.jamal@aspose.com

---

## Available Models

| Name | Underlying model | Endpoint | Best for |
|---|---|---|---|
| `recommended` | same as `gpt-oss` | `/v1/chat/completions` | **Default choice** for most use cases |
| `gpt-oss` | GPT-OSS-120b | `/v1/chat/completions` | General tasks — best quality/performance on this stack |
| `experimental` | same as `qwen3-next` | `/v1/chat/completions` | Coding tasks (experimental alias) |
| `qwen3-next` | Qwen3-Coder-Next FP8 | `/v1/chat/completions` | Code generation, code understanding, coding agents |
| `qwen3-embedding-8b` | Qwen3-Embedding-8B | `/v1/embeddings` | Semantic embeddings — **only model for this endpoint** |
| `Qwen2.5-VL-7B` | Qwen2.5-VL-7B-Instruct | `/v1/chat/completions` | Image recognition, visual understanding, multimodal input |

**Important:** `recommended` and `experimental` are stable aliases — the underlying model may change over time. Prefer these aliases in production code so upgrades are transparent.

### Task → Model mapping

| Task | Model to use |
|---|---|
| General text generation, summarisation, Q&A | `recommended` |
| Classification, extraction, structured output | `recommended` |
| Code generation, refactoring, code review | `qwen3-next` / `experimental` |
| Semantic search, RAG vector store population | `qwen3-embedding-8b` |
| Image description, OCR-assist, visual Q&A | `Qwen2.5-VL-7B` |
| Agentic pipelines with tool calls | `recommended` (gpt-oss) — higher reliability |
| Experimental coding agents | `experimental` |

---

## API Usage Examples

**Chat completion:**
```bash
curl -X POST https://llm.professionalize.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"model":"recommended","messages":[{"role":"user","content":"Hello"}]}'
```

**Embeddings:**
```bash
curl -X POST https://llm.professionalize.com/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"model":"qwen3-embedding-8b","input":"text to embed"}'
```

**Vision (image + text):**
```bash
curl -X POST https://llm.professionalize.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "model": "Qwen2.5-VL-7B",
    "messages": [{"role":"user","content":[
      {"type":"text","text":"Describe this image"},
      {"type":"image_url","image_url":{"url":"<image_url>"}}
    ]}],
    "max_tokens": 512,
    "temperature": 0
  }'
```

---

## Guardrails — Mandatory Practices

These models are **mid-tier**: they hallucinate more often and break structured output more frequently than flagship models. Invalid JSON, made-up field names, confident-but-wrong answers are expected, not anomalies. Guardrails are not optional.

### 1. Retry with re-prompting (always apply)

On invalid response, retry up to 3 times — **always pass the error back to the model**, not just re-send the original prompt.

```python
def call_with_retry(prompt: str, max_attempts: int = 3) -> dict:
    last_error = None
    for attempt in range(max_attempts):
        user_prompt = prompt if attempt == 0 else (
            f"{prompt}\n\nPrevious attempt failed with error: {last_error}. "
            f"Return valid JSON."
        )
        raw = llm.complete(user_prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = str(e)
    raise RuntimeError(f"Failed after {max_attempts} attempts")
```

### 2. Schema-based validation (always apply for structured output)

Never trust structured output without validating it. Use Pydantic or JSON Schema. Feed validation errors back into the retry loop.

```python
from pydantic import BaseModel, ValidationError

class MyOutput(BaseModel):
    field1: str
    field2: int

def extract(text: str) -> MyOutput:
    raw = llm.complete(f"Extract as JSON: {text}")
    try:
        return MyOutput.model_validate_json(raw)
    except ValidationError as e:
        raise ValueError(f"Schema mismatch: {e.errors()}")  # → retry loop
```

Core loop: **validate → error → re-prompt with error text → re-validate**

### 3. Self-correction loops (use selectively — critical steps only)

Two-call pattern: generate answer, then critique it. Costs extra tokens and latency — enable only where semantic correctness matters more than speed.

```python
def self_correct(task: str) -> str:
    draft = llm.complete(f"Task: {task}\nAnswer:")
    critique = llm.complete(
        f"Task: {task}\nCandidate answer: {draft}\n"
        f"Find errors and inaccuracies. If correct, reply OK."
    )
    if critique.strip().startswith("OK"):
        return draft
    return llm.complete(
        f"Task: {task}\nDraft: {draft}\nIssues: {critique}\n"
        f"Produce a corrected final version."
    )
```

### 4. Confidence-based gating (use on high-stakes nodes)

Ask the model to self-report confidence. Route low-confidence responses to a stronger model or human. Default threshold: 0.75.

```python
def answer_with_gating(question: str, threshold: float = 0.75) -> str:
    response = llm.complete(
        f"Answer and rate confidence 0-1 as JSON {{'answer':...,'confidence':...}}:\n{question}"
    )
    data = json.loads(response)
    if data["confidence"] < threshold:
        return escalate_to_strong_model(question)
    return data["answer"]
```

Place gating at: tool calls with side effects, final user-facing answers, pipeline branching decisions.

---

## Minimum Required Guardrails per Use Case

| Scenario | Required guardrails |
|---|---|
| Any structured output (JSON, typed data) | Schema validation + retry (mandatory) |
| Agentic pipeline step with side effects | Schema validation + retry + confidence gating |
| Critical semantic correctness needed | Schema validation + retry + self-correction |
| Simple one-off text generation | Retry only (lenient, 2–3 attempts) |
| Embeddings (`qwen3-embedding-8b`) | None — deterministic output, no guardrails needed |
| Image description (`Qwen2.5-VL-7B`) | Retry + schema validation if structured output expected |

**Absolute minimum for any agentic pipeline:** schema validation + retry on every LLM call with structured output, plus gating on steps with side effects.

---

## Key Constraints

- `qwen3-embedding-8b` supports **only** `/v1/embeddings` — never send it to `/v1/chat/completions`
- `Qwen2.5-VL-7B` is the **only** model with vision/image capability
- These are mid-tier models — do not assume flagship-level reliability; always wrap with guardrails
- Hallucinations are expected; design pipelines to handle them gracefully, not to avoid them
