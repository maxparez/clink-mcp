# Context Bundle Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `clink-mcp` consultations over local code more reliable by turning `file_paths` into an explicit, testable context bundle with optional embedded file contents and deterministic limits.

**Architecture:** Keep the downstream contract simple: `clink-mcp` still sends one assembled prompt string to the selected CLI, but that string will contain a structured context envelope instead of a loose `Relevant files:` list. Add a small context-building helper module so `server.py` stays explicit and short, and keep prompt transport unchanged in this first increment because stdin or temp-file support is not yet verified per downstream CLI.

**Tech Stack:** Python 3.12+, FastMCP, pytest

### Task 1: Add failing tests for context bundle assembly

**Files:**
- Create: `tests/test_context.py`
- Modify: `tests/test_server.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from clink_mcp.context import build_context_section


def test_embed_mode_includes_file_contents_with_line_numbers(tmp_path: Path):
    source = tmp_path / "demo.py"
    source.write_text("def add(a, b):\n    return a + b\n")

    result = build_context_section(
        file_paths=[str(source)],
        context_mode="embed",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "Context files" in result
    assert "demo.py" in result
    assert "1 | def add(a, b):" in result
```

```python
def test_paths_mode_does_not_embed_contents(tmp_path: Path):
    source = tmp_path / "demo.py"
    source.write_text("print('x')\n")

    result = build_context_section(
        file_paths=[str(source)],
        context_mode="paths",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "demo.py" in result
    assert "print('x')" not in result
    assert "contents not included" in result.lower()
```

```python
def test_embed_mode_marks_truncation(tmp_path: Path):
    source = tmp_path / "big.py"
    source.write_text("x = 1\n" * 1000)

    result = build_context_section(
        file_paths=[str(source)],
        context_mode="embed",
        max_file_bytes=40,
        max_total_bytes=80,
    )

    assert "truncated" in result.lower()
```

```python
def test_embed_mode_reports_missing_file():
    result = build_context_section(
        file_paths=["/tmp/does-not-exist.py"],
        context_mode="embed",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "does-not-exist.py" in result
    assert "missing" in result.lower()
```

```python
def test_build_command_uses_context_bundle_text():
    client = {
        "command": "claude",
        "args": ["--output-format", "json"],
        "prompt_flag": "-p",
        "models": {"default": "sonnet"},
        "roles": {"default": {}},
    }

    cmd = build_command(
        client,
        "Review this file",
        role="default",
        model=None,
        file_paths=["/tmp/demo.py"],
        context_mode="paths",
    )

    assert cmd[-2] == "-p"
    assert "Context manifest" in cmd[-1]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_context.py tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'clink_mcp.context'` and signature mismatch for `build_command(...)`.

**Step 3: Write minimal implementation**

Create `src/clink_mcp/context.py` with:

```python
from pathlib import Path


def build_context_section(
    file_paths: list[str] | None,
    context_mode: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> str:
    if not file_paths:
        return ""

    lines = ["Context manifest:"]
    rendered_files = []
    total_bytes = 0

    for raw_path in file_paths:
        path = Path(raw_path)
        if not path.exists():
            lines.append(f"- {raw_path} [missing]")
            continue

        if context_mode == "paths":
            lines.append(f"- {raw_path} [contents not included]")
            continue

        text = path.read_text(errors="replace")
        encoded = text.encode("utf-8")
        truncated = False
        if len(encoded) > max_file_bytes:
            text = encoded[:max_file_bytes].decode("utf-8", errors="ignore")
            truncated = True

        remaining = max_total_bytes - total_bytes
        if remaining <= 0:
            lines.append(f"- {raw_path} [skipped: total context limit reached]")
            continue

        clipped = text.encode("utf-8")[:remaining].decode("utf-8", errors="ignore")
        total_bytes += len(clipped.encode("utf-8"))
        numbered = "\n".join(
            f"{idx} | {line}" for idx, line in enumerate(clipped.splitlines(), start=1)
        )
        status = "truncated" if truncated or clipped != text else "embedded"
        lines.append(f"- {raw_path} [{status}]")
        rendered_files.append(f"File: {raw_path}\n{numbered}")

    if rendered_files:
        lines.append("")
        lines.append("Context files:")
        lines.extend(rendered_files)

    return "\n".join(lines)
```

