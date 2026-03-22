"""Context bundle assembly for file-based consultations."""

from pathlib import Path

_VALID_CONTEXT_MODES = {"auto", "embed", "paths"}


def _validate_context_mode(context_mode: str) -> None:
    if context_mode not in _VALID_CONTEXT_MODES:
        valid_modes = ", ".join(sorted(_VALID_CONTEXT_MODES))
        raise ValueError(
            f"Invalid context_mode '{context_mode}'. Use one of: {valid_modes}"
        )


def _read_text_file(path: Path) -> tuple[str | None, str | None]:
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None, "unreadable or binary"

    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "unreadable or binary"


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text, False
    clipped = raw[:limit].decode("utf-8", errors="ignore")
    return clipped, True


def _render_numbered_lines(text: str) -> str:
    return "\n".join(
        f"{line_no} | {line}" for line_no, line in enumerate(text.splitlines(), start=1)
    )


def build_context_section(
    file_paths: list[str] | None,
    context_mode: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> str:
    """Build a deterministic context section for attached file paths."""
    if not file_paths:
        return ""

    _validate_context_mode(context_mode)

    lines = ["Context manifest:"]
    rendered_files = []
    total_bytes = 0

    for raw_path in file_paths:
        path = Path(raw_path)
        if not path.exists():
            lines.append(f"- {raw_path} [missing]")
            continue

        if context_mode == "paths":
            lines.append(f"- {raw_path} [contents not included]")
            continue

        text, error = _read_text_file(path)
        if error:
            lines.append(f"- {raw_path} [skipped: {error}]")
            continue

        truncated_text, file_truncated = _truncate_text(text, max_file_bytes)
        remaining = max_total_bytes - total_bytes
        if remaining <= 0:
            lines.append(f"- {raw_path} [skipped: total context limit reached]")
            continue

        embedded_text, total_truncated = _truncate_text(truncated_text, remaining)
        total_bytes += len(embedded_text.encode("utf-8"))
        status = "truncated" if file_truncated or total_truncated else "embedded"
        lines.append(f"- {raw_path} [{status}]")
        rendered_files.append(f"File: {raw_path}\n{_render_numbered_lines(embedded_text)}")

    if rendered_files:
        lines.append("")
        lines.append("Context files:")
        lines.extend(rendered_files)

    return "\n".join(lines)
