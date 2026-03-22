import json

from clink_mcp.parsers import parse_codex, parse_gemini, parse_claude, parse_output


class TestParseCodex:
    def test_extracts_message_from_jsonl(self):
        lines = [
            json.dumps({"type": "message", "content": "Hello from Codex"}),
            json.dumps({"type": "status", "state": "done"}),
        ]
        stdout = "\n".join(lines)
        result = parse_codex(stdout, "", 0)
        assert "Hello from Codex" in result

    def test_fallback_on_invalid_json(self):
        result = parse_codex("plain text output", "", 0)
        assert result == "plain text output"

    def test_extracts_agent_message_from_current_jsonl_event_stream(self):
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_4",
                        "type": "agent_message",
                        "text": "Summary from Codex",
                    },
                }
            ),
            json.dumps({"type": "turn.completed"}),
        ]
        result = parse_codex("\n".join(lines), "", 0)
        assert result == "Summary from Codex"

    def test_error_on_nonzero_exit(self):
        result = parse_codex("", "command not found", 1)
        assert "error" in result.lower()


class TestParseGemini:
    def test_extracts_response_from_json(self):
        data = {"response": "Hello from Gemini"}
        stdout = json.dumps(data)
        result = parse_gemini(stdout, "", 0)
        assert "Hello from Gemini" in result

    def test_fallback_on_plain_text(self):
        result = parse_gemini("just text", "", 0)
        assert result == "just text"

    def test_error_on_nonzero_exit(self):
        result = parse_gemini("", "auth failed", 1)
        assert "error" in result.lower()


class TestParseClaude:
    def test_extracts_result_from_json(self):
        data = {"result": "Hello from Claude"}
        stdout = json.dumps(data)
        result = parse_claude(stdout, "", 0)
        assert "Hello from Claude" in result

    def test_fallback_on_plain_text(self):
        result = parse_claude("raw output", "", 0)
        assert result == "raw output"


class TestParseOutput:
    def test_dispatches_to_codex(self):
        lines = [json.dumps({"type": "message", "content": "test"})]
        result = parse_output("codex", "\n".join(lines), "", 0)
        assert "test" in result

    def test_dispatches_to_gemini(self):
        result = parse_output("gemini", json.dumps({"response": "test"}), "", 0)
        assert "test" in result

    def test_dispatches_to_claude(self):
        result = parse_output("claude", json.dumps({"result": "test"}), "", 0)
        assert "test" in result

    def test_unknown_client_returns_raw(self):
        result = parse_output("unknown", "raw", "", 0)
        assert result == "raw"
