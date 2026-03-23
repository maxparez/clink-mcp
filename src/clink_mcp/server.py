"""clink-mcp: Lightweight MCP server for CLI-to-CLI bridge."""

import asyncio
import json
import logging
import shlex
import shutil
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from clink_mcp.config import load_config, resolve_config_path, resolve_prompt
from clink_mcp.context import build_context_bundle, build_context_section
from clink_mcp.parsers import parse_output
from clink_mcp.transport import (
    validate_markdown_path,
    write_markdown_output_file,
    write_markdown_prompt_file,
)

mcp = FastMCP("clink-mcp")
logger = logging.getLogger(__name__)

_clients: dict = {}


def _load_clients() -> dict:
    """Load clients config (lazy, cached)."""
    global _clients
    if not _clients:
        config_path = resolve_config_path()
        _clients = load_config(config_path)
        logger.debug("Cached client configuration from %s", config_path)
    return _clients


def merge_args(base_args: list, role_args: list | None) -> list:
    """Merge base client args with role-specific args."""
    if not role_args:
        return list(base_args)
    return list(base_args) + list(role_args)


def _normalize_file_paths(
    file_paths: list[str] | str | None,
) -> list[str] | None:
    """Accept either a real list or a comma-separated compatibility string."""
    if file_paths is None:
        return None
    if isinstance(file_paths, str):
        parts = [part.strip() for part in file_paths.split(",")]
        normalized = [part for part in parts if part]
        return normalized or None
    return file_paths


def _resolve_role_config(client: dict, role: str) -> dict:
    """Resolve role config and fail fast on invalid role names."""
    roles = client.get("roles", {})
    if role not in roles:
        available = ", ".join(sorted(roles.keys()))
        raise ValueError(f"Unknown role '{role}'. Available: {available}")
    return roles[role]


