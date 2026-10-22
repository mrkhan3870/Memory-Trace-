from app.parsers.chatgpt_parser import ChatGPTParser
from app.parsers.chatgpt_share_parser import ChatGPTShareParser
from app.parsers.claude_parser import ClaudeJsonParser, ClaudeShareParser
from app.parsers.image_parser import ImageParser
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.text_parser import TxtParser
from app.parsers.base import BaseParser

import json

PARSER_MAP: dict[str, type[BaseParser]] = {
    "chatgpt": ChatGPTParser,
    "chatgpt_share": ChatGPTShareParser,
    "claude": ClaudeJsonParser,
    "claude_share": ClaudeShareParser,
    "image": ImageParser,
    "markdown": MarkdownParser,
    "txt": TxtParser,
    "pdf": PDFParser,
}

EXT_MAP: dict[str, str] = {
    ".json": "chatgpt",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "txt",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".bmp": "image",
}

def _detect_json_type(file_bytes: bytes) -> str:
    try:
        data = json.loads(file_bytes.decode("utf-8", errors="replace"))
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return "chatgpt"
        if data.get("chat_messages") is not None:
            return "claude"
        if data.get("mapping") is not None:
            return "chatgpt"
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return "chatgpt"


def get_parser(source_type: str) -> BaseParser:
    cls = PARSER_MAP.get(source_type)
    if not cls:
        raise ValueError(f"No parser for source_type: {source_type!r}")
    return cls()


def detect_source_type(filename: str, file_bytes: bytes | None = None) -> str:
    if "." not in filename:
        return "txt"
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    source = EXT_MAP.get(ext, "txt")
    if source == "chatgpt" and file_bytes is not None:
        return _detect_json_type(file_bytes)
    return source

