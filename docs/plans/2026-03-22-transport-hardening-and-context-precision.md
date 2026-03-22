# Transport Hardening And Context Precision Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden `clink-mcp` after the markdown-file transport rollout by tightening API safety, reducing silent failure modes, and improving the precision of local-code context passed to downstream CLIs.

**Architecture:** Keep the current small orchestration shape in `server.py`, but move policy checks out of implicit behavior and into explicit validation. The next iteration should not redesign prompt transport again; it should harden the current file-backed transport, make role/prompt failures fail fast, and add a more precise context-selection layer on top of the existing context bundle.

**Tech Stack:** Python 3.12+, FastMCP, pytest

### Task 1: Fail fast on invalid roles and missing prompt files

**Files:**
- Modify: `src/clink_mcp/server.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing test**

```python
def test_clink_rejects_unknown_role():
    result = asyncio.run(clink("Review this", "codex", role="does-not-exist"))
    assert "[Error]" in result
    assert "Unknown role" in result
```

```python
def test_build_prompt_raises_for_missing_prompt_file():
    with pytest.raises(FileNotFoundError):
        _build_prompt("question", {"prompt_file": "prompts/missing.txt"}, None)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL because unknown roles currently fall back to `{}` and missing prompt files currently become inline warning text.

**Step 3: Write minimal implementation**

In `src/clink_mcp/server.py`:
- Add a tiny helper that validates `role` against `client["roles"]`.
- Return a tool error string from `clink()` when the role is unknown.
- Stop converting missing `prompt_file` into prompt content; let the exception surface as an error result instead.

Keep implementation local and explicit. Do not introduce classes or a generic validation layer in this task.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/server.py tests/test_server.py
git commit -m "fix: fail fast on invalid role and prompt config"
```

### Task 2: Restrict and validate markdown output paths

**Files:**
- Modify: `src/clink_mcp/transport.py`
- Modify: `src/clink_mcp/server.py`
- Modify: `tests/test_transport.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing test**

```python
def test_output_file_must_use_markdown_extension(tmp_path):
    with pytest.raises(ValueError):
        write_markdown_output_file(str(tmp_path / "answer.txt"), "hello")
```

```python
def test_clink_rejects_non_markdown_output_file(monkeypatch, tmp_path):
    def fake_build_command(*args, **kwargs):
        return ["echo", "ok"], None

    async def fake_run_cli(*args, **kwargs):
        return "hello"

    monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
    monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

    result = asyncio.run(
        clink("Inspect this", "codex", output_file=str(tmp_path / "answer.txt"))
    )

    assert "[Error]" in result
    assert ".md" in result
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_transport.py tests/test_server.py -v`
Expected: FAIL because any output path is currently accepted.

**Step 3: Write minimal implementation**

In `src/clink_mcp/transport.py`:
- Require `output_file` to end with `.md`.
- Keep parent directory creation behavior.

In `src/clink_mcp/server.py`:
- Catch `ValueError` from output validation and return a tool error string instead of crashing.

Optional small enhancement if still reviewable:
- Reject empty output path strings.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_transport.py tests/test_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/transport.py src/clink_mcp/server.py tests/test_transport.py tests/test_server.py
git commit -m "fix: validate markdown output paths"
```

### Task 3: Add explicit prompt-temp-file policy

**Files:**
- Modify: `src/clink_mcp/transport.py`
- Modify: `src/clink_mcp/config.py`
- Modify: `tests/test_transport.py`
- Modify: `tests/test_config.py`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Write the failing test**

```python
def test_prompt_temp_file_uses_configured_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINK_TRANSPORT_DIR", str(tmp_path))
    path = write_markdown_prompt_file("hello")
    assert Path(path).parent == tmp_path
    Path(path).unlink()
```

```python
def test_transport_dir_must_exist_if_explicitly_configured(monkeypatch):
    monkeypatch.setenv("CLINK_TRANSPORT_DIR", "/tmp/does-not-exist-clink")
    with pytest.raises(FileNotFoundError):
        resolve_transport_dir()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_transport.py tests/test_config.py -v`
Expected: FAIL because transport temp dir is not configurable today.

**Step 3: Write minimal implementation**

In `src/clink_mcp/config.py`:
- Add `resolve_transport_dir()` that reads `CLINK_TRANSPORT_DIR`.
- If env var is absent, use the current tempfile default behavior.
- If env var is present, require the directory to exist.

In `src/clink_mcp/transport.py`:
- Pass the resolved directory into `NamedTemporaryFile(dir=...)`.

In docs:
- Record the new env var and its privacy/debugging trade-off.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_transport.py tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/config.py src/clink_mcp/transport.py tests/test_transport.py tests/test_config.py docs/2026-03-22-testing-and-context-notes.md
git commit -m "feat: add configurable prompt transport directory"
```

### Task 4: Improve context precision beyond whole-file embedding

**Files:**
- Modify: `src/clink_mcp/context.py`
- Modify: `src/clink_mcp/server.py`
- Modify: `tests/test_context.py`
- Modify: `tests/test_server.py`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Write the failing test**

```python
def test_context_section_supports_line_ranges(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("a\nb\nc\nd\n")

    result = build_context_section(
        file_paths=[f"{source}:2-3"],
        context_mode="embed",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "1 | b" in result
    assert "2 | c" in result
    assert "a" not in result
    assert "d" not in result
```

```python
def test_invalid_line_range_is_reported(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("a\nb\n")

    result = build_context_section(
        file_paths=[f"{source}:9-10"],
        context_mode="embed",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "skipped" in result.lower()
    assert "range" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_context.py tests/test_server.py -v`
Expected: FAIL because `file_paths` currently accept only plain paths.

**Step 3: Write minimal implementation**

In `src/clink_mcp/context.py`:
- Add support for `path:start-end` syntax.
- Parse the suffix only when it looks like a numeric range.
- Embed only the requested lines, renumbered from 1 inside the snippet.
- Report invalid or empty ranges explicitly in the manifest.

In `src/clink_mcp/server.py`:
- Document the extended `file_paths` syntax in the tool docstring.

In docs:
- Record that full-file embedding remains supported, but ranged embedding is now preferred for focused consultations.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_context.py tests/test_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/context.py src/clink_mcp/server.py tests/test_context.py tests/test_server.py docs/2026-03-22-testing-and-context-notes.md
git commit -m "feat: support ranged file context snippets"
```

### Task 5: Add explicit smoke verification for all three CLIs

**Files:**
- Modify: `tests/smoke_test.sh`
- Modify: `docs/2026-03-22-testing-and-context-notes.md`

**Step 1: Add failing smoke expectation**

Extend `tests/smoke_test.sh` so it verifies:
- `codex` with file-backed prompt transport
- `gemini` with file-backed prompt transport
- `claude` with file-backed prompt transport and `--no-session-persistence`
- optional `output_file` write for at least one client

Expected initial state before script update: no single smoke script exercises this exact transport matrix.

**Step 2: Implement minimal smoke script changes**

Make the script:
- use one small attached file from `src/clink_mcp/server.py`
- request one concrete function name in the answer
- fail if output is empty
- fail if the output file is missing when requested

Keep the smoke script small and readable; do not add a general-purpose harness.

**Step 3: Run verification**

Run:

```bash
.venv/bin/python -m pytest -v
bash tests/smoke_test.sh
```

Expected: both commands pass.

**Step 4: Commit**

```bash
git add tests/smoke_test.sh docs/2026-03-22-testing-and-context-notes.md
git commit -m "test: add transport smoke checks for all cli clients"
```
