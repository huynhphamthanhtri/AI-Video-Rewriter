import tempfile
from pathlib import Path

from app.services.creator_dna import load_creator_dna


class TestCreatorDNAMissingFile:
    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.md"
            assert not missing.exists()
            result = load_creator_dna(missing)
            assert result is None

    def test_nonexistent_path_does_not_raise(self) -> None:
        result = load_creator_dna(Path("z://impossible/path/that/does/not/exist.md"))
        assert result is None


class TestCreatorDNAEmptyFile:
    def test_empty_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_file = Path(tmp) / "empty.md"
            empty_file.write_text("", encoding="utf-8")
            result = load_creator_dna(empty_file)
            assert result is None

    def test_whitespace_only_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws_file = Path(tmp) / "whitespace.md"
            ws_file.write_text("   \n\n  \n  ", encoding="utf-8")
            result = load_creator_dna(ws_file)
            assert result is None


class TestCreatorDNAContent:
    def test_nonempty_file_returns_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content.md"
            content_file.write_text("Đây là Creator DNA test", encoding="utf-8")
            result = load_creator_dna(content_file)
            assert result == "Đây là Creator DNA test"

    def test_multiline_content_returned_stripped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "multi.md"
            content_file.write_text("\n  Dòng 1\n  Dòng 2\n  ", encoding="utf-8")
            result = load_creator_dna(content_file)
            assert result == "Dòng 1\n  Dòng 2"
            assert len(result) > 0

    def test_unicode_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "unicode.md"
            content_file.write_text("Tiếng Việt: ắ, ễ, ớ, à, ỳ, ỷ, ử, ẫ", encoding="utf-8")
            result = load_creator_dna(content_file)
            assert "Tiếng Việt" in result
            assert "ắ" in result

    def test_large_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "large.md"
            text = "# Heading\n\n" + "\n".join(f"Line {i}" for i in range(500))
            content_file.write_text(text, encoding="utf-8")
            result = load_creator_dna(content_file)
            assert result
            assert "Line 499" in result
