"""Context bundle assembly for file-based consultations."""

import re
from pathlib import Path

_VALID_CONTEXT_MODES = {"auto", "embed", "paths"}
_LINE_RANGE_PATTERN = re.compile(r"^(?P<path>.+):(?P<start>\d+)-(?P<end>\d+)$")


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


def _parse_file_reference(file_ref: str) -> tuple[Path, tuple[int, int] | None]:
    match = _LINE_RANGE_PATTERN.match(file_ref)
    if not match:
        return Path(file_ref), None
    path = Path(match.group("path"))
    start = int(match.group("start"))
    end = int(match.group("end"))
    return path, (start, end)


def _slice_line_range(text: str, line_range: tuple[int, int]) -> tuple[str | None, str | None]:
    start, end = line_range
    if start <= 0 or end < start:
        return None, "invalid line range"

    lines = text.splitlines()
    if start > len(lines):
        return None, "line range outside file"

    sliced = lines[start - 1 : end]
    if not sliced:
        return None, "line range outside file"
    return "\n".join(sliced), None


def build_context_bundle(
    file_paths: list[str] | None,
    context_mode: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> tuple[str, list[dict[str, object]]]:
    """Build both the rendered context section and a machine-readable manifest."""
    _validate_context_mode(context_mode)

    if not file_paths:
        return "", []

    lines = ["Context manifest:"]
    rendered_files = []
    manifest = []
    total_bytes = 0

    for raw_path in file_paths:
        entry: dict[str, object] = {"path": raw_path}
        path, line_range = _parse_file_reference(raw_path)
        if line_range:
            entry["line_range"] = {"start": line_range[0], "end": line_range[1]}

        if not path.exists():
            lines.append(f"- {raw_path} [missing]")
            entry["status"] = "missing"
            manifest.append(entry)
            continue

        if context_mode == "paths":
            lines.append(f"- {raw_path} [contents not included]")
            entry["status"] = "listed"
            manifest.append(entry)
            continue

        text, error = _read_text_file(path)
        if error:
            lines.append(f"- {raw_path} [skipped: {error}]")
            entry["status"] = "skipped"
            entry["reason"] = error
            manifest.append(entry)
            continue

        if line_range:
            text, range_error = _slice_line_range(text, line_range)
            if range_error:
                lines.append(f"- {raw_path} [skipped: {range_error}]")
                entry["status"] = "skipped"
                entry["reason"] = range_error
                manifest.append(entry)
                continue

        truncated_text, file_truncated = _truncate_text(text, max_file_bytes)
        remaining = max_total_bytes - total_bytes
        if remaining <= 0:
            lines.append(f"- {raw_path} [skipped: total context limit reached]")
            entry["status"] = "skipped"
            entry["reason"] = "total context limit reached"
            manifest.append(entry)
            continue

        embedded_text, total_truncated = _truncate_text(truncated_text, remaining)
        embedded_bytes = len(embedded_text.encode("utf-8"))
        total_bytes += embedded_bytes
        status = "truncated" if file_truncated or total_truncated else "embedded"
        lines.append(f"- {raw_path} [{status}]")
        entry["status"] = status
        entry["bytes"] = embedded_bytes
        manifest.append(entry)
        rendered_files.append(f"File: {raw_path}\n{_render_numbered_lines(embedded_text)}")

    if rendered_files:
        lines.append("")
        lines.append("Context files:")
        lines.extend(rendered_files)

    return "\n".join(lines), manifest


def build_context_section(
    file_paths: list[str] | None,
    context_mode: str,
    max_file_bytes: int,
    max_total_bytes: int,
) -> str:
    """Build a deterministic context section for attached file paths."""
    section, _manifest = build_context_bundle(
        file_paths,
        context_mode=context_mode,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    return section
