import json

from clink_mcp.cli import main


class TestClinkCli:
    def test_main_accepts_tool_args_json_and_timeout(self, monkeypatch, capsys):
        captured = {}

        async def fake_execute_clink_call(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr("clink_mcp.cli.execute_clink_call", fake_execute_clink_call)

        exit_code = main(
            [
                "--tool-args-json",
                json.dumps(
                    {
                        "prompt": "Inspect this",
                        "cli_name": "claude",
                        "role": "codereviewer",
                        "file_paths": ["/tmp/a.md"],
                        "context_mode": "embed",
                    }
                ),
                "--timeout",
                "900",
            ]
        )

        out = capsys.readouterr().out
        assert exit_code == 0
        assert out == "ok\n"
        assert captured["cli_name"] == "claude"
        assert captured["role"] == "codereviewer"
        assert captured["file_paths"] == ["/tmp/a.md"]
        assert captured["context_mode"] == "embed"
        assert captured["timeout"] == 900
