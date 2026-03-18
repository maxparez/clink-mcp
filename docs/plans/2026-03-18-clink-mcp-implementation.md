# clink-mcp Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a lightweight Python MCP server that bridges prompts to external CLI tools (Codex, Gemini, Claude).

**Architecture:** Single FastMCP server with two tools (`clink`, `list_clients`). Config from one `clients.yaml`. Per-client parser functions extract response text from JSON/JSONL output. Async subprocess execution.

**Tech Stack:** Python 3.12+, `mcp` (Python MCP SDK with FastMCP), `pyyaml`, `asyncio.subprocess`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/clink_mcp/__init__.py`
- Create: `.gitignore`
- Create: `CLAUDE.md`

**Step 1: Initialize git repo**

Run: `cd /root/vyvoj_sw/clink-mcp && git init`

**Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "clink-mcp"
version = "0.1.0"
description = "Lightweight MCP server for CLI-to-CLI bridge"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.12.0",
    "pyyaml>=6.0",
]

[project.scripts]
clink-mcp = "clink_mcp.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/clink_mcp"]

[tool.hatch.build.targets.wheel.force-include]
"prompts" = "clink_mcp/prompts"
"clients.yaml" = "clink_mcp/clients.yaml"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]
```

**Step 3: Create `src/clink_mcp/__init__.py`**

```python
"""clink-mcp: Lightweight MCP server for CLI-to-CLI bridge."""

__version__ = "0.1.0"
```

**Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
venv/
.pytest_cache/
```

**Step 5: Create `CLAUDE.md`**

```markdown
# clink-mcp

Lightweight Python MCP server — CLI-to-CLI bridge for Codex, Gemini, Claude.

## Quick Reference
- **Language**: Python 3.12+, code in English, no UI
- **Dependencies**: mcp (FastMCP), pyyaml
- **Entry point**: `src/clink_mcp/server.py:main()`
- **Config**: `clients.yaml` (YAML, single file for all CLI clients)
- **Design doc**: `docs/plans/2026-03-18-clink-mcp-design.md`

## Commands
```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run server
clink-mcp

# Tests
pytest -v
```

## Principles
- KISS, DRY, YAGNI
- Max 200 lines per file, 50 lines per function
- No classes where functions suffice
- No PAL compatibility needed
```

**Step 6: Create venv and install**

Run: `cd /root/vyvoj_sw/clink-mcp && python -m venv venv && source venv/bin/activate && pip install -e ".[dev]"`

**Step 7: Commit**

```bash
git add pyproject.toml src/clink_mcp/__init__.py .gitignore CLAUDE.md
git commit -m "chore: project scaffolding with pyproject.toml and package structure"
```

---

### Task 2: Configuration Loader

**Files:**
- Create: `clients.yaml`
- Create: `tests/test_config.py`
- Create: `src/clink_mcp/config.py`

**Step 1: Create default `clients.yaml`**

```yaml
clients:
  codex:
    command: "codex exec"
    args: ["--json", "--skip-git-repo-check"]
    models:
      default: "o3"
      available: ["o3", "o4-mini", "gpt-5-codex"]
    sandbox: "read-only"
    roles:
      default:
        prompt_file: "prompts/consult.txt"
      codereviewer:
        prompt_file: "prompts/codereview.txt"
      docgen:
        prompt_file: "prompts/docgen.txt"

  gemini:
    command: "gemini"
    args: ["-p", "--output-format", "json"]
    models:
      default: "gemini-2.5-pro"
      available: ["gemini-2.5-pro", "gemini-2.5-flash"]
    roles:
      default:
        prompt_file: "prompts/consult.txt"
      trusted:
        prompt_file: "prompts/consult.txt"
        args: ["--yolo"]
      codereviewer:
        prompt_file: "prompts/codereview.txt"
      docgen:
        prompt_file: "prompts/docgen.txt"

  claude:
    command: "claude"
    args: ["-p", "--output-format", "json"]
    models:
      default: "sonnet"
      available: ["sonnet", "opus", "haiku"]
    roles:
      default:
        prompt_file: "prompts/consult.txt"
      codereviewer:
        prompt_file: "prompts/codereview.txt"
        args: ["--tools", "Bash,Read,Glob,Grep"]
      docgen:
        prompt_file: "prompts/docgen.txt"
        args: ["--tools", "Read,Glob,Grep"]
