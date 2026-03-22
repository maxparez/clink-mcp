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
- `file_paths` can now use `path:start-end` to embed only selected line ranges
  instead of whole-file content.
- Embedded context is truncated deterministically by `max_file_bytes` and
  `max_total_bytes`.
- Missing files, binary files, and context-limit skips are reported in the
  context manifest rather than silently ignored.
- The assembled prompt is written to a temporary markdown file for configured
  clients and then streamed to the downstream CLI via `stdin`.
- In the current checked implementation this is the default for Codex, Gemini,
  and Claude.
- The temp prompt directory can be pinned explicitly with
  `CLINK_TRANSPORT_DIR` when operators need stronger control over where prompt
  files land.
- Temporary prompt files are deleted after the CLI call returns.
- The server does not create a stored context object and does not pass a
  context reference or handle.
- Bundled `clients.yaml` and prompt templates are now resolved through
  `importlib.resources` instead of relying only on repo-root path guessing.
- Output is captured from `stdout` and parsed in
  `src/clink_mcp/parsers.py`.
- For current Codex JSONL output, `clink-mcp` should extract text from both
  legacy `type="message"` events and current `item.completed` events carrying
  `item.type="agent_message"`.
- If a known CLI parser cannot extract structured output, the returned text is
  now explicitly marked with a `[Fallback]` prefix instead of silently passing
  through raw output.
- When requested, the parsed response can also be persisted to a caller-chosen
  markdown file via `output_file`.

## Practical Consequences

- Narrow, well-scoped questions still work well.
- Repo-specific consultations are more reliable when `context_mode` embeds the
  exact source text that the downstream model should reason over.
- Focused consultations are better served by ranged snippets than by large
  whole-file embeddings, especially when prompt budget is tight.
- Hallucination risk is reduced because the prompt now records which files were
  embedded, truncated, skipped, or missing.
- Parser degradation is easier to notice because raw fallback is explicitly
  marked and warning-logged.
- Prompt exposure is lower than the previous argv-only transport because prompt
  text is no longer appended directly to the command line for configured
  clients.
- Local prompt exposure is not eliminated because temporary files still exist
  briefly on disk during execution.
- `CLINK_TRANSPORT_DIR` improves operational control, but it also shifts
  responsibility to the caller to choose a directory with appropriate local
  permissions and cleanup policy.
- Basic observability is now present through module-level logging in config
  resolution, prompt transport, parser fallback, and CLI execution/timeout
  paths.

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
- workflows that need stronger local prompt privacy than temporary files on disk

## Verification Notes For Structured Context Bundle

- Unit verification should cover both manifest-only and embedded-content modes.
- Manual verification should use explicit byte limits so truncation behavior is
  observable and repeatable.
- A representative local check is:
  `context_mode="embed"`, `max_file_bytes=4000`, `max_total_bytes=4000` on
  `src/clink_mcp/server.py`, using file-backed prompt transport.
- A representative markdown-output check is:
  set `output_file` to a `.md` path and confirm the parsed final response is
  written there verbatim.
- `tests/smoke_test.sh` should exercise Codex, Gemini, and Claude against the
  same attached local snippet and verify at least one markdown output file write.
- `tests/smoke_test.sh` now also exercises the `testgen` role against one small
  Python function using a single fast provider in the first iteration and
  checks that the response contains one fenced code block, a `<SUMMARY>`
  section, and the attached function name `add_one`.
- `testgen` should be treated as a candidate-test workflow: generate markdown
  first, then let the orchestrator decide whether to save or apply it.
- For `testgen`, provider reliability may differ by model; the current smoke
  path uses one fast provider rather than forcing all three through the same
  workload.
- Current Codex verification should confirm that the parsed response is plain
  text, not the raw JSONL event stream, unless an explicit `[Fallback]` marker
  is expected.
- Success criterion for manual verification is that the downstream answer cites
  details from the embedded file contents rather than responding generically.

## Suggested Next Development Topics

1. Consider whether prompt temp files should support a caller-selected secure
   directory or explicit retention for debugging.
2. Add selective include options later if the API needs line ranges or explicit
   file snippets instead of whole-file embedding.
3. Consider whether Codex effort should be configurable per call instead of
   fixed in `clients.yaml`.
4. If `testgen` becomes popular, decide whether the markdown-only output contract
   needs a more structured artifact format for easier downstream parsing.
