# AGENTS.md

This file is the durable operating guide for agents working in the
`clink-mcp` repository.

## Purpose

- Keep repository-specific rules in one place.
- Point agents to the real implementation entry points.
- Preserve important architectural constraints between sessions.

## Read First

Read these files before making changes:

1. `README.md`
2. `CLAUDE.md`
3. `clients.yaml`
4. `src/clink_mcp/server.py`
5. `src/clink_mcp/parsers.py`
6. `docs/2026-03-22-testing-and-context-notes.md` for current findings and open concerns

## Repository Facts

- Language: Python 3.12+
- MCP framework: FastMCP
- Main entry point: `src/clink_mcp/server.py`
- Client registry: `clients.yaml`
- Prompt templates: `prompts/`
- Tests: `tests/`

## Core Behavioral Rules

- Keep the server small and explicit. Prefer simple functions over abstractions.
- Do not silently change prompt transport semantics. Context delivery is a core product behavior.
- Treat `clients.yaml` as user-facing contract. Changes there affect runtime behavior immediately.
- Preserve per-CLI output parsing behavior unless you also update tests and docs.
- If you change how context is passed to downstream CLIs, document the security and correctness tradeoffs in the same change.
- If you add or change role prompts, verify that the resulting prompt assembly still matches `server.py`.

## Current Design Risk

- The main open concern is context transfer quality and safety.
- Today, `clink-mcp` builds one prompt string from role prompt content, user prompt, and optional `file_paths`.
- That prompt is passed directly to downstream CLIs, rather than through a stored context object or file reference abstraction.
- Any change in this area should be tested against correctness, hallucination risk, and local prompt exposure.
- Separately from `clink-mcp` itself, stock Codex host usage appears to impose an outer MCP tool-call timeout around 120 seconds.
- Treat that host-side ceiling as a workflow constraint: do not assume a long-running downstream CLI call can complete just because `clink-mcp` allows a longer internal timeout.

## Workflow Expectations

- Prefer small, reviewable changes.
- Update docs when runtime behavior changes.
- Run the relevant verification before claiming success.
- For prompt transport or parsing changes, verify at least one real end-to-end CLI call in addition to unit tests.
- For workflow guidance, distinguish clearly between `clink-mcp` runtime behavior and host-specific limits such as stock Codex MCP timeout ceilings.
