# 2026-03-22 Testing And Context Notes

## Scope

These notes capture local findings from hands-on verification of the MCP server
installed from commit `2958e5e7dfb66ef70aaed75cbda0ba1e200b92b6`.

## Environment Findings

- The MCP server loaded successfully in Codex after restart.
- `list_clients` returned `codex`, `gemini`, and `claude`.
- The installed server binary and import path were already verified before this
  working copy was created.

## End-To-End Runtime Checks

### Claude via `clink-mcp`

- Direct tool call succeeded with `cli_name="claude"` and `model="opus"`.
- The configured Claude effort is `high` via `clients.yaml`.
- A delegated-agent proof also succeeded.

### Gemini via `clink-mcp`

- Direct tool call succeeded with default Gemini settings.
- Default model in `clients.yaml` is `gemini-3-flash-preview`.
- A delegated-agent proof also succeeded.

### Codex direct CLI

- Direct CLI call succeeded with `gpt-5.4` and
  `model_reasoning_effort="xhigh"`.
- A delegated-agent proof also succeeded.

### Codex via `clink-mcp`

- `clink-mcp` currently hardcodes Codex to
  `model_reasoning_effort="high"` in `clients.yaml`.
- Because of that, `xhigh` is verified for direct `codex exec`, but not through
  the current `clink-mcp` abstraction.

## How Context Is Passed Today

Implementation reference: `src/clink_mcp/server.py`

`clink-mcp` now assembles one final prompt string from:

1. Role prompt file contents, if configured
2. User prompt
3. A structured context bundle derived from `file_paths`

Important details:

- `file_paths` no longer mean path-only by default.
- The tool accepts `context_mode="auto" | "paths" | "embed"`.
- `paths` adds a manifest only and does not embed file contents.
- `embed` inlines readable file contents with line numbers.
- `auto` behaves like `embed` for readable UTF-8 text files and explicitly
  reports skipped unreadable or binary entries.
- Embedded context is truncated deterministically by `max_file_bytes` and
  `max_total_bytes`.
- Missing files, binary files, and context-limit skips are reported in the
  context manifest rather than silently ignored.
- The server does not create a stored context object and does not pass a
  context reference or handle.
- The final prompt is passed directly to the downstream CLI command.
- Output is captured from `stdout` and parsed in
  `src/clink_mcp/parsers.py`.
- For current Codex JSONL output, `clink-mcp` should extract text from both
  legacy `type="message"` events and current `item.completed` events carrying
  `item.type="agent_message"`.

## Practical Consequences

- Narrow, well-scoped questions still work well.
- Repo-specific consultations are more reliable when `context_mode` embeds the
  exact source text that the downstream model should reason over.
- Hallucination risk is reduced because the prompt now records which files were
  embedded, truncated, skipped, or missing.
- Prompt exposure remains an open concern because the assembled context still
  travels inline through CLI invocation arguments.

## Why This Matters

The current design is usable for:

- second opinions
- focused code review
- bounded consultations
- model-to-model comparison
- targeted local-code analysis when relevant files are embedded

The current design is weak for:

- broad repo analysis with no attached context
- very large context sets that exceed prompt-size limits
- workflows that need stronger local prompt privacy than inline argv transport

## Verification Notes For Structured Context Bundle

- Unit verification should cover both manifest-only and embedded-content modes.
- Manual verification should use explicit byte limits so truncation behavior is
  observable and repeatable.
- A representative local check is:
  `context_mode="embed"`, `max_file_bytes=4000`, `max_total_bytes=4000` on
  `src/clink_mcp/server.py`.
- Current Codex verification should confirm that the parsed response is plain
  text, not the raw JSONL event stream.
- Success criterion for manual verification is that the downstream answer cites
  details from the embedded file contents rather than responding generically.

## Suggested Next Development Topics

1. Decide whether context transport should stay inline or move to a safer
   mechanism such as stdin or temp files.
2. Verify stdin or temp-file prompt transport separately for Codex, Gemini, and
   Claude before changing the runtime default.
3. Add selective include options later if the API needs line ranges or explicit
   file snippets instead of whole-file embedding.
4. Consider whether Codex effort should be configurable per call instead of
   fixed in `clients.yaml`.
