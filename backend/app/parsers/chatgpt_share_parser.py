"""
Parser for ChatGPT shared conversation pages (chatgpt.com/share/<id>, /s/<id>).

Thin wrapper over the vendored ChatPeek parser, which understands all three
page formats ChatGPT has shipped (React Router stream, post shares, legacy
__NEXT_DATA__) and follows `linear_conversation` so turns come out in order
with no duplicate branches. Fails loudly instead of indexing page chrome.
"""

from __future__ import annotations

from app.parsers.base import ParsedDocument
from app.parsers.conversation import chat_to_document
from app.vendor.chatpeek import parse_share_html


class ChatGPTShareParser:
    source_type = "chatgpt_share"

    def parse(self, html: str, url: str = "") -> ParsedDocument:
        try:
            chat = parse_share_html(html)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(
                "No conversation found in the ChatGPT share page. The link may be "
                "invalid, or ChatGPT changed its page format (update app/vendor/chatpeek.py)."
            ) from exc
        return chat_to_document(chat, self.source_type, url, "ChatGPT Conversation")
