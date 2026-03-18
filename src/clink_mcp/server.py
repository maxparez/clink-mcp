"""clink-mcp: Lightweight MCP server for CLI-to-CLI bridge."""

import asyncio
import shlex
import shutil

from mcp.server.fastmcp import FastMCP

from clink_mcp.config import load_config, resolve_config_path, resolve_prompt
from clink_mcp.parsers import parse_output

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


def build_command(
    client: dict,
    prompt: str,
    role: str,
    model: str | None,
    file_paths: list[str] | None,
) -> list[str]:
    """Build CLI command from client config, role, and prompt."""
    parts = shlex.split(client["command"])
    role_config = client.get("roles", {}).get(role, {})
    args = merge_args(client.get("args", []), role_config.get("args"))

    use_model = model or client.get("models", {}).get("default")
    if use_model:
        args.extend(["--model", use_model])

    full_prompt = _build_prompt(prompt, role_config, file_paths)

    return parts + args + [full_prompt]


def _build_prompt(
    prompt: str,
    role_config: dict,
    file_paths: list[str] | None,
) -> str:
    """Compose final prompt from user prompt, role system prompt, and file paths."""
    sections = []

    prompt_file = role_config.get("prompt_file")
    if prompt_file:
        try:
            system_prompt = resolve_prompt(prompt_file)
            sections.append(system_prompt)
        except FileNotFoundError:
            pass

    sections.append(prompt)

    if file_paths:
        files_section = "Relevant files:\n" + "\n".join(
            f"- {p}" for p in file_paths
        )
        sections.append(files_section)

    return "\n\n".join(sections)


async def run_cli(cli_name: str, command: list[str], timeout: int = 300) -> str:
    """Execute CLI command as async subprocess and return parsed output."""
    executable = command[0]
    if not shutil.which(executable):
        return f"[Error] CLI not found: {executable}"

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
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
) -> str:
    """Send a prompt to an external CLI (codex, gemini, claude) and return the result.

    Args:
        prompt: The request to send to the CLI.
        cli_name: Which CLI to use: codex, gemini, or claude.
        role: Role preset (default, codereviewer, docgen, trusted).
        model: Override the default model for this call.
        file_paths: Absolute paths to relevant files (included in prompt).
    """
    clients = _load_clients()
    cli_name_lower = cli_name.lower()

    if cli_name_lower not in clients:
        available = ", ".join(clients.keys())
        return f"[Error] Unknown CLI '{cli_name}'. Available: {available}"

    client = clients[cli_name_lower]
    command = build_command(client, prompt, role, model, file_paths)
    return await run_cli(cli_name_lower, command)


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
