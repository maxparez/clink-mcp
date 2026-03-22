#!/bin/bash
# Smoke test: verify clink-mcp components work together
set -euo pipefail

echo "=== clink-mcp smoke test ==="

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
CLINK_BIN="${CLINK_BIN:-.venv/bin/clink-mcp}"

[ -x "$PYTHON_BIN" ] || { echo "FAIL: python not found at $PYTHON_BIN"; exit 1; }
[ -x "$CLINK_BIN" ] || { echo "FAIL: clink-mcp not found at $CLINK_BIN"; exit 1; }
echo "OK: repo-local python and entry point found"

# Check clients.yaml loads
"$PYTHON_BIN" -c "
from clink_mcp.config import resolve_config_path, load_config
path = resolve_config_path()
clients = load_config(path)
print(f'OK: loaded {len(clients)} clients: {list(clients.keys())}')
"

# Check prompts exist and have SUMMARY tag
"$PYTHON_BIN" -c "
from clink_mcp.config import resolve_prompt
for p in ['prompts/consult.txt', 'prompts/codereview.txt', 'prompts/docgen.txt', 'prompts/testgen.txt']:
    text = resolve_prompt(p)
    assert 'SUMMARY' in text, f'{p} missing SUMMARY tag'
    print(f'OK: {p} ({len(text)} chars)')
"

# Check parsers work
"$PYTHON_BIN" -c "
import json
from clink_mcp.parsers import parse_output
r = parse_output('codex', json.dumps({'type':'message','content':'test'}), '', 0)
print(f'OK: codex parser returned: {r[:50]}')
r = parse_output('gemini', json.dumps({'response':'test'}), '', 0)
print(f'OK: gemini parser returned: {r[:50]}')
r = parse_output('claude', json.dumps({'result':'test'}), '', 0)
print(f'OK: claude parser returned: {r[:50]}')
"

# Check server builds commands correctly
"$PYTHON_BIN" -c "
from clink_mcp.server import build_command
client = {
    'command': 'echo',
    'args': ['--test'],
    'models': {'default': 'test-model'},
    'roles': {'default': {'prompt_file': 'prompts/consult.txt'}},
}
cmd, stdin_file = build_command(client, 'hello', 'default', None, None)
assert cmd[0] == 'echo'
assert '--model' in cmd
assert stdin_file is None
print(f'OK: build_command produces: {\" \".join(cmd[:5])}...')
"

# Check end-to-end transport for all supported CLIs
OUT_FILE="$(mktemp /tmp/clink-smoke-XXXX.md)"
TESTGEN_SOURCE="$(mktemp /tmp/clink-testgen-src-XXXX.py)"
cat > "$TESTGEN_SOURCE" <<'EOF'
def add_one(value):
    return value + 1
EOF
trap 'rm -f "$OUT_FILE" "$TESTGEN_SOURCE"' EXIT
export OUT_FILE
export TESTGEN_SOURCE
"$PYTHON_BIN" - <<'PY'
import asyncio
import os
from pathlib import Path

from clink_mcp.server import clink

TARGET = "/home/pavel/vyvoj_sw/clink-mcp/src/clink_mcp/server.py:39-75"
OUT_FILE = Path(os.environ["OUT_FILE"])
TESTGEN_SOURCE = Path(os.environ["TESTGEN_SOURCE"])


async def check(cli_name: str, *, model: str | None = None, output_file: str | None = None):
    print(f"RUN: {cli_name}", flush=True)
    result = await asyncio.wait_for(
        clink(
            prompt="Name the function build_command if you can see it. Keep the answer short.",
            cli_name=cli_name,
            model=model,
            file_paths=[TARGET],
            context_mode="embed",
            max_file_bytes=2000,
            max_total_bytes=2000,
            output_file=output_file,
        ),
        timeout=90,
    )
    if not result.strip():
        raise AssertionError(f"{cli_name} returned empty output")
    if "build_command" not in result:
        raise AssertionError(f"{cli_name} output did not mention build_command: {result}")
    print(f"OK: {cli_name} end-to-end transport", flush=True)


async def main():
    await check("codex", model="gpt-5.4-mini", output_file=str(OUT_FILE))
    if not OUT_FILE.exists():
        raise AssertionError("codex output_file was not created")
    if "build_command" not in OUT_FILE.read_text():
        raise AssertionError("codex output_file missing expected content")
    print("OK: codex markdown output file", flush=True)

    await check("gemini", model="gemini-2.5-flash-lite")
    await check("claude", model="haiku")

    testgen_result = await asyncio.wait_for(
        clink(
            prompt=(
                "Generate one minimal pytest test for this function. "
                "Keep it short and runnable."
            ),
            cli_name="codex",
            role="testgen",
            model="gpt-5.4-mini",
            file_paths=[str(TESTGEN_SOURCE)],
            context_mode="embed",
            max_file_bytes=2000,
            max_total_bytes=2000,
        ),
        timeout=90,
    )
    if not testgen_result.strip():
        raise AssertionError("testgen returned empty output")
    if testgen_result.count("```") < 2:
        raise AssertionError(f"testgen output missing fenced code block: {testgen_result}")
    if "<SUMMARY>" not in testgen_result:
        raise AssertionError(f"testgen output missing SUMMARY section: {testgen_result}")
    if "add_one" not in testgen_result:
        raise AssertionError(f"testgen output missing source-specific signal: {testgen_result}")
    print("OK: testgen smoke output", flush=True)


asyncio.run(main())
PY

echo "=== All smoke tests passed ==="
