import asyncio

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
        cmd = build_command(client, "Hello", role="default", model=None, file_paths=None)
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "--json" in cmd
        assert "--model" in cmd
        assert "o3" in cmd
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
        cmd = build_command(client, "Hi", role="default", model="gemini-2.5-flash", file_paths=None)
        assert "gemini-2.5-flash" in cmd
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
        cmd = build_command(
            client, "Review this",
            role="default", model=None,
            file_paths=["/tmp/a.py", "/tmp/b.py"],
        )
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
        cmd = build_command(
            client,
            "Review this file",
            role="default",
            model=None,
            file_paths=["/tmp/demo.py"],
            context_mode="paths",
        )
        assert cmd[-2] == "-p"
        assert "Context manifest:" in cmd[-1]

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
        cmd = build_command(client, "Review", role="codereviewer", model=None, file_paths=None)
        assert "--tools" in cmd
        assert "Bash,Read" in cmd
        assert cmd[-2] == "-p"


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
        result = _build_prompt("my question", role_config, None)
        assert "[Warning:" in result
        assert "nonexistent.txt" in result
        assert "my question" in result


class TestRunCli:
    def test_missing_executable(self):
        result = asyncio.run(run_cli("test", ["nonexistent_binary_xyz", "hello"]))
        assert "[Error]" in result
        assert "not found" in result

    def test_successful_execution(self):
        result = asyncio.run(run_cli("unknown", ["echo", "hello world"]))
        assert "hello world" in result


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
        ):
            captured["context_mode"] = context_mode
            captured["max_file_bytes"] = max_file_bytes
            captured["max_total_bytes"] = max_total_bytes
            return ["echo", "ok"]

        async def fake_run_cli(cli_name, command, timeout=300):
            return "ok"

        monkeypatch.setattr("clink_mcp.server.build_command", fake_build_command)
        monkeypatch.setattr("clink_mcp.server.run_cli", fake_run_cli)

        asyncio.run(clink("Inspect this", "codex"))

        assert captured["context_mode"] == "auto"
        assert captured["max_file_bytes"] > 0
        assert captured["max_total_bytes"] > 0
