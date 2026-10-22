"""
Shared helpers that turn a ChatPeek `Chat` into a ParsedDocument.

Used by the ChatGPT share, Claude share and Claude JSON export parsers so all
conversation sources produce the same section layout:
  heading: "USER — first words of the turn"
  text:    "[USER]\\n<turn text>"
Consecutive replies from the same speaker are merged into one section.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.parsers.base import ParsedDocument
from app.vendor.chatpeek import Chat

_HEADING_SNIPPET_LEN = 60


def chat_sections(chat: Chat, heading_prefix: str = "") -> list[dict]:
    """Group a chat's replies into speaker sections."""

    sections: list[dict] = []
    speaker: str | None = None
    parts: list[str] = []

    def flush() -> None:
        if speaker and parts:
            label = speaker.upper()
            sections.append({
                "heading": f"{heading_prefix}{label} — {_truncate(parts[0])}",
                "text": f"[{label}]\n" + "\n\n".join(parts),
            })

    for reply in chat.replies:
        text = reply.statement.strip()
        if not text:
            continue
        name = reply.author_name or reply.type.value
        if name != speaker:
            flush()
            speaker, parts = name, []
        parts.append(text)
    flush()
    return sections


def sections_to_text(title: str, sections: Iterable[dict]) -> str:
    return "\n\n".join([f"=== {title} ===", *(s["text"] for s in sections)])


def chat_to_document(chat: Chat, source_type: str, url: str, default_title: str) -> ParsedDocument:
    """Build a ParsedDocument from a single shared conversation.

    Raises ValueError when the chat has no readable messages, so callers never
    index an empty or junk document.
    """

    sections = chat_sections(chat)
    if not sections:
        raise ValueError("The shared conversation contains no readable messages")

    title = chat.title or default_title
    return ParsedDocument(
        title=title,
        raw_text=sections_to_text(title, sections),
        source_type=source_type,
        sections=sections,
        metadata={
            "url": url,
            "share_id": chat.share_id,
            "model": chat.ai_model,
            "message_count": len(chat.replies),
            "method": "chatpeek",
        },
    )


def _truncate(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= _HEADING_SNIPPET_LEN:
        return clean
    return clean[: _HEADING_SNIPPET_LEN - 1] + "…"
