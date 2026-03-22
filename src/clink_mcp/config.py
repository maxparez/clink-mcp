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


def resolve_transport_dir() -> Path | None:
    """Resolve optional temp directory for prompt transport files."""
    env_path = os.environ.get("CLINK_TRANSPORT_DIR")
    if not env_path:
        return None

    path = Path(env_path)
    if not path.exists():
        raise FileNotFoundError(f"CLINK_TRANSPORT_DIR not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"CLINK_TRANSPORT_DIR is not a directory: {path}")
    return path


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