Update `tests/test_server.py` imports and expected text so the prompt assertions look for `Context manifest:` instead of the old `Relevant files:` block when `context_mode="paths"`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_context.py tests/test_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_context.py tests/test_server.py src/clink_mcp/context.py
git commit -m "test: cover context bundle assembly"
```

### Task 2: Wire context options into server prompt assembly

**Files:**
- Modify: `src/clink_mcp/server.py`
- Test: `tests/test_server.py`

**Step 1: Write the failing test**

```python
def test_build_prompt_appends_context_bundle(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text("answer = 42\n")

    result = _build_prompt(
        "Explain this module",
        {},
        [str(source)],
        context_mode="embed",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "Explain this module" in result
    assert "Context manifest:" in result
    assert "answer = 42" in result
```

```python
def test_clink_defaults_context_mode_to_auto(monkeypatch):
    captured = {}

    def fake_build_command(client, prompt, role, model, file_paths, context_mode, max_file_bytes, max_total_bytes):
        captured["context_mode"] = context_mode
        return ["echo", "ok"]

    monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -v`
Expected: FAIL because `_build_prompt()` and `build_command()` do not accept the new context parameters yet.

**Step 3: Write minimal implementation**

Update `src/clink_mcp/server.py`:

```python
from clink_mcp.context import build_context_section
```

Extend signatures:

```python
def build_command(..., file_paths: list[str] | None, context_mode: str = "auto", max_file_bytes: int = 12000, max_total_bytes: int = 48000) -> list[str]:
```

```python
def _build_prompt(..., file_paths: list[str] | None, context_mode: str = "auto", max_file_bytes: int = 12000, max_total_bytes: int = 48000) -> str:
```

Implementation rule:
- `auto` means embed file contents for readable text files until limits are reached.
- `paths` means include only the manifest.
- `embed` means try to embed contents and mark truncation or skips explicitly.

Append the result of `build_context_section(...)` only when it returns non-empty text.

Extend the MCP tool signature:

```python
async def clink(
    prompt: str,
    cli_name: str,
    role: str = "default",
    model: str | None = None,
    file_paths: list[str] | None = None,
    context_mode: str = "auto",
    max_file_bytes: int = 12000,
    max_total_bytes: int = 48000,
) -> str:
```

Docstring requirements:
- Document the three `context_mode` values.
- Document that `file_paths` can now include file contents in the assembled prompt.
- Document deterministic truncation via byte limits.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_server.py tests/test_context.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/server.py tests/test_server.py src/clink_mcp/context.py tests/test_context.py
git commit -m "feat: add structured file context bundle"
```

### Task 3: Preserve compatibility and keep failure modes explicit

**Files:**
- Modify: `src/clink_mcp/context.py`
- Modify: `src/clink_mcp/server.py`
- Test: `tests/test_context.py`

**Step 1: Write the failing test**

```python
def test_auto_mode_skips_unreadable_entries_and_reports_reason(tmp_path):
    source = tmp_path / "binary.bin"
    source.write_bytes(b"\x00\x01\x02\x03")

    result = build_context_section(
        file_paths=[str(source)],
        context_mode="auto",
        max_file_bytes=200,
        max_total_bytes=500,
    )

    assert "binary.bin" in result
    assert "skipped" in result.lower()
```

```python
def test_invalid_context_mode_raises_value_error():
    with pytest.raises(ValueError):
        build_context_section(
            file_paths=["/tmp/x.py"],
            context_mode="bogus",
            max_file_bytes=200,
            max_total_bytes=500,
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_context.py -v`
Expected: FAIL because binary detection and mode validation are not implemented yet.

**Step 3: Write minimal implementation**

In `src/clink_mcp/context.py`:
- Validate `context_mode` against `{"auto", "paths", "embed"}`.
- Add a tiny text-read helper that catches `UnicodeDecodeError` and reports `[skipped: unreadable or binary]`.
- Keep manifest lines deterministic so tests can assert exact phrases.

In `src/clink_mcp/server.py`:
- Let invalid `context_mode` bubble as a normal tool error message rather than silently falling back.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_context.py tests/test_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/context.py src/clink_mcp/server.py tests/test_context.py tests/test_server.py
git commit -m "feat: validate and report context bundle limits"
```

### Task 4: Document semantics and verify one real end-to-end call

**Files:**
- Modify: `docs/2026-03-22-testing-and-context-notes.md`
- Modify: `clients.yaml` only if a new default is intentionally chosen
- Test: `tests/smoke_test.sh`

**Step 1: Write the failing test**

There is no unit test for documentation, so make the runtime verification the failing step:

Run:

```bash
pytest tests/test_context.py tests/test_server.py tests/test_parsers.py tests/test_config.py -v
```

Then run one real end-to-end call against a locally available client:

```bash
python - <<'PY'
import asyncio
from clink_mcp.server import clink

async def main():
    result = await clink(
        prompt="Summarize the exact behavior of the attached file.",
        cli_name="codex",
        file_paths=["/home/pavel/vyvoj_sw/clink-mcp/src/clink_mcp/server.py"],
        context_mode="embed",
        max_file_bytes=4000,
        max_total_bytes=4000,
    )
    print(result)

asyncio.run(main())
PY
```

Expected before docs update: tests pass, but documentation still describes path-only behavior.

**Step 2: Update docs**

In `docs/2026-03-22-testing-and-context-notes.md`:
- Replace the old path-only description with the new `context_mode` semantics.
- Record the exact limits used in the manual verification.
- State clearly that prompt transport is still inline in this increment, so argv exposure remains an open follow-up concern.

Only update `clients.yaml` in this task if you intentionally choose a new runtime default such as `context_mode="auto"` at the tool layer and want that behavior mirrored in docs. Do not add transport-specific config yet.

**Step 3: Re-run verification**

Run:

```bash
pytest -v
```

And repeat the same end-to-end call once more.

Expected: PASS in pytest and a downstream answer that cites code behavior from the embedded file content rather than generic assumptions.

**Step 4: Commit**

```bash
git add docs/2026-03-22-testing-and-context-notes.md tests test* src/clink_mcp
git commit -m "docs: describe structured context bundle behavior"
```
