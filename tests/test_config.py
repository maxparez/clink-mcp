import os
from pathlib import Path

import pytest
import yaml

from clink_mcp.config import (
    load_config,
    resolve_config_path,
    resolve_prompt,
    resolve_transport_dir,
)


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

    def test_bundled_claude_uses_stdin_markdown_without_session_persistence(self):
        config = load_config(resolve_config_path())
        claude = config["claude"]

        assert claude["prompt_transport"] == "stdin_markdown"
        assert claude["stdin_prompt_args"] == ["-p"]
        assert "--no-session-persistence" in claude["args"]


class TestResolvePrompt:
    def test_resolves_bundled_prompt(self):
        text = resolve_prompt("prompts/consult.txt")
        assert "SUMMARY" in text

    def test_resolves_absolute_path(self, tmp_path):
        prompt_file = tmp_path / "custom.txt"
        prompt_file.write_text("Custom prompt")
        text = resolve_prompt(str(prompt_file))
        assert text == "Custom prompt"

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError):
            resolve_prompt("prompts/nonexistent.txt")


class TestResolveTransportDir:
    def test_missing_explicit_transport_dir_raises(self, monkeypatch):
        monkeypatch.setenv("CLINK_TRANSPORT_DIR", "/tmp/does-not-exist-clink")
        with pytest.raises(FileNotFoundError):
            resolve_transport_dir()

    def test_non_directory_transport_dir_raises(self, monkeypatch, tmp_path):
        path = tmp_path / "file.md"
        path.write_text("x")
        monkeypatch.setenv("CLINK_TRANSPORT_DIR", str(path))
        with pytest.raises(NotADirectoryError):
            resolve_transport_dir()
