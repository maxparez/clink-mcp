"""Helpers for file-backed prompt and response transport."""

from pathlib import Path
from tempfile import NamedTemporaryFile


def write_markdown_prompt_file(text: str) -> str:
    """Write prompt text into a temporary markdown file and return its path."""
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".md",
        prefix="clink-prompt-",
        delete=False,
    ) as handle:
        handle.write(text)
        return handle.name


def write_markdown_output_file(path: str, text: str) -> None:
    """Persist response text to a markdown file path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text)
