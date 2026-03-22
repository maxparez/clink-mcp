# Testgen Role Design And Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a first-class `testgen` workflow to `clink-mcp` for generating focused regression tests or repro scripts from local code context, without changing the core MCP API.

**Architecture:** Reuse the current `clink(prompt, cli_name, role, file_paths, context_mode, output_file)` contract. Add a new `testgen` role to `clients.yaml` and a new `prompts/testgen.txt` template that forces small, reviewable test outputs. Keep orchestration outside the server: `clink-mcp` should generate candidate test content, not write directly into `.py` source files or run the generated test automatically.

**Tech Stack:** Python 3.12+, FastMCP, YAML client config, markdown prompt transport, pytest-oriented prompt design

## Recommendation

Start with `testgen` as the next productized workflow.

Why:
- It fits the existing architecture with almost no server surface change.
- It produces an artifact that is easy to inspect, save, and iterate on.
- It keeps hallucination risk bounded because the task can be tightly scoped to attached code and failing behavior.
- It is more practical than consensus as a first milestone because it creates direct engineering output, not just another opinion.

Defer multi-model consensus to the orchestrator layer.

Why:
- It is useful, but it is orchestration-heavy and cost/latency-heavy.
- It should remain a composition pattern over multiple `clink()` calls, not a core server feature yet.

## Minimal Product Shape

### User-Facing API

No new MCP tool is needed in v1.

Use:

```python
await clink(
    prompt="Generate a minimal pytest regression test for this bug...",
    cli_name="codex",
    role="testgen",
    file_paths=[...],
    context_mode="embed",
    output_file="/tmp/testgen.md",
)
```

### Output Contract

The `testgen` role should produce one of these:
- a minimal `pytest` test file body
- a minimal standalone repro script
- a short refusal if the context is insufficient

The output must include:
- target file/module under test
- assumptions or missing context
- the proposed test content
- a `<SUMMARY>` section with:
  - recommendation
  - missing context
  - risks/unknowns
  - next concrete steps

The role should explicitly avoid:
- broad refactors
- multi-file fixture systems unless strictly needed
- invented helper APIs not visible in the attached context
- writing directly into repo files

## Prompt Contract

Create `prompts/testgen.txt`.

Recommended structure:

```text
You are a test-generation subagent invoked via a CLI-to-CLI bridge.

Your task: Generate the smallest useful regression test or repro artifact for the attached code and request.

What to optimize for:
- Correctness over coverage
- Minimal, runnable output
- Use only APIs and symbols visible in the attached context
- Prefer pytest unless the request clearly calls for another format

Hard constraints:
- Keep output short and actionable.
- Do NOT invent project helpers, fixtures, imports, or module paths not visible in context.
- If context is insufficient, say exactly what is missing instead of guessing.
- Prefer a single focused test over a broad test suite.
- Follow KISS: no fixture frameworks or abstractions unless strictly necessary.

Output format:
- Start with a short assessment.
- Then provide one fenced code block containing the proposed test or repro script.
- End with a single <SUMMARY>...</SUMMARY> section (required).
- The <SUMMARY> must include:
  - Recommendation
  - Assumptions / missing context
  - Risks/unknowns
  - Next concrete steps
```

## Context Contract

`testgen` should be used only when the caller can provide enough local grounding.

Recommended attached context:
- target source file or line range
- failing test or stack trace, if available
- directly adjacent helpers or parser/config files when the behavior crosses boundaries

Preferred pattern:
- `file_paths` should use line ranges when possible
- `context_mode="embed"` should be the default for serious use
- caller should keep the context narrow and bug-focused

Insufficient-context examples:
- “Write tests for this repo” with no file attachments
- a stack trace with no relevant code
- a diff with no surrounding implementation

## Safety Boundaries

Keep these boundaries explicit in v1:
- `clink-mcp` generates candidate test content only
- the orchestrator decides whether to save or apply it
- generated code should go to markdown output first, not directly to `.py`
- no automatic execution of generated tests inside `clink-mcp`

This preserves correctness and keeps the server small.

## Trade-Offs

### Option A: Role-only `testgen` (Recommended)

Implementation:
- add `prompts/testgen.txt`
- add `testgen` role entries in `clients.yaml`
- no new server tool

Pros:
- lowest risk
- fastest to ship
- fully aligned with current architecture

