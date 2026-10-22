"""
Fetches and parses ChatGPT / Claude shared conversation links.

Only allowlisted share URLs are accepted (see `resolve_share_url`); arbitrary
webpages are rejected so the server never fetches user-supplied hosts.
Network I/O uses ChatPeek's `requests`-based fetchers, which are blocking —
call `import_url` from a threadpool (the import route does).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlparse

from app.parsers.base import ParsedDocument
from app.parsers.chatgpt_share_parser import ChatGPTShareParser
from app.parsers.claude_parser import ClaudeShareParser
from app.vendor.chatpeek import claude_share_id, fetch_claude_snapshot, fetch_share_page

CHATGPT_HOSTS = frozenset({"chatgpt.com", "www.chatgpt.com", "chat.openai.com"})
CHATGPT_SHARE_PREFIXES = ("/share/", "/s/")

FETCH_TIMEOUT_SECONDS = 20
FETCH_ATTEMPTS = 2
MAX_RESPONSE_CHARS = 25_000_000


@dataclass(frozen=True)
class ShareLink:
    source_type: str   # chatgpt_share | claude_share
    share_id: str
    url: str


def resolve_share_url(url: str) -> ShareLink:
    """Validate a share URL against the allowlist. Raises ValueError otherwise."""

    url = url.strip()
    claude_id = claude_share_id(url)
    if claude_id:
        return ShareLink("claude_share", claude_id, url)

    try:
        parsed = urlparse(url)
    except ValueError:
        parsed = None
    host = ((parsed.hostname if parsed else "") or "").lower().rstrip(".")
    if parsed and parsed.scheme == "https" and host in CHATGPT_HOSTS:
        path = parsed.path or ""
        if path.startswith("/c/"):
            raise ValueError(
                "This is a private ChatGPT conversation link. Use Share → Copy link "
                "to get a public https://chatgpt.com/share/... link."
            )
        for prefix in CHATGPT_SHARE_PREFIXES:
            share_id = path[len(prefix):].strip("/")
            if path.startswith(prefix) and share_id and "/" not in share_id:
                return ShareLink("chatgpt_share", share_id, url)

    raise ValueError(
        "Unsupported URL. Paste a public ChatGPT (https://chatgpt.com/share/...) "
        "or Claude (https://claude.ai/share/...) share link."
    )


def import_url(url: str) -> ParsedDocument:
    """Fetch and parse a share link (blocking).

    Raises:
        ValueError: URL not allowlisted, response too large, or no conversation found.
        ShareAccessError: The share is private, deleted, or blocked by bot protection.
        requests.RequestException: Network / HTTP failure after retries.
    """

    link = resolve_share_url(url)

    if link.source_type == "claude_share":
        body = fetch_claude_snapshot(link.url, attempts=FETCH_ATTEMPTS)
        parser: ChatGPTShareParser | ClaudeShareParser = ClaudeShareParser()
    else:
        body = fetch_share_page(link.url, timeout=FETCH_TIMEOUT_SECONDS, attempts=FETCH_ATTEMPTS)
        parser = ChatGPTShareParser()

    if len(body) > MAX_RESPONSE_CHARS:
        raise ValueError("Shared conversation is too large to import")

    parsed = parser.parse(body, link.url)
    # Hash the canonical share id so the same share pasted with different
    # query strings / trailing slashes deduplicates.
    parsed.metadata["file_hash"] = hashlib.sha256(
        f"{link.source_type}:{link.share_id}".encode()
    ).hexdigest()
    return parsed