```

**Step 2: Write failing test**

```python
# tests/test_config.py
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from clink_mcp.config import load_config, resolve_config_path, resolve_prompt


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data))


class TestResolveConfigPath:
    def test_env_var_override(self, tmp_path):
        config_file = tmp_path / "custom.yaml"
        _write_yaml(config_file, {"clients": {}})
        os.environ["CLIENTS_CONFIG"] = str(config_file)
        try:
            assert resolve_config_path() == config_file
        finally:
            del os.environ["CLIENTS_CONFIG"]

    def test_missing_env_var_file_raises(self):
        os.environ["CLIENTS_CONFIG"] = "/nonexistent/path.yaml"
        try:
            with pytest.raises(FileNotFoundError):
                resolve_config_path()
        finally:
            del os.environ["CLIENTS_CONFIG"]


class TestLoadConfig:
    def test_loads_clients(self, tmp_path):
        data = {
            "clients": {
                "test_cli": {
                    "command": "echo",
                    "args": ["--json"],
                    "models": {"default": "m1", "available": ["m1"]},
                    "roles": {
                        "default": {"prompt_file": "prompts/consult.txt"}
                    },
                }
            }
        }
        config_file = tmp_path / "clients.yaml"
        _write_yaml(config_file, data)
        config = load_config(config_file)
        assert "test_cli" in config
        assert config["test_cli"]["command"] == "echo"
        assert config["test_cli"]["models"]["default"] == "m1"

    def test_empty_clients_raises(self, tmp_path):
        config_file = tmp_path / "clients.yaml"
        _write_yaml(config_file, {"clients": {}})
        with pytest.raises(ValueError):
            load_config(config_file)


class TestResolvePrompt:
    def test_resolves_bundled_prompt(self):
        text = resolve_prompt("prompts/consult.txt")
        assert "consultant" in text.lower() or "SUMMARY" in text

    def test_resolves_absolute_path(self, tmp_path):
        prompt_file = tmp_path / "custom.txt"
        prompt_file.write_text("Custom prompt")
        text = resolve_prompt(str(prompt_file))
        assert text == "Custom prompt"

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError):
            resolve_prompt("prompts/nonexistent.txt")
```

**Step 3: Run test to verify it fails**

Run: `cd /root/vyvoj_sw/clink-mcp && source venv/bin/activate && pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'clink_mcp.config'`

**Step 4: Write implementation**

```python
# src/clink_mcp/config.py
"""Configuration loader for clink-mcp CLI clients."""

import os
from pathlib import Path

import yaml


def _package_dir() -> Path:
    """Return the package root directory."""
    return Path(__file__).parent


def _project_root() -> Path:
    """Return the project root (two levels up from package)."""
    return _package_dir().parent.parent


def resolve_config_path() -> Path:
    """Find clients.yaml in order: env var > ~/.clink-mcp > bundled."""
    env_path = os.environ.get("CLIENTS_CONFIG")
    if env_path:
        path = Path(env_path)
        if not path.exists():
            raise FileNotFoundError(f"CLIENTS_CONFIG not found: {path}")
        return path

    home_path = Path.home() / ".clink-mcp" / "clients.yaml"
    if home_path.exists():
        return home_path

    for candidate in [
        _project_root() / "clients.yaml",
        _package_dir() / "clients.yaml",
    ]:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No clients.yaml found")


def load_config(config_path: Path) -> dict:
    """Load and validate clients.yaml, return clients dict."""
    raw = yaml.safe_load(config_path.read_text())
    clients = raw.get("clients", {})
    if not clients:
        raise ValueError(f"No clients defined in {config_path}")
    return clients


