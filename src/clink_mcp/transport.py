"""Helpers for file-backed prompt and response transport."""

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from clink_mcp.config import resolve_transport_dir

logger = logging.getLogger(__name__)


def validate_markdown_path(path: str) -> Path:
    """Validate that a persisted markdown artifact uses a .md suffix."""
    output_path = Path(path)
    if output_path.suffix.lower() != ".md":
        raise ValueError(f"output_file must use a .md extension: {path}")
    return output_path


def write_markdown_prompt_file(text: str) -> str:
    """Write prompt text into a temporary markdown file and return its path."""
    transport_dir = resolve_transport_dir()
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".md",
        prefix="clink-prompt-",
        delete=False,
        dir=transport_dir,
    ) as handle:
        handle.write(text)
        logger.debug(
            "Wrote markdown prompt file %s (%d chars)",
            handle.name,
            len(text),
        )
        return handle.name


def write_markdown_output_file(path: str, text: str) -> None:
    """Persist response text to a markdown file path."""
    output_path = validate_markdown_path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text)
    logger.debug("Wrote markdown output file %s (%d chars)", output_path, len(text))
