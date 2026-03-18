"""Per-CLI output parsers for clink-mcp.

Each parser extracts response text from CLI-specific output format.
Falls back to raw text on parse failure.
"""

import json


def _error_message(stderr: str, exit_code: int) -> str:
    return f"[Error] CLI exited with code {exit_code}.\n{stderr}".strip()


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
        except json.JSONDecodeError:
            continue

    return "\n".join(messages) if messages else stdout.strip()


def parse_gemini(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Gemini JSON output. Extract response field."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return data.get("response", data.get("text", json.dumps(data)))
    except json.JSONDecodeError:
        pass

    return stdout.strip()


def parse_claude(stdout: str, stderr: str, exit_code: int) -> str:
    """Parse Claude JSON output. Extract result field."""
    if exit_code != 0:
        return _error_message(stderr, exit_code)

    try:
        data = json.loads(stdout)
        if isinstance(data, dict):
            return data.get("result", data.get("content", json.dumps(data)))
    except json.JSONDecodeError:
        pass

    return stdout.strip()


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