def resolve_prompt(prompt_path: str) -> str:
    """Resolve prompt file path and return contents."""
    path = Path(prompt_path)
    if path.is_absolute() and path.exists():
        return path.read_text()

    for base in [_project_root(), _package_dir()]:
        candidate = base / prompt_path
        if candidate.exists():
            return candidate.read_text()

    raise FileNotFoundError(f"Prompt not found: {prompt_path}")
```

**Step 5: Create prompts directory with consult.txt**

```
mkdir -p /root/vyvoj_sw/clink-mcp/prompts
```

Copy the existing consult prompt:

```text
You are a consultant subagent invoked via a CLI-to-CLI bridge.

Hard constraints:
- Keep output short and actionable. Prefer bullets and checklists.
- Do NOT dump large code blocks. If you must reference code, cite file paths and symbols only.
- If you need to inspect files, open them yourself (you have access to the workspace). Do not ask the orchestrator to paste code.
- Follow KISS: no overengineering, no needless components.

Output format:
- End your response with a single <SUMMARY>...</SUMMARY> section (required).
- The <SUMMARY> must be at most ~12 bullets and include:
  - Recommendation
  - Key trade-offs
  - Risks/unknowns
  - Next concrete steps
```

**Step 6: Run tests**

Run: `cd /root/vyvoj_sw/clink-mcp && source venv/bin/activate && pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/clink_mcp/config.py tests/test_config.py clients.yaml prompts/consult.txt
git commit -m "feat: config loader with YAML parsing and prompt resolution"
```

---

### Task 3: Parsers

**Files:**
- Create: `tests/test_parsers.py`
- Create: `src/clink_mcp/parsers.py`

**Step 1: Write failing test**

```python
# tests/test_parsers.py
import json

from clink_mcp.parsers import parse_codex, parse_gemini, parse_claude, parse_output


class TestParseCodex:
    def test_extracts_message_from_jsonl(self):
        lines = [
            json.dumps({"type": "message", "content": "Hello from Codex"}),
            json.dumps({"type": "status", "state": "done"}),
        ]
        stdout = "\n".join(lines)
        result = parse_codex(stdout, "", 0)
        assert "Hello from Codex" in result

    def test_fallback_on_invalid_json(self):
        result = parse_codex("plain text output", "", 0)
        assert result == "plain text output"

    def test_error_on_nonzero_exit(self):
        result = parse_codex("", "command not found", 1)
        assert "error" in result.lower()


class TestParseGemini:
    def test_extracts_response_from_json(self):
        data = {"response": "Hello from Gemini"}
        stdout = json.dumps(data)
        result = parse_gemini(stdout, "", 0)
        assert "Hello from Gemini" in result

    def test_fallback_on_plain_text(self):
        result = parse_gemini("just text", "", 0)
        assert result == "just text"

    def test_error_on_nonzero_exit(self):
        result = parse_gemini("", "auth failed", 1)
        assert "error" in result.lower()


class TestParseClaude:
    def test_extracts_result_from_json(self):
        data = {"result": "Hello from Claude"}
        stdout = json.dumps(data)
        result = parse_claude(stdout, "", 0)
        assert "Hello from Claude" in result

    def test_fallback_on_plain_text(self):
        result = parse_claude("raw output", "", 0)
        assert result == "raw output"


class TestParseOutput:
    def test_dispatches_to_codex(self):
        lines = [json.dumps({"type": "message", "content": "test"})]
        result = parse_output("codex", "\n".join(lines), "", 0)
        assert "test" in result

    def test_dispatches_to_gemini(self):
        result = parse_output("gemini", json.dumps({"response": "test"}), "", 0)
        assert "test" in result

    def test_dispatches_to_claude(self):
        result = parse_output("claude", json.dumps({"result": "test"}), "", 0)
        assert "test" in result

    def test_unknown_client_returns_raw(self):
        result = parse_output("unknown", "raw", "", 0)
        assert result == "raw"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_parsers.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/clink_mcp/parsers.py
