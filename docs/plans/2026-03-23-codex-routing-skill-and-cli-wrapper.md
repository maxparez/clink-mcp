# Codex Routing Skill And CLI Wrapper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a thin direct CLI wrapper for `clink-mcp` and a local Codex skill that routes heavy tasks to the wrapper instead of the stock MCP path.

**Architecture:** Keep `clink-mcp` as the single source of truth for config, prompt assembly, context handling, transport, and parsing. Add one repo CLI entry point that accepts the same request shape as the MCP tool plus a terminal-only `timeout` override. Keep the routing decision in a local Codex skill outside the repo.

**Tech Stack:** Python 3.12+, FastMCP, argparse, pytest

### Task 1: Add failing tests for the direct wrapper contract

**Files:**
- Modify: `tests/test_server.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing test**

Add tests that require:
- a shared async execution helper callable outside the MCP tool
- `clink-cli` to accept a JSON payload matching the MCP request shape
- `clink-cli` to forward a terminal-only `timeout` override

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py tests/test_cli.py -v`
Expected: FAIL because the helper and CLI entry point do not exist yet.

### Task 2: Implement the repo wrapper with minimal shared logic

**Files:**
- Modify: `src/clink_mcp/server.py`
- Create: `src/clink_mcp/cli.py`
- Modify: `pyproject.toml`

**Step 1: Write minimal implementation**

- Extract the current `clink()` runtime body into a shared async helper
- Keep the MCP tool as a thin wrapper over that helper
- Add `clink-cli` that accepts `--tool-args-json` and optional `--timeout`
- Reuse the exact same config, context, transport, parsing, and response rendering paths

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_server.py tests/test_cli.py -v`
Expected: PASS

### Task 3: Document and verify the wrapper

**Files:**
- Modify: `README.md`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Update docs**

Document:
- `clink-cli` exists for direct terminal execution
- it accepts the same request shape as the MCP tool via JSON payload
- the terminal wrapper is the recommended escape hatch for tasks likely to exceed the stock Codex host timeout

**Step 2: Run real verification**

Run:
- `pip install -e .`
- `clink-cli --tool-args-json ...`

Expected: wrapper returns a real downstream response.

### Task 4: Create the local Codex routing skill

**Files:**
- Create: `~/.codex/skills/clink-routing/SKILL.md`

**Step 1: Write the skill**

The skill should:
- route short bounded tasks to MCP `clink`
- route heavy review / agentic / multi-file tasks to terminal `clink-cli`
- keep only routing heuristics in the skill
- never duplicate prompt or client logic

**Step 2: Verify the skill**

Check:
- the skill text is concise and searchable
- it references the direct wrapper path actually installed for Codex
- it gives one minimal routing rule set and one invocation example for each path

### Task 5: Finish integration

**Files:**
- Modify installed copy if needed: `/home/pavel/.codex/mcp/clink-mcp`

**Step 1: Final verification**

Run:
- `pytest -v`
- `git diff --check`
- one real `clink-cli` call from repo venv
- install/update the script in the Codex copy if `pyproject.toml` changed

**Step 2: Commit and push**

Commit the repo changes, push to `main`, and confirm local and remote SHA match.
