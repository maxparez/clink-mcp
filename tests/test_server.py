import asyncio
import json
from pathlib import Path

import pytest

from clink_mcp.server import (
    build_command,
    merge_args,
    _build_prompt,
    run_cli,
    clink,
    list_clients,
    _load_clients,
    _clients,
)


class TestMergeArgs:
    def test_base_plus_role_args(self):
        result = merge_args(["--json"], ["--sandbox", "read-only"])
        assert result == ["--json", "--sandbox", "read-only"]

    def test_no_role_args(self):
        result = merge_args(["--json"], None)
        assert result == ["--json"]

    def test_empty_lists(self):
        result = merge_args([], [])
        assert result == []


class TestBuildCommand:
    def test_codex_basic(self):
        client = {
            "command": "codex exec",
            "args": ["--json", "--skip-git-repo-check", "--sandbox", "read-only"],
            "models": {"default": "o3"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd, stdin_file = build_command(
            client, "Hello", role="default", model=None, file_paths=None
        )
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "--json" in cmd
        assert "--model" in cmd
        assert "o3" in cmd
        assert stdin_file is None
        # No prompt_flag, so prompt is last positional arg
        assert cmd[-1].endswith("Hello") or "Hello" in cmd[-1]

    def test_model_override(self):
        client = {
            "command": "gemini",
            "args": ["--output-format", "json"],
            "prompt_flag": "-p",
            "models": {"default": "gemini-2.5-pro"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd, stdin_file = build_command(
            client,
            "Hi",
            role="default",
            model="gemini-2.5-flash",
            file_paths=None,
        )
        assert "gemini-2.5-flash" in cmd
        assert stdin_file is None
        # Default model should NOT be present
        assert "gemini-2.5-pro" not in cmd
        # prompt_flag: -p should precede the prompt
        assert cmd[-2] == "-p"

    def test_file_paths_in_prompt(self):
        client = {
            "command": "claude",
            "args": ["--output-format", "json"],
            "prompt_flag": "-p",
            "models": {"default": "sonnet"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd, stdin_file = build_command(
            client, "Review this",
            role="default", model=None,
            file_paths=["/tmp/a.py", "/tmp/b.py"],
        )
        assert stdin_file is None
        # With prompt_flag, prompt is last, -p is second-to-last
        assert cmd[-2] == "-p"
        prompt_text = cmd[-1]
        assert "/tmp/a.py" in prompt_text
        assert "/tmp/b.py" in prompt_text

    def test_context_bundle_manifest_in_prompt(self):
        client = {
            "command": "claude",
            "args": ["--output-format", "json"],
            "prompt_flag": "-p",
            "models": {"default": "sonnet"},
            "roles": {"default": {}},
        }
        cmd, stdin_file = build_command(
            client,
            "Review this file",
            role="default",
            model=None,
            file_paths=["/tmp/demo.py"],
            context_mode="paths",
        )
        assert stdin_file is None
        assert cmd[-2] == "-p"
        assert "Context manifest:" in cmd[-1]

    def test_stdin_markdown_transport_uses_temp_md_file(self):
        client = {
            "command": "codex exec",
            "args": ["--json"],
            "prompt_transport": "stdin_markdown",
            "stdin_prompt_args": [],
            "models": {"default": "gpt-5.4"},
            "roles": {"default": {}},
        }
        cmd, stdin_file = build_command(
            client,
            "Inspect this module",
            role="default",
            model=None,
            file_paths=["/tmp/demo.py"],
            context_mode="paths",
        )
        assert cmd[:2] == ["codex", "exec"]
        assert stdin_file is not None
        path = Path(stdin_file)
        assert path.suffix == ".md"
        assert path.exists()
        text = path.read_text()
        assert "Inspect this module" in text
        assert "Context manifest:" in text

    def test_role_args_merged(self):
        client = {
            "command": "claude",
            "args": ["--output-format", "json"],
            "prompt_flag": "-p",
            "models": {"default": "sonnet"},
            "roles": {
                "codereviewer": {
                    "prompt_file": "prompts/codereview.txt",
                    "args": ["--tools", "Bash,Read"],
                }
            },
        }
        cmd, stdin_file = build_command(
            client, "Review", role="codereviewer", model=None, file_paths=None
        )
        assert "--tools" in cmd
        assert "Bash,Read" in cmd
        assert stdin_file is None
        assert cmd[-2] == "-p"

    def test_extra_args_are_appended_after_default_args(self):
        client = {
            "command": "codex exec",
            "args": ["--json", "-c", 'model_reasoning_effort="high"'],
            "models": {"default": "gpt-5.4"},
            "roles": {"default": {}},
        }
        cmd, stdin_file = build_command(
            client,
            "Inspect",
            role="default",
            model=None,
            file_paths=None,
            extra_args=["-c", 'model_reasoning_effort="xhigh"'],
        )
        assert stdin_file is None
        assert cmd[-3:] == ["-c", 'model_reasoning_effort="xhigh"', "Inspect"]

    def test_testgen_role_includes_prompt_and_embedded_context(self, tmp_path):
        source = tmp_path / "bug.py"
        source.write_text("def buggy():\n    return 1\n")
        client = {
            "command": "claude",
            "args": ["--output-format", "json", "--effort", "high"],
            "prompt_transport": "stdin_markdown",
            "stdin_prompt_args": ["-p"],
            "models": {"default": "opus"},
            "roles": {
                "testgen": {
                    "prompt_file": "prompts/testgen.txt",
                }
            },
        }
        cmd, stdin_file = build_command(
            client,
            "Generate a regression test for the bug.",
            role="testgen",
            model=None,
            file_paths=[str(source)],
            context_mode="embed",
            max_file_bytes=500,
            max_total_bytes=1000,
        )
        assert stdin_file is not None
        try:
            prompt_text = Path(stdin_file).read_text()
            assert "test-generation subagent" in prompt_text.lower()
            assert "Context manifest:" in prompt_text
            assert "def buggy():" in prompt_text
            assert "Generate a regression test for the bug." in prompt_text
        finally:
            Path(stdin_file).unlink(missing_ok=True)


class TestBuildPrompt:
    def test_includes_system_prompt(self):
        role_config = {"prompt_file": "prompts/consult.txt"}
        result = _build_prompt("my question", role_config, None)
        assert "SUMMARY" in result
        assert "my question" in result

    def test_includes_file_paths(self):
        role_config = {}
        result = _build_prompt(
            "review",
            role_config,
            ["/a.py", "/b.py"],
            context_mode="paths",
        )
        assert "/a.py" in result
        assert "/b.py" in result
        assert "Context manifest:" in result

    def test_appends_embedded_context_bundle(self, tmp_path):
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

    def test_no_system_prompt_no_files(self):
        result = _build_prompt("just a question", {}, None)
        assert result == "just a question"

    def test_missing_prompt_file_warning(self):
        role_config = {"prompt_file": "prompts/nonexistent.txt"}
        with pytest.raises(FileNotFoundError):
            _build_prompt("my question", role_config, None)


class TestRunCli:
    def test_missing_executable(self):
        result = asyncio.run(run_cli("test", ["nonexistent_binary_xyz", "hello"]))
        assert result["text"].startswith("[Error]")
        assert "not found" in result["text"]
        assert result["exit_code"] is None

    def test_successful_execution(self):
        result = asyncio.run(run_cli("unknown", ["echo", "hello world"]))
        assert result["text"] == "hello world"
        assert result["exit_code"] == 0

    def test_reads_stdin_from_temp_markdown_file(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("hello from markdown file")
        result = asyncio.run(run_cli("unknown", ["cat"], stdin_file=str(prompt_file)))
        assert result["text"] == "hello from markdown file"
        assert result["exit_code"] == 0

    def test_timeout_kills_and_waits_for_process(self, monkeypatch):
        state = {"killed": False, "waited": False}

        class FakeProc:
            returncode = None

            async def communicate(self, stdin_bytes):
                return b"", b""

            def kill(self):
                state["killed"] = True

            async def wait(self):
                state["waited"] = True

        async def fake_create_subprocess_exec(*args, **kwargs):
            return FakeProc()

        async def fake_wait_for(awaitable, timeout):
            raise asyncio.TimeoutError

        monkeypatch.setattr("clink_mcp.server.shutil.which", lambda executable: "/bin/fake")
        monkeypatch.setattr(
            "clink_mcp.server.asyncio.create_subprocess_exec",
            fake_create_subprocess_exec,
        )
        monkeypatch.setattr("clink_mcp.server.asyncio.wait_for", fake_wait_for)

        result = asyncio.run(run_cli("codex", ["fake-cli"], timeout=1))

        assert result["text"].startswith("[Error]")
        assert "timed out" in result["text"]
        assert state["killed"] is True
        assert state["waited"] is True


class TestListClients:
    def test_returns_all_clients(self):
        result = asyncio.run(list_clients())
        assert "codex" in result
        assert "gemini" in result
        assert "claude" in result


class TestClink:
    def test_defaults_context_mode_to_auto(self, monkeypatch):
        captured = {}

        def fake_build_command(
            client,
            prompt,
            role,
            model,
            file_paths,
            context_mode,
            max_file_bytes,
            max_total_bytes,
            extra_args,
        ):
            captured["context_mode"] = context_mode
            captured["max_file_bytes"] = max_file_bytes
            captured["max_total_bytes"] = max_total_bytes
            captured["extra_args"] = extra_args
            return ["echo", "ok"], None

        async def fake_run_cli(cli_name, command, timeout=300, stdin_file=None):
            return {"text": "ok", "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
        monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

        asyncio.run(clink("Inspect this", "codex"))

        assert captured["context_mode"] == "auto"
        assert captured["max_file_bytes"] > 0
        assert captured["max_total_bytes"] > 0
        assert captured["extra_args"] is None

    def test_response_format_json_returns_execution_envelope(self, monkeypatch, tmp_path):
        source = tmp_path / "demo.py"
        source.write_text("print('hi')\n")

        def fake_build_command(*args, **kwargs):
            return ["echo", "ok"], None

        async def fake_run_cli(cli_name, command, timeout=300, stdin_file=None):
            return {
                "text": "parsed result",
                "exit_code": 0,
                "duration_ms": 12,
            }

        monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
        monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

        result = asyncio.run(
            clink(
                "Inspect this",
                "codex",
                file_paths=[str(source)],
                response_format="json",
            )
        )

        data = json.loads(result)
        assert data["status"] == "success"
        assert data["text"] == "parsed result"
        assert data["meta"]["cli"] == "codex"
        assert data["meta"]["model"] == "gpt-5.4"
        assert data["meta"]["role"] == "default"
        assert data["meta"]["exit_code"] == 0
        assert data["meta"]["duration_ms"] == 12
        assert data["meta"]["context_manifest"][0]["status"] == "embedded"

    def test_rejects_unknown_role(self):
        result = asyncio.run(clink("Review this", "codex", role="does-not-exist"))
        assert "[Error]" in result
        assert "Unknown role" in result

    def test_rejects_invalid_context_mode(self):
        result = asyncio.run(
            clink("Inspect this", "codex", context_mode="bogus")
        )
        assert "[Error]" in result
        assert "Invalid context_mode" in result

    def test_writes_output_markdown_file(self, monkeypatch, tmp_path):
        output_file = tmp_path / "out" / "response.md"

        def fake_build_command(*args, **kwargs):
            return ["echo", "ok"], None

        async def fake_run_cli(cli_name, command, timeout=300, stdin_file=None):
            return {"text": "# Result\n\nHello", "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
        monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

        result = asyncio.run(
            clink("Inspect this", "codex", output_file=str(output_file))
        )

        assert result == "# Result\n\nHello"
        assert output_file.read_text() == "# Result\n\nHello"

    def test_rejects_non_markdown_output_file(self, monkeypatch, tmp_path):
        output_file = tmp_path / "out" / "response.txt"

        def fake_build_command(*args, **kwargs):
            return ["echo", "ok"], None

        async def fake_run_cli(cli_name, command, timeout=300, stdin_file=None):
            raise AssertionError("run_cli should not be called for invalid output_file")

        monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
        monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

        result = asyncio.run(
            clink("Inspect this", "codex", output_file=str(output_file))
        )

        assert "[Error]" in result
        assert ".md" in result

    def test_rejects_non_directory_transport_path(self, monkeypatch, tmp_path):
        transport_path = tmp_path / "transport.md"
        transport_path.write_text("not a directory")
        monkeypatch.setenv("CLINK_TRANSPORT_DIR", str(transport_path))

        result = asyncio.run(clink("Inspect this", "codex"))

        assert "[Error]" in result
        assert "not a directory" in result.lower()

    def test_cleans_up_temp_prompt_file(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("temporary prompt")

        def fake_build_command(*args, **kwargs):
            return ["echo", "ok"], str(prompt_file)

        async def fake_run_cli(cli_name, command, timeout=300, stdin_file=None):
            assert stdin_file == str(prompt_file)
            return {"text": "ok", "exit_code": 0, "duration_ms": 1}

        monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
        monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

        asyncio.run(clink("Inspect this", "codex"))

        assert not prompt_file.exists()