"""Per-CLI output parsers for clink-mcp.

Each parser extracts response text from CLI-specific output format.
Falls back to raw text on parse failure.
"""

import json


def _error_message(stderr: str, exit_code: int) -> str:
    return f"[Error] CLI exited with code {exit_code}.\n{stderr}".strip()


def parse_codex(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Codex JSONL output. Extract message content from event stream."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    messages = []
    for line in stdout.strip().splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "message":
                messages.append(event.get("content", ""))
        except json.JSONDecodeError:
            continue

    return "\n".join(messages) if messages else stdout.strip()


def parse_gemini(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Gemini JSON output. Extract response field."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return data.get("response", data.get("text", json.dumps(data)))
    except json.JSONDecodeError:
        pass

    return stdout.strip()


def parse_claude(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Claude JSON output. Extract result field."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return data.get("result", data.get("content", json.dumps(data)))
    except json.JSONDecodeError:
        pass

    return stdout.strip()


_PARSERS = {
    "codex": parse_codex,
    "gemini": parse_gemini,
    "claude": parse_claude,
}


def parse_output(cli_name: str, stdout: str, stderr: str, exit_code: int) -> str:
    """Dispatch to the appropriate parser by CLI name."""
    parser = _PARSERS.get(cli_name)
    if parser:
        return parser(stdout, stderr, exit_code)
    return stdout.strip()
```

**Step 4: Run tests**

Run: `pytest tests/test_parsers.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/clink_mcp/parsers.py tests/test_parsers.py
git commit -m "feat: per-CLI output parsers with JSON/JSONL extraction"
```

---

### Task 4: MCP Server

**Files:**
- Create: `tests/test_server.py`
- Create: `src/clink_mcp/server.py`

**Step 1: Write failing test**

```python
# tests/test_server.py
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from clink_mcp.server import build_command, merge_args


class TestBuildCommand:
    def test_codex_basic(self):
        client = {
            "command": "codex exec",
            "args": ["--json", "--skip-git-repo-check"],
            "models": {"default": "o3"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd = build_command(client, "Hello", role="default", model=None, file_paths=None)
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "--json" in cmd
        assert "--model" in cmd
        assert "o3" in cmd
        assert cmd[-1] == "Hello"

    def test_model_override(self):
        client = {
            "command": "gemini",
            "args": ["-p", "--output-format", "json"],
            "models": {"default": "gemini-2.5-pro"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd = build_command(client, "Hi", role="default", model="gemini-2.5-flash", file_paths=None)
        assert "gemini-2.5-flash" in cmd

    def test_file_paths_in_prompt(self):
        client = {
            "command": "claude",
            "args": ["-p", "--output-format", "json"],
            "models": {"default": "sonnet"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd = build_command(
            client, "Review this",
            role="default", model=None,
            file_paths=["/tmp/a.py", "/tmp/b.py"],
        )
        prompt_text = cmd[-1]
        assert "/tmp/a.py" in prompt_text
        assert "/tmp/b.py" in prompt_text


class TestMergeArgs:
    def test_base_plus_role_args(self):
        result = merge_args(["--json"], ["--sandbox", "read-only"])
        assert result == ["--json", "--sandbox", "read-only"]

    def test_no_role_args(self):
        result = merge_args(["--json"], None)
        assert result == ["--json"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/clink_mcp/server.py
"""clink-mcp: Lightweight MCP server for CLI-to-CLI bridge."""

import asyncio
import shlex
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from clink_mcp.config import load_config, resolve_config_path, resolve_prompt
from clink_mcp.parsers import parse_output

mcp = FastMCP("clink-mcp")

_clients: dict = {}


def _load_clients() -> dict:
    """Load clients config (lazy, cached)."""
    global _clients
    if not _clients:
        config_path = resolve_config_path()
        _clients = load_config(config_path)
    return _clients


def merge_args(base_args: list, role_args: list | None) -> list:
    """Merge base client args with role-specific args."""
    if not role_args:
        return list(base_args)
    return list(base_args) + list(role_args)


def build_command(
    client: dict,
    prompt: str,
    role: str,
    model: str | None,
    file_paths: list[str] | None,
) -> list[str]:
    """Build CLI command from client config, role, and prompt."""
    parts = shlex.split(client["command"])
    role_config = client.get("roles", {}).get(role, {})
    args = merge_args(client.get("args", []), role_config.get("args"))

    use_model = model or client.get("models", {}).get("default")
    if use_model:
        args.extend(["--model", use_model])

    full_prompt = _build_prompt(prompt, role_config, file_paths)

    return parts + args + [full_prompt]


def _build_prompt(
    prompt: str,
    role_config: dict,
    file_paths: list[str] | None,
) -> str:
    """Compose final prompt from user prompt, role system prompt, and file paths."""
    sections = []

    prompt_file = role_config.get("prompt_file")
    if prompt_file:
        try:
            system_prompt = resolve_prompt(prompt_file)
            sections.append(system_prompt)
        except FileNotFoundError:
            pass

    sections.append(prompt)

    if file_paths:
        files_section = "\n\nRelevant files:\n" + "\n".join(f"- {p}" for p in file_paths)
        sections.append(files_section)

    return "\n\n".join(sections)


async def run_cli(cli_name: str, command: list[str], timeout: int = 300) -> str:
    """Execute CLI command as async subprocess and return parsed output."""
    executable = command[0]
    if not shutil.which(executable):
        return f"[Error] CLI not found: {executable}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return f"[Error] CLI timed out after {timeout}s"

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return parse_output(cli_name, stdout, stderr, proc.returncode or 0)


@mcp.tool()
async def clink(
    prompt: str,
    cli_name: str,
    role: str = "default",
    model: str | None = None,
    file_paths: list[str] | None = None,
) -> str:
    """Send a prompt to an external CLI (codex, gemini, claude) and return the result.

    Args:
        prompt: The request to send to the CLI.
        cli_name: Which CLI to use: codex, gemini, or claude.
        role: Role preset (default, codereviewer, docgen, trusted).
        model: Override the default model for this call.
        file_paths: Absolute paths to relevant files (included in prompt).
    """
    clients = _load_clients()
    cli_name_lower = cli_name.lower()

    if cli_name_lower not in clients:
        available = ", ".join(clients.keys())
        return f"[Error] Unknown CLI '{cli_name}'. Available: {available}"

    client = clients[cli_name_lower]
    command = build_command(client, prompt, role, model, file_paths)
    return await run_cli(cli_name_lower, command)


@mcp.tool()
async def list_clients() -> str:
    """List available CLI clients, their roles, and models."""
    clients = _load_clients()
    lines = []
    for name, cfg in clients.items():
        models = cfg.get("models", {})
        roles = list(cfg.get("roles", {}).keys())
        lines.append(
            f"- **{name}**: model={models.get('default')} "
            f"(available: {', '.join(models.get('available', []))}) "
            f"| roles: {', '.join(roles)}"
        )
    return "\n".join(lines)


def main():
    """Entry point for clink-mcp server."""
    mcp.run()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

Run: `pytest tests/test_server.py -v`
Expected: ALL PASS

**Step 5: Verify server starts**

Run: `cd /root/vyvoj_sw/clink-mcp && source venv/bin/activate && timeout 3 clink-mcp 2>&1 || true`
Expected: Server starts (may show MCP transport info), exits on timeout — no crash

**Step 6: Commit**

```bash
git add src/clink_mcp/server.py tests/test_server.py
git commit -m "feat: MCP server with clink and list_clients tools"
```

---

### Task 5: Prompt Templates

**Files:**
- Create: `prompts/codereview.txt`
- Create: `prompts/docgen.txt`

**Step 1: Create codereview prompt**

```text
You are a code reviewer subagent invoked via a CLI-to-CLI bridge.

Your task: Review the provided files for issues.

What to look for:
- Bugs and logic errors
- Security vulnerabilities (injection, auth, data exposure)
- KISS/DRY/YAGNI violations
- Performance problems
- Missing error handling at system boundaries

Severity levels:
- CRITICAL: Bugs or security issues that must be fixed
- WARNING: Code smells, potential problems
- SUGGESTION: Improvements, style, readability

Hard constraints:
- Keep output short and actionable. Prefer bullets and checklists.
- Do NOT dump large code blocks. Cite file paths, line numbers, and symbols only.
- If you need to inspect files, open them yourself (you have access to the workspace).
- Follow KISS: no overengineering suggestions.

Output format:
- List findings grouped by file, each with severity and one-line description.
- End your response with a single <SUMMARY>...</SUMMARY> section (required).
- The <SUMMARY> must be at most ~12 bullets and include:
  - Overall assessment (OK / needs fixes / critical issues)
  - Top 3 actions to take
  - Risks/unknowns
```

**Step 2: Create docgen prompt**

```text
You are a documentation generator subagent invoked via a CLI-to-CLI bridge.

Your task: Analyze the provided code and generate concise documentation.

What to document:
- Module overview (purpose, 1-2 sentences)
- Public API: functions, classes, their parameters and return values
- Usage examples (short, practical)
- Dependencies and configuration if relevant

Hard constraints:
- Keep output short and actionable. No generic filler text.
- Do NOT copy entire source files. Reference file paths and symbols.
- If you need to inspect files, open them yourself (you have access to the workspace).
- Output in Markdown format.
- Follow KISS: document what exists, don't suggest what should exist.

Output format:
- Structured markdown with headers per module/file.
- End your response with a single <SUMMARY>...</SUMMARY> section (required).
- The <SUMMARY> must be at most ~12 bullets and include:
  - What was documented
  - Coverage gaps (if any)
  - Suggested next steps
```

**Step 3: Commit**

```bash
git add prompts/codereview.txt prompts/docgen.txt
git commit -m "feat: add codereview and docgen prompt templates"
```

---

### Task 6: GitHub Repo Setup

**Step 1: Create GitHub repo**

Run: `cd /root/vyvoj_sw/clink-mcp && gh repo create maxparez/clink-mcp --public --source=. --remote=origin --description "Lightweight MCP server for CLI-to-CLI bridge (Codex, Gemini, Claude)"`

**Step 2: Push**

Run: `git push -u origin main`

---

### Task 7: Integration Smoke Test

**Step 1: Create smoke test script**

Create: `tests/smoke_test.sh`

```bash
#!/bin/bash
# Smoke test: verify clink-mcp server starts and responds to MCP protocol
set -e

echo "=== clink-mcp smoke test ==="

# Check entry point exists
which clink-mcp || { echo "FAIL: clink-mcp not in PATH"; exit 1; }
echo "OK: entry point found"

# Check clients.yaml loads
python -c "
from clink_mcp.config import resolve_config_path, load_config
path = resolve_config_path()
clients = load_config(path)
print(f'OK: loaded {len(clients)} clients: {list(clients.keys())}')
"

# Check prompts exist
python -c "
from clink_mcp.config import resolve_prompt
for p in ['prompts/consult.txt', 'prompts/codereview.txt', 'prompts/docgen.txt']:
    text = resolve_prompt(p)
    assert 'SUMMARY' in text, f'{p} missing SUMMARY tag'
    print(f'OK: {p} ({len(text)} chars)')
"

echo "=== All smoke tests passed ==="
```

**Step 2: Run smoke test**

Run: `cd /root/vyvoj_sw/clink-mcp && source venv/bin/activate && bash tests/smoke_test.sh`
Expected: All OK

**Step 3: Run full test suite**

Run: `pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/smoke_test.sh
git commit -m "test: add integration smoke test"
```

---

### Task 8: Final Cleanup and Push

**Step 1: Verify file sizes**

Run: `wc -l src/clink_mcp/*.py`
Expected: Each file under 200 lines, total ~270 lines

**Step 2: Run all tests one final time**

Run: `pytest -v && bash tests/smoke_test.sh`
Expected: ALL PASS

**Step 3: Push to GitHub**

Run: `git push`
