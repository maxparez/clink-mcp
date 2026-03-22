# clink-mcp

Lightweight MCP server that bridges AI CLI tools together. Let Claude call Codex or Gemini, let Codex consult Claude — any combination.

## What it does

clink-mcp exposes a single MCP tool (`clink`) that sends prompts to external AI CLIs and returns the result. This enables **cross-model collaboration** — your primary AI assistant can delegate tasks to other AI models as subagents.

**Supported CLIs:**

| CLI | Command | Default Model | Roles |
|-----|---------|---------------|-------|
| **Codex** (OpenAI) | `codex exec` | gpt-5.4 | default, codereviewer, docgen, testgen |
| **Gemini** (Google) | `gemini` | gemini-3-flash-preview | default, trusted, codereviewer, docgen, testgen |
| **Claude** (Anthropic) | `claude` | opus | default, codereviewer, docgen, testgen |

**Roles** are preset system prompts:
- `default` — consultant (short, actionable answers with summary)
- `codereviewer` — code review (bugs, security, KISS/DRY violations)
- `docgen` — documentation generator
- `testgen` — test generation / repro script generator from narrow local context
- `trusted` (Gemini only) — consultant with `--yolo` flag (auto-approve actions)

## Prerequisites

- Python 3.12+
- At least one CLI installed: [Codex CLI](https://github.com/openai/codex), [Gemini CLI](https://github.com/google-gemini/gemini-cli), or [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Each CLI must be authenticated and working (`codex exec "hello"`, `gemini "hello"`, `claude -p "hello"`)

## Installation

```bash
git clone https://github.com/maxparez/clink-mcp.git
cd clink-mcp
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Configuration in Claude Code

Add to `~/.claude/settings.json` (global) or project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "clink-mcp": {
      "command": "/ABSOLUTE/PATH/TO/clink-mcp/venv/bin/clink-mcp"
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO` with your actual path (e.g. `/root/vyvoj_sw`).

After adding, restart Claude Code. Verify with:
```
> list_clients()
```

### Example usage in Claude Code

Claude can now call other AIs as subagents:

```
"Ask Codex to review this file for security issues"
→ Claude calls: clink(prompt="Review for security issues", cli_name="codex", role="codereviewer", file_paths=["/path/to/file.py"])

"Get a second opinion from Gemini on this architecture"
→ Claude calls: clink(prompt="Evaluate this architecture...", cli_name="gemini")

"Have Codex generate docs for this module"
→ Claude calls: clink(prompt="Generate docs", cli_name="codex", role="docgen", file_paths=["/path/to/module.py"])

"Generate a minimal regression test for this function"
→ Claude calls: clink(
    prompt="Generate one minimal pytest test for this function.",
    cli_name="claude",
    role="testgen",
    model="opus",
    file_paths=["/path/to/module.py:40-95"],
    context_mode="embed",
    output_file="/tmp/testgen.md",
  )
```

## Configuration in Codex CLI

Add to `~/.codex/config.yaml`:

```yaml
mcp_servers:
  - name: clink-mcp
    command: /ABSOLUTE/PATH/TO/clink-mcp/venv/bin/clink-mcp
```

After adding, restart Codex. Codex can then call Claude or Gemini as subagents.

## Custom configuration

clink-mcp looks for `clients.yaml` in this order:

1. `$CLIENTS_CONFIG` environment variable (explicit path)
2. `~/.clink-mcp/clients.yaml` (user config)
3. Bundled `clients.yaml` (project default)

To customize, copy and edit:
```bash
mkdir -p ~/.clink-mcp
cp clients.yaml ~/.clink-mcp/clients.yaml
```

You can add new CLIs, change default models, or create custom roles with your own prompt files.

## Usage recommendations

### When to use cross-model delegation

- **Code review** — get a second opinion from a different model (`role="codereviewer"`)
- **Consultation** — ask another model about its strengths (e.g. Codex for OpenAI ecosystem, Gemini for Google APIs)
- **Documentation** — delegate doc generation to free up the primary agent (`role="docgen"`)
- **Verification** — cross-check critical decisions with an independent model
- **Test generation** — generate a candidate regression test or repro script from narrow local context, then review it before applying

### Tips

- **Specify `file_paths`** when the subagent needs to see code — the paths are included in the prompt
- **Use roles** instead of putting instructions in the prompt — they include optimized system prompts
- **Override models** with the `model` parameter when you need a specific model variant (e.g. `model="haiku"` for fast/cheap Claude responses)
- **Use `extra_args` sparingly** when an orchestrator needs one-off provider flags without editing `clients.yaml`
- **Use `response_format="json"`** when a caller needs a structured envelope; keep the default text mode for human-facing consultations
- **Timeout** is 300s by default — sufficient for most tasks, but complex code reviews may need more
- **Use `role="testgen"`** when you want a markdown-first candidate test or repro script; keep `file_paths` narrow, use `context_mode="embed"`, and review the output before saving or applying it
- **Treat `testgen` provider support as staged** — the role is available for all configured clients, but this repo's smoke workflow currently exercises Codex first for reliability

### What to avoid

- Don't create loops (Claude calling Claude calling Claude)
- Don't delegate simple tasks — the overhead isn't worth it for one-line answers
- Don't send sensitive data through CLIs you don't control
- Don't treat `testgen` output as finished code; it is a candidate artifact that still needs human or orchestrator review

## MCP Tools

### `clink`

Send a prompt to an external CLI and return the result.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | yes | The request to send |
| `cli_name` | string | yes | `codex`, `gemini`, or `claude` |
| `role` | string | no | Role preset (default: `default`) |
| `model` | string | no | Override the default model |
| `file_paths` | string[] | no | Absolute paths to include in prompt |
| `context_mode` | string | no | `auto`, `paths`, or `embed` for file context handling |
| `output_file` | string | no | Optional `.md` path for saving the parsed response |
| `response_format` | string | no | `text` for the legacy string result or `json` for a structured envelope |
| `extra_args` | string[] | no | Raw per-call CLI args appended after configured defaults |

When `response_format="json"`, the tool returns a JSON string with this minimal shape:

```json
{
  "status": "success",
  "text": "parsed response text",
  "meta": {
    "cli": "codex",
    "model": "gpt-5.4",
    "role": "default",
    "exit_code": 0,
    "duration_ms": 1234,
    "context_manifest": []
  }
}
```

`clink-mcp` still remains a single-call execution layer. Scheduling, retries, routing, and state belong in an orchestrator above it.

### `list_clients`

List available CLI clients, their roles, and models. No parameters.

## Development

```bash
pip install -e ".[dev]"
pytest -v
```

## License

MIT