Cons:
- caller still has to know how to formulate the prompt well
- output remains free-form markdown, not structured JSON

### Option B: Dedicated `generate_test` MCP tool

Implementation:
- add a separate MCP tool with specialized args like `failure_text`, `target_files`, `test_style`

Pros:
- better ergonomics
- easier to document as a workflow

Cons:
- duplicates `clink()` surface
- more server complexity
- forces opinionated API decisions too early

### Option C: Auto-write test files directly into repo

Implementation:
- `output_file` points directly into `tests/...`

Pros:
- fastest path from suggestion to runnable artifact

Cons:
- high hallucination risk
- easy to create junk files or wrong imports
- too aggressive for v1

Recommendation:
- ship Option A first
- keep Option B for later only if role-based usage proves too awkward
- avoid Option C in the server

## Implementation Plan

### Task 1: Add Role Prompt

**Files:**
- Create: `prompts/testgen.txt`
- Test: `tests/test_config.py`

**Step 1: Write failing config test**

Add a test that expects each bundled client to expose a `testgen` role with a valid prompt file.

**Step 2: Run targeted test**

Run: `pytest tests/test_config.py -v`

Expected: FAIL because `testgen` does not exist yet.

**Step 3: Add prompt file**

Create `prompts/testgen.txt` with the contract above.

**Step 4: Add role entries**

Modify `clients.yaml`:
- `codex.roles.testgen.prompt_file = "prompts/testgen.txt"`
- `gemini.roles.testgen.prompt_file = "prompts/testgen.txt"`
- `claude.roles.testgen.prompt_file = "prompts/testgen.txt"`

Do not add special args in v1 unless testing proves one provider needs them.

**Step 5: Re-run targeted test**

Run: `pytest tests/test_config.py -v`

Expected: PASS

### Task 2: Verify Prompt Assembly

**Files:**
- Modify: `tests/test_server.py`
- Test: `tests/test_server.py`

**Step 1: Write failing test**

Add a test that builds a command with `role="testgen"` and asserts:
- the prompt includes the `testgen` system prompt
- the prompt still includes embedded context manifest/content

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py::TestBuildCommand -v`

Expected: FAIL before the role exists, PASS after Task 1.

**Step 3: Keep implementation minimal**

Do not modify `server.py` unless the test reveals a real role-resolution or prompt-assembly gap.

### Task 3: Smoke The Workflow

**Files:**
- Modify: `tests/smoke_test.sh`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Add a `testgen` smoke call**

Use one small Python source file and prompt:
- “Generate one minimal pytest test for this function.”

Assert:
- non-empty output
- one fenced code block exists
- `<SUMMARY>` exists

**Step 2: Run smoke test**

Run: `bash tests/smoke_test.sh`

Expected: PASS for at least one provider in the first iteration. If all three work reliably, keep all three in the matrix.

### Task 4: Document Recommended Usage

**Files:**
- Modify: `README.md`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Add one usage example**

Document a canonical call showing:
- `role="testgen"`
- `context_mode="embed"`
- narrow `file_paths`
- optional `output_file`

**Step 2: Document boundaries**

State explicitly:
- output is a candidate artifact
- human review is required
- direct repo writes are not the default workflow

### Task 5: Full Verification

**Files:**
- None beyond files above

**Step 1: Run focused tests**

Run:
- `pytest tests/test_config.py tests/test_server.py -v`

**Step 2: Run full suite**

Run:
- `pytest -v`

**Step 3: Run smoke verification**

Run:
- `bash tests/smoke_test.sh`

**Step 4: Commit**

Suggested commit message:

```bash
git commit -m "Add test generation role"
```

## Example Canonical Usage

```python
await clink(
    prompt=(
        "Generate one minimal pytest regression test for this parser bug. "
        "If context is missing, state exactly what is missing."
    ),
    cli_name="claude",
    role="testgen",
    model="opus",
    file_paths=[
        "/abs/path/src/module.py:40-95",
        "/abs/path/tests/test_module.py:1-80",
    ],
    context_mode="embed",
    max_file_bytes=8000,
    max_total_bytes=16000,
    output_file="/tmp/testgen.md",
)
```

## Follow-Up Milestone

After `testgen` proves useful, revisit multi-model consensus as a separate orchestration feature.

Keep that out of the core server at first:
- no `multi_clink` in v1
- no synthesis logic in `server.py`
- orchestration should live in the calling agent or skill layer
