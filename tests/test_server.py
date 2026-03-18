import json
import shlex
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from clink_mcp.server import build_command, merge_args, _build_prompt


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

    def test_model_override(self):
        client = {
            "command": "gemini",
            "args": ["-p", "--output-format", "json"],
            "models": {"default": "gemini-2.5-pro"},
            "roles": {"default": {"prompt_file": "prompts/consult.txt"}},
        }
        cmd = build_command(client, "Hi", role="default", model="gemini-2.5-flash", file_paths=None)
        assert "gemini-2.5-flash" in cmd
        # Default model should NOT be present
        assert "gemini-2.5-pro" not in cmd

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

    def test_role_args_merged(self):
        client = {
            "command": "claude",
            "args": ["-p"],
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


class TestBuildPrompt:
    def test_includes_system_prompt(self):
        role_config = {"prompt_file": "prompts/consult.txt"}
        result = _build_prompt("my question", role_config, None)
        assert "SUMMARY" in result
        assert "my question" in result

    def test_includes_file_paths(self):
        role_config = {}
        result = _build_prompt("review", role_config, ["/a.py", "/b.py"])
        assert "/a.py" in result
        assert "/b.py" in result

    def test_no_system_prompt_no_files(self):
        result = _build_prompt("just a question", {}, None)
        assert result == "just a question"
