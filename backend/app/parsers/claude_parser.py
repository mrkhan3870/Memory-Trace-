"""
Parsers for Claude conversations — JSON exports and shared links.

Both formats carry the same message shape:
  {"chat_messages": [{"sender": "human"|"assistant", "text": str|null,
                      "content": [{"type": "text", "text": ...}, ...]}], "name": ...}
so both go through ChatPeek's `parse_claude_snapshot`, which prefers
`content[]` (text, artifacts, voice notes) and falls back to `text`.

Shared links (claude.ai/share/<uuid>) are not scraped: the share page is an
empty client-rendered shell. url_fetcher fetches the public
/api/chat_snapshots/<uuid> JSON instead and hands it to ClaudeShareParser.
"""

from __future__ import annotations

import json

from app.parsers.base import BaseParser, ParsedDocument
from app.parsers.conversation import chat_sections, chat_to_document, sections_to_text
from app.vendor.chatpeek import parse_claude_snapshot


class ClaudeJsonParser(BaseParser):
    """Parses a Claude JSON export (one conversation, or a list of them)."""

    source_type = "claude"

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        try:
            data = json.loads(file_bytes.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        conversations = data if isinstance(data, list) else [data]
        conversations = [
            c for c in conversations
            if isinstance(c, dict) and isinstance(c.get("chat_messages"), list)
        ]
        if not conversations:
            raise ValueError("No Claude conversations found in file")

        multi = len(conversations) > 1
        all_sections: list[dict] = []
        all_text: list[str] = []
        titles: list[str] = []

        for conv in conversations:
            chat = parse_claude_snapshot(json.dumps(conv))
            name = chat.title or "Claude Conversation"
            sections = chat_sections(chat, heading_prefix=f"[{name}] " if multi else "")
            if not sections:
                continue
            titles.append(name)
            all_sections.extend(sections)
            all_text.append(sections_to_text(name, sections))

        if not all_sections:
            raise ValueError("Claude export contains no readable messages")

        return ParsedDocument(
            title=titles[0] if len(titles) == 1 else filename,
            raw_text="\n\n".join(all_text),
            source_type=self.source_type,
            sections=all_sections,
            metadata={"conversation_count": len(titles)},
        )


class ClaudeShareParser:
    """Parses the chat_snapshots JSON behind a claude.ai/share/<uuid> link."""

    source_type = "claude_share"

    def parse(self, snapshot_json: str, url: str = "") -> ParsedDocument:
        chat = parse_claude_snapshot(snapshot_json)
        return chat_to_document(chat, self.source_type, url, "Claude Conversation")
