import os
from pathlib import Path

import pytest
import yaml
import clink_mcp.config as config_module

from clink_mcp.config import (
    load_config,
    resolve_config_path,
    resolve_prompt,
    resolve_transport_dir,
)


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data))


class _FakeTraversable:
    def __init__(self, mapping: dict[str, str], path: str = ""):
        self.mapping = mapping
        self.path = path

    def __truediv__(self, name: str):
        next_path = f"{self.path}/{name}" if self.path else name
        return _FakeTraversable(self.mapping, next_path)

    def exists(self):
        return self.path in self.mapping

    def is_file(self):
        return self.exists()

    def read_text(self):
        return self.mapping[self.path]

    def __str__(self):
        return f"virtual://{self.path}"


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

    def test_resolves_bundled_clients_via_importlib_resources(self, monkeypatch, tmp_path):
        package_root = tmp_path / "package"
        package_root.mkdir()
        bundled = package_root / "clients.yaml"
        bundled.write_text("clients:\n  demo:\n    command: echo\n")

        monkeypatch.delenv("CLIENTS_CONFIG", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setattr(config_module, "_project_root", lambda: tmp_path / "missing-project")
        monkeypatch.setattr(config_module, "_package_dir", lambda: tmp_path / "missing-package")
        monkeypatch.setattr(
            "importlib.resources.files",
            lambda package: package_root,
        )

        assert resolve_config_path() == bundled

    def test_loads_bundled_clients_from_non_path_traversable(self, monkeypatch, tmp_path):
        fake_root = _FakeTraversable(
            {
                "clients.yaml": yaml.dump(
                    {
                        "clients": {
                            "demo": {
                                "command": "echo",
                                "models": {"default": "x"},
                                "roles": {"default": {}},
                            }
                        }
                    }
                )
            }
        )

        monkeypatch.delenv("CLIENTS_CONFIG", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setattr(config_module, "_project_root", lambda: tmp_path / "missing-project")
        monkeypatch.setattr(config_module, "_package_dir", lambda: tmp_path / "missing-package")
        monkeypatch.setattr("importlib.resources.files", lambda package: fake_root)

        config = load_config(resolve_config_path())
        assert config["demo"]["command"] == "echo"


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

    def test_bundled_clients_expose_testgen_role(self):
        config = load_config(resolve_config_path())

        for client_name in ["codex", "gemini", "claude"]:
            client = config[client_name]
            assert "testgen" in client["roles"]
            prompt_file = client["roles"]["testgen"]["prompt_file"]
            assert prompt_file == "prompts/testgen.txt"
            prompt_text = resolve_prompt(prompt_file)
            prompt_lower = prompt_text.lower()
            assert "test-generation subagent" in prompt_lower
            assert "one fenced code block" in prompt_lower
            assert "<summary>" in prompt_lower
            assert "if context is insufficient, say exactly what is missing instead of guessing." in prompt_lower


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

    def test_resolves_bundled_prompt_via_importlib_resources(self, monkeypatch, tmp_path):
        package_root = tmp_path / "package"
        prompts_dir = package_root / "prompts"
        prompts_dir.mkdir(parents=True)
        bundled = prompts_dir / "consult.txt"
        bundled.write_text("Bundled prompt text")

        monkeypatch.setattr(config_module, "_project_root", lambda: tmp_path / "missing-project")
        monkeypatch.setattr(config_module, "_package_dir", lambda: tmp_path / "missing-package")
        monkeypatch.setattr(
            "importlib.resources.files",
            lambda package: package_root,
        )

        assert resolve_prompt("prompts/consult.txt") == "Bundled prompt text"

    def test_resolves_bundled_prompt_from_non_path_traversable(self, monkeypatch, tmp_path):
        fake_root = _FakeTraversable({"prompts/consult.txt": "Virtual bundled prompt"})

        monkeypatch.setattr(config_module, "_project_root", lambda: tmp_path / "missing-project")
        monkeypatch.setattr(config_module, "_package_dir", lambda: tmp_path / "missing-package")
        monkeypatch.setattr("importlib.resources.files", lambda package: fake_root)

        assert resolve_prompt("prompts/consult.txt") == "Virtual bundled prompt"


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
