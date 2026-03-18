#!/bin/bash
# Smoke test: verify clink-mcp components work together
set -e

echo "=== clink-mcp smoke test ==="

# Check entry point exists
which clink-mcp || { echo "FAIL: clink-mcp not in PATH"; exit 1; }
echo "OK: entry point found"

# Check clients.yaml loads
python -c "
from clink_mcp.config import resolve_config_path, load_config
path = resolve_config_path()
clients = load_config(path)
print(f'OK: loaded {len(clients)} clients: {list(clients.keys())}')
"

# Check prompts exist and have SUMMARY tag
python -c "
from clink_mcp.config import resolve_prompt
for p in ['prompts/consult.txt', 'prompts/codereview.txt', 'prompts/docgen.txt']:
    text = resolve_prompt(p)
    assert 'SUMMARY' in text, f'{p} missing SUMMARY tag'
    print(f'OK: {p} ({len(text)} chars)')
"

# Check parsers work
python -c "
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
python -c "
from clink_mcp.server import build_command
client = {
    'command': 'echo',
    'args': ['--test'],
    'models': {'default': 'test-model'},
    'roles': {'default': {'prompt_file': 'prompts/consult.txt'}},
}
cmd = build_command(client, 'hello', 'default', None, None)
assert cmd[0] == 'echo'
assert '--model' in cmd
print(f'OK: build_command produces: {\" \".join(cmd[:5])}...')
"

echo "=== All smoke tests passed ==="
