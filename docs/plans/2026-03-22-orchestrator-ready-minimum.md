# Orchestrator-Ready Minimum Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the smallest useful orchestrator-facing contract to `clink-mcp`: opt-in structured output and per-call CLI overrides.

**Architecture:** Keep `clink-mcp` as a single-call execution layer. Preserve existing text output by default, add `response_format="json"` as an opt-in envelope, and forward `extra_args` without introducing routing or scheduler logic.

**Tech Stack:** Python 3.12+, FastMCP, pytest

### Task 1: Add failing tests for the public contract

**Files:**
- Modify: `tests/test_server.py`
- Modify: `tests/test_parsers.py`

**Step 1: Write the failing test**

Add tests that require:
- `build_command(..., extra_args=[...])` to append the extra CLI args
- `clink(..., response_format="json")` to return a JSON string envelope
- the JSON envelope to expose stable keys only: `status`, `text`, `meta`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py tests/test_parsers.py -v`
Expected: FAIL because `extra_args` and `response_format` do not exist yet.

### Task 2: Implement the minimal runtime support

**Files:**
- Modify: `src/clink_mcp/server.py`
- Modify: `src/clink_mcp/context.py`
- Modify: `src/clink_mcp/parsers.py`

**Step 1: Write minimal implementation**

- Add `extra_args` pass-through in `build_command()` and `clink()`
- Add opt-in `response_format="json"` in `clink()`
- Return a simple execution envelope containing:
  - `status`
  - `text`
  - `meta` with `cli`, `model`, `role`, `duration_ms`, `exit_code`, `context_manifest`
- Keep default text behavior unchanged

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_server.py tests/test_parsers.py -v`
Expected: PASS

### Task 3: Verify and document the minimum contract

**Files:**
- Modify: `README.md`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Update docs**

Document:
- `response_format="json"` is opt-in
- `extra_args` is raw CLI pass-through
- `clink-mcp` remains a single-call execution layer, not an orchestrator

**Step 2: Full verification**

Run:
- `pytest -v`
- `bash tests/smoke_test.sh`
- `git diff --check`

Expected: all pass cleanly.
