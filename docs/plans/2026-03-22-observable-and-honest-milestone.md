# Observable And Honest Milestone Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make clink-mcp more trustworthy in daily use by making parser fallbacks visible, resolving bundled assets robustly, and adding basic runtime observability.

**Architecture:** Keep the current small functional design. Add explicit fallback markers in parser output, use `importlib.resources` for packaged `clients.yaml` and prompt templates, and add lightweight module-level logging plus one small subprocess hardening fix.

**Tech Stack:** Python 3.12+, FastMCP, `importlib.resources`, `logging`, pytest

### Task 1: Failing Tests For Honest Parsing And Bundled Assets

**Files:**
- Modify: `tests/test_parsers.py`
- Modify: `tests/test_config.py`
- Test: `tests/test_parsers.py`
- Test: `tests/test_config.py`

**Step 1: Write failing parser tests**

Add tests that expect:
- Codex raw fallback to be visibly marked, not returned silently.
- Gemini raw fallback to be visibly marked.
- Claude raw fallback to be visibly marked.

**Step 2: Write failing bundled-resource tests**

Add tests that monkeypatch the package resource resolver and assert:
- `resolve_config_path()` can return packaged `clients.yaml` without relying on repo-root path guessing.
- `resolve_prompt()` can return packaged prompt text without relying on repo-root path guessing.

**Step 3: Run failing tests**

Run: `pytest tests/test_parsers.py tests/test_config.py -v`

Expected: FAIL on missing fallback marker support and missing package-resource lookup support.

### Task 2: Minimal Implementation For Parser Honesty And Resource Loading

**Files:**
- Modify: `src/clink_mcp/parsers.py`
- Modify: `src/clink_mcp/config.py`
- Test: `tests/test_parsers.py`
- Test: `tests/test_config.py`

**Step 1: Implement parser fallback marker**

Add one shared helper in `src/clink_mcp/parsers.py` that returns a visible fallback prefix plus raw text when parsing fails for known clients.

**Step 2: Implement packaged resource lookup**

Use `importlib.resources.files("clink_mcp")` in `src/clink_mcp/config.py` for bundled `clients.yaml` and prompts, while preserving env-var and absolute-path overrides.

**Step 3: Run targeted tests**

Run: `pytest tests/test_parsers.py tests/test_config.py -v`

Expected: PASS

### Task 3: Logging And Runtime Hardening

**Files:**
- Modify: `src/clink_mcp/config.py`
- Modify: `src/clink_mcp/server.py`
- Modify: `src/clink_mcp/transport.py`
- Modify: `src/clink_mcp/parsers.py`
- Modify: `tests/test_server.py`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Add lightweight module logging**

Add `logging.getLogger(__name__)` and debug/warning logs for:
- config resolution decisions
- prompt transport file creation
- CLI invocation timing and timeout
- parser fallback usage

**Step 2: Harden timeout cleanup**

In `run_cli()`, after `proc.kill()` on timeout, wait for the process before returning.

**Step 3: Add or update focused tests**

Add one server-side regression test that proves timeout cleanup path still returns the expected error.

**Step 4: Run targeted tests**

Run: `pytest tests/test_server.py tests/test_transport.py tests/test_parsers.py tests/test_config.py -v`

Expected: PASS

### Task 4: Full Verification And Integration

**Files:**
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Update docs**

Document:
- fallback marker behavior
- packaged resource lookup via `importlib.resources`
- logging/observability boundaries

**Step 2: Run full verification**

Run: `pytest -v`
Run: `bash tests/smoke_test.sh`

Expected: all tests pass and smoke checks pass for Codex, Gemini, and Claude.

**Step 3: Commit and push**

Commit with a focused message and push `main` to `origin`.
