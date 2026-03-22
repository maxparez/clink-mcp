"""Configuration loader for clink-mcp CLI clients."""

from importlib import resources
from importlib.resources.abc import Traversable
import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _package_dir() -> Path:
    """Return the package root directory."""
    return Path(__file__).parent


def _project_root() -> Path:
    """Return the project root (two levels up from package)."""
    return _package_dir().parent.parent


def _bundled_resource(relative_path: str) -> Traversable | None:
    """Resolve bundled package data via importlib.resources when available."""
    candidate = resources.files("clink_mcp") / relative_path
    if candidate.is_file():
        logger.debug("Resolved bundled resource via importlib.resources: %s", candidate)
        return candidate
    return None


def resolve_config_path() -> Path | Traversable:
    """Find clients.yaml in order: env var > ~/.clink-mcp > bundled."""
    env_path = os.environ.get("CLIENTS_CONFIG")
    if env_path:
        path = Path(env_path)
        if not path.exists():
            raise FileNotFoundError(f"CLIENTS_CONFIG not found: {path}")
        logger.debug("Resolved clients config from CLIENTS_CONFIG: %s", path)
        return path

    home_path = Path.home() / ".clink-mcp" / "clients.yaml"
    if home_path.exists():
        logger.debug("Resolved clients config from home directory: %s", home_path)
        return home_path

    for candidate in [
        _project_root() / "clients.yaml",
        _package_dir() / "clients.yaml",
        _bundled_resource("clients.yaml"),
    ]:
        if candidate is None:
            continue
        if candidate.exists():
            logger.debug("Resolved clients config from bundled path: %s", candidate)
            return candidate

    raise FileNotFoundError("No clients.yaml found")


def load_config(config_path: Path | Traversable) -> dict:
    """Load and validate clients.yaml, return clients dict."""
    raw = yaml.safe_load(config_path.read_text())
    clients = raw.get("clients", {})
    if not clients:
        raise ValueError(f"No clients defined in {config_path}")
    logger.debug("Loaded %d clients from %s", len(clients), config_path)
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
    logger.debug("Resolved transport directory from env: %s", path)
    return path


def resolve_prompt(prompt_path: str) -> str:
    """Resolve prompt file path and return contents."""
    path = Path(prompt_path)
    if path.is_absolute() and path.exists():
        logger.debug("Resolved prompt from absolute path: %s", path)
        return path.read_text()

    for base in [_project_root(), _package_dir()]:
        candidate = base / prompt_path
        if candidate.exists():
            logger.debug("Resolved prompt from filesystem path: %s", candidate)
            return candidate.read_text()

    bundled = _bundled_resource(prompt_path)
    if bundled is not None:
        logger.debug("Resolved prompt from bundled resource: %s", bundled)
        return bundled.read_text()

    raise FileNotFoundError(f"Prompt not found: {prompt_path}")
