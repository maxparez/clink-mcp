from pathlib import Path

import pytest

from clink_mcp.context import build_context_section


class TestBuildContextSection:
    def test_embed_mode_includes_file_contents_with_line_numbers(self, tmp_path: Path):
        source = tmp_path / "demo.py"
        source.write_text("def add(a, b):\n    return a + b\n")

        result = build_context_section(
            file_paths=[str(source)],
            context_mode="embed",
            max_file_bytes=200,
            max_total_bytes=500,
        )

        assert "Context files:" in result
        assert "demo.py" in result
        assert "1 | def add(a, b):" in result

    def test_paths_mode_does_not_embed_contents(self, tmp_path: Path):
        source = tmp_path / "demo.py"
        source.write_text("print('x')\n")

        result = build_context_section(
            file_paths=[str(source)],
            context_mode="paths",
            max_file_bytes=200,
            max_total_bytes=500,
        )

        assert "demo.py" in result
        assert "print('x')" not in result
        assert "contents not included" in result.lower()

    def test_embed_mode_marks_truncation(self, tmp_path: Path):
        source = tmp_path / "big.py"
        source.write_text("x = 1\n" * 1000)

        result = build_context_section(
            file_paths=[str(source)],
            context_mode="embed",
            max_file_bytes=40,
            max_total_bytes=80,
        )

        assert "truncated" in result.lower()

    def test_embed_mode_reports_missing_file(self):
        result = build_context_section(
            file_paths=["/tmp/does-not-exist.py"],
            context_mode="embed",
            max_file_bytes=200,
            max_total_bytes=500,
        )

        assert "does-not-exist.py" in result
        assert "missing" in result.lower()

    def test_auto_mode_skips_unreadable_entries_and_reports_reason(
        self, tmp_path: Path
    ):
        source = tmp_path / "binary.bin"
        source.write_bytes(b"\x00\x01\x02\x03")

        result = build_context_section(
            file_paths=[str(source)],
            context_mode="auto",
            max_file_bytes=200,
            max_total_bytes=500,
        )

        assert "binary.bin" in result
        assert "skipped" in result.lower()

    def test_invalid_context_mode_raises_value_error(self):
        with pytest.raises(ValueError):
            build_context_section(
                file_paths=["/tmp/x.py"],
                context_mode="bogus",
                max_file_bytes=200,
                max_total_bytes=500,
            )
