"""Per-CLI output parsers for clink-mcp.

Each parser extracts response text from CLI-specific output format.
Falls back to raw text on parse failure.
"""

import json
import logging

logger = logging.getLogger(__name__)


def _error_message(stderr: str, exit_code: int) -> str:
    return f"[Error] CLI exited with code {exit_code}.\n{stderr}".strip()


def _fallback_raw_text(cli_name: str, stdout: str) -> str:
    raw = stdout.strip()
    logger.warning(
        "Parser fallback triggered for %s; returning raw output (%d chars)",
        cli_name,
        len(raw),
    )
    if not raw:
        return f"[Fallback] {cli_name} parser could not extract structured output."
    return (
        f"[Fallback] {cli_name} parser could not extract structured output.\n\n{raw}"
    )


def _coerce_text_field(
    cli_name: str,
    data: dict,
    field_names: tuple[str, ...],
    stdout: str,
) -> str:
    for field_name in field_names:
        if field_name not in data:
            continue
        value = data[field_name]
        if isinstance(value, str):
            return value
        if value is None:
            return _fallback_raw_text(cli_name, stdout)
        return json.dumps(value)
    return json.dumps(data)


def parse_codex(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Codex JSONL output. Extract message content from event stream."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    messages = []
    for line in stdout.strip().splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "message":
                messages.append(event.get("content", ""))
                continue

            item = event.get("item")
            if (
                event.get("type") == "item.completed"
                and isinstance(item, dict)
                and item.get("type") == "agent_message"
            ):
                messages.append(item.get("text", ""))
        except json.JSONDecodeError:
            continue

    return "\n".join(messages) if messages else _fallback_raw_text("codex", stdout)


def parse_gemini(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Gemini JSON output. Extract response field."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return _coerce_text_field("gemini", data, ("response", "text"), stdout)
    except json.JSONDecodeError:
        pass

    return _fallback_raw_text("gemini", stdout)


def parse_claude(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Claude JSON output. Extract result field."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return _coerce_text_field("claude", data, ("result", "content"), stdout)
    except json.JSONDecodeError:
        pass

    return _fallback_raw_text("claude", stdout)


_PARSERS = {
    "codex": parse_codex,
    "gemini": parse_gemini,
    "claude": parse_claude,
}


def parse_output(cli_name: str, stdout: str, stderr: str, exit_code: int) -> str:
    """Dispatch to the appropriate parser by CLI name."""
    parser = _PARSERS.get(cli_name)
    if parser:
        return parser(stdout, stderr, exit_code)
    return stdout.strip()
