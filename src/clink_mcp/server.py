"""clink-mcp: Lightweight MCP server for CLI-to-CLI bridge."""

import asyncio
import shlex
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from clink_mcp.config import load_config, resolve_config_path, resolve_prompt
from clink_mcp.context import build_context_section
from clink_mcp.parsers import parse_output
from clink_mcp.transport import (
    validate_markdown_path,
    write_markdown_output_file,
    write_markdown_prompt_file,
)

mcp = FastMCP("clink-mcp")

_clients: dict = {}


def _load_clients() -> dict:
    """Load clients config (lazy, cached)."""
    global _clients
    if not _clients:
        config_path = resolve_config_path()
        _clients = load_config(config_path)
    return _clients


def merge_args(base_args: list, role_args: list | None) -> list:
    """Merge base client args with role-specific args."""
    if not role_args:
        return list(base_args)
    return list(base_args) + list(role_args)


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
) -> tuple[list[str], str | None]:
    """Build CLI command from client config, role, and prompt."""
    parts = shlex.split(client["command"])
    role_config = _resolve_role_config(client, role)
    args = merge_args(client.get("args", []), role_config.get("args"))

    use_model = model or client.get("models", {}).get("default")
    if use_model:
        args.extend(["--model", use_model])

    full_prompt = _build_prompt(
        prompt,
        role_config,
        file_paths,
        context_mode=context_mode,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
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


async def run_cli(
    cli_name: str,
    command: list[str],
    timeout: int = 300,
    stdin_file: str | None = None,
) -> str:
    """Execute CLI command as async subprocess and return parsed output."""
    executable = command[0]
    if not shutil.which(executable):
        return f"[Error] CLI not found: {executable}"

    try:
        stdin_stream = asyncio.subprocess.PIPE if stdin_file else asyncio.subprocess.DEVNULL
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=stdin_stream,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdin_bytes = None
        if stdin_file:
            stdin_bytes = Path(stdin_file).read_bytes()
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(stdin_bytes), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        return f"[Error] CLI timed out after {timeout}s"

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return parse_output(cli_name, stdout, stderr, proc.returncode or 0)


@mcp.tool()
async def clink(
    prompt: str,
    cli_name: str,
    role: str = "default",
    model: str | None = None,
    file_paths: list[str] | None = None,
    context_mode: str = "auto",
    max_file_bytes: int = 12_000,
    max_total_bytes: int = 48_000,
    output_file: str | None = None,
) -> str:
    """Send a prompt to an external CLI (codex, gemini, claude) and return the result.

    Args:
        prompt: The request to send to the CLI.
        cli_name: Which CLI to use: codex, gemini, or claude.
        role: Role preset (default, codereviewer, docgen, trusted).
        model: Override the default model for this call.
        file_paths: Absolute paths to relevant files. Entries may also use
            "path:start-end" to embed only a selected line range.
        context_mode: "paths" keeps a manifest only, "embed" inlines readable
            file contents, and "auto" embeds readable text files while
            explicitly skipping unreadable ones.
        max_file_bytes: Per-file byte limit for embedded context.
        max_total_bytes: Total byte limit for embedded context across files.
        output_file: Optional markdown file path for persisting the parsed result.
    """
    clients = _load_clients()
    cli_name_lower = cli_name.lower()

    if cli_name_lower not in clients:
        available = ", ".join(clients.keys())
        return f"[Error] Unknown CLI '{cli_name}'. Available: {available}"

    try:
        if output_file:
            validate_markdown_path(output_file)
    except ValueError as exc:
        return f"[Error] {exc}"

    client = clients[cli_name_lower]
    try:
        command, stdin_file = build_command(
            client,
            prompt,
            role,
            model,
            file_paths,
            context_mode=context_mode,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        return f"[Error] {exc}"
    try:
        result = await run_cli(cli_name_lower, command, stdin_file=stdin_file)
    finally:
        if stdin_file:
            Path(stdin_file).unlink(missing_ok=True)

    if output_file:
        write_markdown_output_file(output_file, result)
    return result


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