def build_command(
    client: dict,
    prompt: str,
    role: str,
    model: str | None,
    file_paths: list[str] | None,
    context_mode: str = "auto",
    max_file_bytes: int = 12_000,
    max_total_bytes: int = 48_000,
    extra_args: list[str] | None = None,
) -> tuple[list[str], str | None]:
    """Build CLI command from client config, role, and prompt."""
    parts = shlex.split(client["command"])
    role_config = _resolve_role_config(client, role)
    args = merge_args(client.get("args", []), role_config.get("args"))

    use_model = model or client.get("models", {}).get("default")
    if use_model:
        args.extend(["--model", use_model])
    if extra_args:
        args.extend(extra_args)

    full_prompt = _build_prompt(
        prompt,
        role_config,
        file_paths,
        context_mode=context_mode,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    logger.debug(
        "Built prompt for role=%s transport=%s (%d chars)",
        role,
        client.get("prompt_transport", "inline"),
        len(full_prompt),
    )

    if client.get("prompt_transport") == "stdin_markdown":
        stdin_file = write_markdown_prompt_file(full_prompt)
        stdin_args = client.get("stdin_prompt_args", [])
        return parts + args + list(stdin_args), stdin_file

    prompt_flag = client.get("prompt_flag")
    if prompt_flag:
        return parts + args + [prompt_flag, full_prompt], None
    return parts + args + [full_prompt], None


def _build_prompt(
    prompt: str,
    role_config: dict,
    file_paths: list[str] | None,
    context_mode: str = "auto",
    max_file_bytes: int = 12_000,
    max_total_bytes: int = 48_000,
) -> str:
    """Compose final prompt from user prompt, role system prompt, and file paths."""
    sections = []

    prompt_file = role_config.get("prompt_file")
    if prompt_file:
        system_prompt = resolve_prompt(prompt_file)
        sections.append(system_prompt)

    sections.append(prompt)

    context_section = build_context_section(
        file_paths,
        context_mode=context_mode,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    if context_section:
        sections.append(context_section)

    return "\n\n".join(sections)


def _status_from_text(result_text: str) -> str:
    if result_text.startswith("[Error]"):
        return "error"
    if result_text.startswith("[Fallback]"):
        return "fallback"
    return "success"


def _build_response(
    result_text: str,
    *,
    cli_name: str,
    model: str | None,
    role: str,
    exit_code: int | None,
    duration_ms: int | None,
    context_manifest: list[dict[str, object]] | None,
) -> dict[str, object]:
    return {
        "status": _status_from_text(result_text),
        "text": result_text,
        "meta": {
            "cli": cli_name,
            "model": model,
            "role": role,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "context_manifest": context_manifest or [],
        },
    }


def _render_response(response: dict[str, object], response_format: str) -> str:
    if response_format == "text":
        return str(response["text"])
    if response_format == "json":
        return json.dumps(response, indent=2)
    raise ValueError("Invalid response_format '"
                     f"{response_format}'. Use one of: text, json")


async def run_cli(
    cli_name: str,
    command: list[str],
    timeout: int = 300,
    stdin_file: str | None = None,
) -> dict[str, object]:
    """Execute CLI command as async subprocess and return parsed output plus metadata."""
    executable = command[0]
    if not shutil.which(executable):
        return {
            "text": f"[Error] CLI not found: {executable}",
            "exit_code": None,
            "duration_ms": 0,
        }

    start = time.monotonic()
    communicate_coro = None
    try:
        stdin_stream = asyncio.subprocess.PIPE if stdin_file else asyncio.subprocess.DEVNULL
        logger.debug("Launching CLI %s with %d args", cli_name, len(command))
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=stdin_stream,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdin_bytes = None
        if stdin_file:
            stdin_bytes = Path(stdin_file).read_bytes()
        communicate_coro = proc.communicate(stdin_bytes)
        stdout_bytes, stderr_bytes = await asyncio.wait_for(communicate_coro, timeout=timeout)
    except asyncio.TimeoutError:
        if communicate_coro is not None:
            communicate_coro.close()
        proc.kill()
        await proc.wait()
        logger.warning("CLI %s timed out after %ss", cli_name, timeout)
        return {
            "text": f"[Error] CLI timed out after {timeout}s",
            "exit_code": None,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    logger.debug(
        "CLI %s finished in %.2fs with exit_code=%s",
        cli_name,
        time.monotonic() - start,
        proc.returncode,
    )
    return {
        "text": parse_output(cli_name, stdout, stderr, proc.returncode or 0),
        "exit_code": proc.returncode,
        "duration_ms": int((time.monotonic() - start) * 1000),
    }


async def execute_clink_call(
    prompt: str,
    cli_name: str,
    role: str = "default",
    model: str | None = None,
    file_paths: list[str] | str | None = None,
    context_mode: str = "auto",
    max_file_bytes: int = 12_000,
    max_total_bytes: int = 48_000,
    output_file: str | None = None,
    response_format: str = "text",
    extra_args: list[str] | None = None,
    timeout: int = 300,
) -> str:
    """Execute one clink request without going through MCP schema validation."""
    clients = _load_clients()
    cli_name_lower = cli_name.lower()
    normalized_file_paths = _normalize_file_paths(file_paths)
    if response_format not in {"text", "json"}:
        return (
            f"[Error] Invalid response_format '{response_format}'. "
            "Use one of: text, json"
        )

    if cli_name_lower not in clients:
        available = ", ".join(clients.keys())
        error_response = _build_response(
            f"[Error] Unknown CLI '{cli_name}'. Available: {available}",
            cli_name=cli_name_lower,
            model=model,
            role=role,
            exit_code=None,
            duration_ms=None,
            context_manifest=[],
        )
        return _render_response(error_response, response_format)

    try:
        if output_file:
            validate_markdown_path(output_file)
    except ValueError as exc:
        error_response = _build_response(
            f"[Error] {exc}",
            cli_name=cli_name_lower,
            model=model,
            role=role,
            exit_code=None,
            duration_ms=None,
            context_manifest=[],
        )
        return _render_response(error_response, response_format)

    client = clients[cli_name_lower]
    use_model = model or client.get("models", {}).get("default")
    context_manifest: list[dict[str, object]] = []
    try:
        _context_section, context_manifest = build_context_bundle(
            normalized_file_paths,
            context_mode=context_mode,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )
        command, stdin_file = build_command(
            client,
            prompt,
            role,
            model,
            normalized_file_paths,
            context_mode=context_mode,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
            extra_args=extra_args,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        error_response = _build_response(
            f"[Error] {exc}",
            cli_name=cli_name_lower,
            model=use_model,
            role=role,
            exit_code=None,
            duration_ms=None,
            context_manifest=context_manifest,
        )
        return _render_response(error_response, response_format)
    try:
        execution = await run_cli(
            cli_name_lower,
            command,
            timeout=timeout,
            stdin_file=stdin_file,
        )
    finally:
        if stdin_file:
            Path(stdin_file).unlink(missing_ok=True)

    response = _build_response(
        str(execution["text"]),
        cli_name=cli_name_lower,
        model=use_model,
        role=role,
        exit_code=execution.get("exit_code"),
        duration_ms=execution.get("duration_ms"),
        context_manifest=context_manifest,
    )
    result = str(response["text"])
    if output_file:
        write_markdown_output_file(output_file, result)
    logger.debug("Completed clink call for cli=%s", cli_name_lower)
    return _render_response(response, response_format)


@mcp.tool()
async def clink(
    prompt: str,
    cli_name: str,
    role: str = "default",
    model: str | None = None,
    file_paths: list[str] | str | None = None,
    context_mode: str = "auto",
    max_file_bytes: int = 12_000,
    max_total_bytes: int = 48_000,
    output_file: str | None = None,
    response_format: str = "text",
    extra_args: list[str] | None = None,
) -> str:
    """Send a prompt to an external CLI (codex, gemini, claude) and return the result.

    Args:
        prompt: The request to send to the CLI.
        cli_name: Which CLI to use: codex, gemini, or claude.
        role: Role preset (default, codereviewer, docgen, trusted).
        model: Override the default model for this call.
        file_paths: Absolute paths to relevant files. Accepts either a real
            list or a comma-separated compatibility string. Entries may also
            use "path:start-end" to embed only a selected line range.
        context_mode: "paths" keeps a manifest only, "embed" inlines readable
            file contents, and "auto" embeds readable text files while
            explicitly skipping unreadable ones.
        max_file_bytes: Per-file byte limit for embedded context.
        max_total_bytes: Total byte limit for embedded context across files.
        output_file: Optional markdown file path for persisting the parsed result.
        response_format: "text" keeps the legacy string result, while "json"
            returns a structured envelope as a JSON string.
        extra_args: Optional raw CLI args appended after configured defaults for
            per-call overrides such as effort or provider-specific flags.
    """
    return await execute_clink_call(
        prompt=prompt,
        cli_name=cli_name,
        role=role,
        model=model,
        file_paths=file_paths,
        context_mode=context_mode,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        output_file=output_file,
        response_format=response_format,
        extra_args=extra_args,
    )


@mcp.tool()
async def list_clients() -> str:
    """List available CLI clients, their roles, and models."""
    clients = _load_clients()
    lines = []
    for name, cfg in clients.items():
        models = cfg.get("models", {})
        roles = list(cfg.get("roles", {}).keys())
        lines.append(
            f"- **{name}**: model={models.get('default')} "
            f"(available: {', '.join(models.get('available', []))}) "
            f"| roles: {', '.join(roles)}"
        )
    return "\n".join(lines)


def main():
    """Entry point for clink-mcp server."""
    mcp.run()


if __name__ == "__main__":
    main()
