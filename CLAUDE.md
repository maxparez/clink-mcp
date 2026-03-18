# clink-mcp

Lightweight Python MCP server — CLI-to-CLI bridge for Codex, Gemini, Claude.

## Quick Reference
- **Language**: Python 3.12+, code in English, no UI
- **Dependencies**: mcp (FastMCP), pyyaml
- **Entry point**: `src/clink_mcp/server.py:main()`
- **Config**: `clients.yaml` (YAML, single file for all CLI clients)
- **Design doc**: `docs/plans/2026-03-18-clink-mcp-design.md`

## Commands
```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run server
clink-mcp

# Tests
pytest -v
```

## Principles
- KISS, DRY, YAGNI
- Max 200 lines per file, 50 lines per function
- No classes where functions suffice
- No PAL compatibility needed
