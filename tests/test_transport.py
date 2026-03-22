from pathlib import Path

import pytest

from clink_mcp.transport import write_markdown_output_file, write_markdown_prompt_file


class TestWriteMarkdownPromptFile:
    def test_writes_markdown_temp_file(self):
        path = write_markdown_prompt_file("## Prompt\n\nHello")
        prompt_path = Path(path)

        assert prompt_path.exists()
        assert prompt_path.suffix == ".md"
        assert prompt_path.read_text() == "## Prompt\n\nHello"

        prompt_path.unlink()

    def test_uses_configured_transport_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLINK_TRANSPORT_DIR", str(tmp_path))
        path = write_markdown_prompt_file("## Prompt\n\nHello")
        prompt_path = Path(path)

        assert prompt_path.parent == tmp_path
        prompt_path.unlink()


class TestWriteMarkdownOutputFile:
    def test_creates_parent_dirs_and_writes_text(self, tmp_path):
        output_path = tmp_path / "reports" / "answer.md"
        write_markdown_output_file(str(output_path), "# Answer\n\nDone")
        assert output_path.read_text() == "# Answer\n\nDone"

    def test_requires_markdown_extension(self, tmp_path):
        output_path = tmp_path / "reports" / "answer.txt"
        with pytest.raises(ValueError):
            write_markdown_output_file(str(output_path), "# Answer\n\nDone")
