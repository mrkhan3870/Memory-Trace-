"""Tests for all ReFound parsers."""

import json
import pytest
from app.parsers.chatgpt_parser import ChatGPTParser
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.text_parser import TxtParser
from app.parsers.image_parser import ImageParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.base import ParsedDocument


class TestChatGPTParser:
    def test_parses_single_conversation(self):
        data = json.dumps({
            "title": "Test Chat",
            "mapping": {
                "node1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Hello"]},
                    }
                },
                "node2": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Hi there!"]},
                    }
                },
            },
        })
        parser = ChatGPTParser()
        result = parser.parse(data.encode(), "export.json")
        assert result.source_type == "chatgpt"
        assert "Hello" in result.raw_text
        assert "Hi there!" in result.raw_text

    def test_handles_list_of_conversations(self):
        data = json.dumps([
            {"title": "Conv A", "mapping": {}},
            {"title": "Conv B", "mapping": {}},
        ])
        parser = ChatGPTParser()
        result = parser.parse(data.encode(), "export.json")
        assert result.metadata["conversation_count"] == 2

    def test_skips_non_user_assistant_roles(self):
        data = json.dumps({
            "title": "Test",
            "mapping": {
                "n1": {
                    "message": {
                        "author": {"role": "tool"},
                        "content": {"parts": ["tool output"]},
                    }
                },
                "n2": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["user query"]},
                    }
                },
            },
        })
        parser = ChatGPTParser()
        result = parser.parse(data.encode(), "export.json")
        assert "user query" in result.raw_text
        assert "tool output" not in result.raw_text


class TestMarkdownParser:
    def test_parses_headings(self):
        md = b"# Title\n\nSome content.\n\n## Section 1\n\nMore content."
        parser = MarkdownParser()
        result = parser.parse(md, "test.md")
        assert result.title == "Title"
        assert len(result.sections) >= 1
        assert result.source_type == "markdown"


class TestTextParser:
    def test_parses_plain_text(self):
        parser = TxtParser()
        result = parser.parse(b"Hello world", "test.txt")
        assert result.raw_text == "Hello world"
        assert result.source_type == "txt"
        assert result.title == "test.txt"


class TestImageParser:
    def test_fallback_without_api_key(self, monkeypatch):
        from config import Settings
        monkeypatch.setattr(Settings, "gemini_api_key", "")
        parser = ImageParser()
        result = parser.parse(b"fake-image-bytes", "photo.png")
        assert "[Image: photo.png]" in result.raw_text
        assert result.source_type == "image"
        assert result.metadata["has_vision_description"] is False

    def test_detects_mime_from_extension(self, monkeypatch):
        from config import Settings
        monkeypatch.setattr(Settings, "gemini_api_key", "")
        parser = ImageParser()
        result = parser.parse(b"data", "screenshot.jpeg")
        assert result.metadata["mime_type"] == "image/jpeg"


class TestPdfParser:
    def test_requires_pymupdf(self):
        parser = PDFParser()
        try:
            import fitz
            data = fitz.open()
            page = data.new_page()
            pdf_bytes = data.tobytes()
            data.close()
            result = parser.parse(pdf_bytes, "test.pdf")
            assert result.source_type == "pdf"
            assert result.title == "test"
        except ImportError:
            result = parser.parse(b"%PDF-1.4 empty", "test.pdf")
            assert result is not None
