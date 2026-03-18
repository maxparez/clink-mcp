# clink-mcp — Design Document

**Date**: 2026-03-18
**Status**: Draft
**Author**: Max Parez + Claude

## Goal

Lightweight Python MCP server providing CLI-to-CLI bridge functionality.
Extracted from PAL MCP Server (BeehiveInnovations/pal-mcp-server) — only the `clink` concept, no PAL dependency.

## Motivation

- PAL MCP is a large project with 16 tools; we only use `clink`
- We want full control, simplicity, and independence
- We need specialized workflows (codereview, docgen) built as prompts over the same bridge

## Architecture

### Core Principle

One MCP server, two tools, three CLI clients, three prompt templates.

### MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `clink` | `prompt` (required), `cli_name` (required), `role`, `model`, `file_paths` | Send prompt to external CLI and return result |
| `list_clients` | none | Return available clients, roles, and models |

### Supported CLI Clients

| Client | Command | Non-interactive mode | Output format |
|--------|---------|---------------------|---------------|
| Codex | `codex exec` | default (exec subcommand) | `--json` (JSONL) |
| Gemini | `gemini` | `-p` flag | `--output-format json` |
| Claude | `claude` | `-p` flag | `--output-format json` |

### Configuration

Single `clients.yaml` file. Location resolved in order:
1. `CLIENTS_CONFIG` env var
2. `~/.clink-mcp/clients.yaml`
3. Bundled default in package

Structure per client:
```yaml
clients:
  <name>:
    command: "<cli command>"
    args: [<base arguments>]
    models:
      default: "<model name>"
      available: [<model list>]
    roles:
      default:
        prompt_file: "prompts/consult.txt"
      <role_name>:
        prompt_file: "prompts/<role>.txt"
        args: [<extra args for this role>]
```

Args merge order: base args + role args + runtime args.

### Parsers

Minimal per-client functions (~20 lines each) in one file `parsers.py`:
- Extract response text from CLI-specific JSON/JSONL output
- Error detection from stderr/exit code
- Fallback to raw text on parse failure

No classes, no inheritance, no registry pattern.

### Prompts

All prompts share `<SUMMARY>` output format (max ~12 bullets).

| Prompt | Purpose |
|--------|---------|
| `consult.txt` | General consultation — recommendation, trade-offs, risks, next steps |
| `codereview.txt` | Code review — bugs, security, KISS/DRY violations, severity levels (critical/warning/suggestion) |
| `docgen.txt` | Documentation generation — module overview, public API, usage examples in markdown |

Hard constraints in all prompts:
- Keep output short and actionable
- No large code blocks — cite file paths and symbols only
- Consultants read files themselves (they have filesystem access)

## Project Structure

```
clink-mcp/
├── src/
│   └── clink_mcp/
│       ├── __init__.py
│       ├── server.py         # MCP server (~150 lines)
│       ├── parsers.py        # Per-CLI parsers (~80 lines)
│       └── config.py         # Load clients.yaml (~40 lines)
├── prompts/
│   ├── consult.txt
│   ├── codereview.txt
│   └── docgen.txt
├── clients.yaml              # Default/example configuration
├── pyproject.toml
└── README.md
```

Total Python code: ~270 lines.

## Distribution

- GitHub repo: `maxparez/clink-mcp`
- Install via `uvx`: `uvx --from git+https://github.com/maxparez/clink-mcp.git clink-mcp`
- No PyPI publishing

### Usage in projects

Each project adds to its `.claude/settings.local.json`:
```json
{
  "mcpServers": {
    "clink": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/maxparez/clink-mcp.git", "clink-mcp"],
      "env": {
        "CLIENTS_CONFIG": "/path/to/custom/clients.yaml"
      }
    }
  }
}
```

Skills/commands (consult, codereview, docgen, setup, smoke) are NOT part of this repo — each project defines its own in `.claude/commands/`.

## Relationship to Existing Projects

- **PAL MCP Server**: Inspiration only, no code dependency, no compatibility needed
- **uctoteka-clink-consult plugin**: Stays unchanged in uctoteka_app, independent

## CLI Reference (for clients.yaml configuration)

### Codex CLI
- `codex exec <prompt>` — non-interactive
- `--model, -m` — model override (e.g. `gpt-5-codex`)
- `--sandbox, -s` — `read-only`, `workspace-write`, `danger-full-access`
- `--json` — JSONL output
- `--skip-git-repo-check` — run outside git repos
- `--ask-for-approval` — `untrusted`, `on-request`, `never`
- `--full-auto` — shortcut for on-request + workspace-write

### Gemini CLI
- `gemini -p <prompt>` — non-interactive
- `-m, --model` — model override (e.g. `gemini-2.5-pro`)
- `--output-format` — `json`, `stream-json`, `text`
- `--yolo` — no confirmations (trusted mode)
- `--include-directories` — add directories to context

### Claude Code CLI
- `claude -p <prompt>` — non-interactive (print mode)
- `--model` — `sonnet`, `opus`, or full model ID
- `--output-format` — `text`, `json`, `stream-json`
- `--system-prompt` / `--system-prompt-file` — custom system prompt
- `--append-system-prompt` — add to default prompt
- `--max-turns` — limit agentic steps
- `--max-budget-usd` — cost limit
- `--effort` — `low`, `medium`, `high`, `max`
- `--tools` — restrict tools (e.g. `Bash,Edit,Read`)
- `--dangerously-skip-permissions` — no confirmations

## Non-Goals

- No PAL compatibility
- No plugin packaging (each project configures MCP directly)
- No web UI
- No multi-turn conversation management (single request-response)
- No model provider API integration (CLI only)
