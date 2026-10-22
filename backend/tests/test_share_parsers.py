"""Tests for ChatGPT/Claude conversation parsers, the share URL fetcher and /import-url."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

from app.parsers import detect_source_type
from app.parsers import url_fetcher
from app.parsers.chatgpt_share_parser import ChatGPTShareParser
from app.parsers.claude_parser import ClaudeJsonParser, ClaudeShareParser
from app.parsers.url_fetcher import import_url, resolve_share_url
from app.vendor.chatpeek import ShareAccessError
from main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_URL = "https://claude.ai/share/0f8e6a52-1c2b-4d3e-9f40-5a6b7c8d9e0f"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def http_error(status: int, headers: dict | None = None) -> requests.HTTPError:
    response = MagicMock(status_code=status, headers=headers or {})
    return requests.HTTPError(response=response)


class TestChatGPTShareParser:
    @pytest.mark.parametrize("name", ["chatgpt_share_modern.html", "chatgpt_share_legacy.html"])
    def test_parses_conversation_in_order(self, name):
        doc = ChatGPTShareParser().parse(fixture(name), "https://chatgpt.com/share/x")
        assert doc.title == "FAISS index tuning"
        assert doc.source_type == "chatgpt_share"
        assert doc.metadata["model"] == "gpt-4o"
        assert doc.metadata["url"] == "https://chatgpt.com/share/x"
        text = doc.raw_text
        order = ["pick nlist", "4·√N", "And nprobe?", "nprobe = 8"]
        positions = [text.index(s) for s in order]
        assert positions == sorted(positions)
        assert [s["text"].split("\n")[0] for s in doc.sections] == ["[USER]", "[ASSISTANT]"] * 2

    @pytest.mark.parametrize("name", ["chatgpt_share_modern.html", "chatgpt_share_legacy.html"])
    def test_skips_system_tool_calls_and_dead_branches(self, name):
        text = ChatGPTShareParser().parse(fixture(name)).raw_text
        assert "You are ChatGPT" not in text
        assert "print(1)" not in text
        assert "STALE BRANCH ANSWER" not in text

    def test_fails_loudly_on_page_without_conversation(self):
        html = "<html><head><title>ChatGPT</title></head><body><main>Log in</main></body></html>"
        with pytest.raises(ValueError, match="No conversation found"):
            ChatGPTShareParser().parse(html)

    def test_fails_loudly_on_empty_conversation(self):
        next_data = {"props": {"pageProps": {"serverResponse": {"data": {"linear_conversation": []}}}}}
        html = f'<script id="__NEXT_DATA__">{json.dumps(next_data)}</script>'
        with pytest.raises(ValueError, match="no readable messages"):
            ChatGPTShareParser().parse(html)


class TestClaudeShareParser:
    def test_parses_snapshot(self):
        doc = ClaudeShareParser().parse(fixture("claude_snapshot.json"), CLAUDE_URL)
        assert doc.title == "Debugging a FastAPI lifespan"
        assert doc.source_type == "claude_share"
        text = doc.raw_text
        # Sorted by index, not list order.
        assert text.index("encoder missing") < text.index("TestClient only runs") < text.index("fixed it")
        assert "AttributeError: encoder" in text      # attachment extracted_content
        assert "with TestClient(app) as client" in text  # artifact source
        assert "PRIVATE REASONING" not in text

    def test_rejects_non_snapshot_body(self):
        with pytest.raises(ValueError):
            ClaudeShareParser().parse("<html>Just a moment...</html>")
        with pytest.raises(ValueError):
            ClaudeShareParser().parse(json.dumps({"uuid": "x"}))

    def test_rejects_snapshot_without_messages(self):
        with pytest.raises(ValueError, match="no readable messages"):
            ClaudeShareParser().parse(json.dumps({"chat_messages": []}))


class TestClaudeJsonParser:
    def test_parses_export_with_null_text_and_content_blocks(self):
        doc = ClaudeJsonParser().parse(fixture("claude_export.json").encode(), "conversations.json")
        assert doc.source_type == "claude"
        assert doc.title == "conversations.json"
        assert doc.metadata["conversation_count"] == 2  # empty chat skipped
        assert "What does 'a mean" in doc.raw_text      # from content[] when text is null
        assert "lifetime parameter" in doc.raw_text     # from text when content is []
        assert "PRAGMA journal_mode=WAL" in doc.raw_text
        assert doc.sections[0]["heading"].startswith("[Rust lifetimes] USER")

    def test_single_conversation_uses_its_name(self):
        data = {"name": "My Claude Chat", "chat_messages": [
            {"sender": "human", "text": "Explain transformers"},
            {"sender": "assistant", "text": "Transformers are a neural network architecture..."},
        ]}
        doc = ClaudeJsonParser().parse(json.dumps(data).encode(), "x.json")
        assert doc.title == "My Claude Chat"
        assert doc.sections[0]["heading"] == "USER — Explain transformers"

    def test_groups_consecutive_same_sender(self):
        data = {"name": "T", "chat_messages": [
            {"sender": "human", "text": "Part 1"},
            {"sender": "human", "text": "Part 2"},
            {"sender": "assistant", "text": "Reply"},
        ]}
        doc = ClaudeJsonParser().parse(json.dumps(data).encode(), "t.json")
        assert len(doc.sections) == 2
        assert "Part 1\n\nPart 2" in doc.sections[0]["text"]

    @pytest.mark.parametrize("payload", [
        [],
        [{"name": "A", "chat_messages": []}],
        {"name": "A", "chat_messages": [{"sender": "human", "text": None}]},
        {"something": "else"},
        ["not a dict"],
    ])
    def test_rejects_empty_or_unrecognised(self, payload):
        with pytest.raises(ValueError):
            ClaudeJsonParser().parse(json.dumps(payload).encode(), "x.json")

    def test_rejects_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            ClaudeJsonParser().parse(b"{nope", "x.json")

    def test_detects_claude_export_type(self):
        raw = fixture("claude_export.json").encode()
        assert detect_source_type("conversations.json", raw) == "claude"
        assert detect_source_type("weird.json", b'["x"]') == "chatgpt"


class TestResolveShareUrl:
    @pytest.mark.parametrize("url,source,share_id", [
        ("https://chatgpt.com/share/abc-123", "chatgpt_share", "abc-123"),
        ("https://chatgpt.com/share/abc-123/?utm=x", "chatgpt_share", "abc-123"),
        ("https://chat.openai.com/share/xyz", "chatgpt_share", "xyz"),
        ("https://chatgpt.com/s/post_1", "chatgpt_share", "post_1"),
        (CLAUDE_URL, "claude_share", "0f8e6a52-1c2b-4d3e-9f40-5a6b7c8d9e0f"),
        ("  " + CLAUDE_URL.upper().replace("HTTPS://CLAUDE.AI/SHARE", "https://claude.ai/share") + "/ ",
         "claude_share", "0f8e6a52-1c2b-4d3e-9f40-5a6b7c8d9e0f"),
    ])
    def test_accepts_share_links(self, url, source, share_id):
        link = resolve_share_url(url)
        assert (link.source_type, link.share_id) == (source, share_id)

    @pytest.mark.parametrize("url", [
        "https://example.com/article",
        "https://evilchatgpt.com/share/abc",
        "https://chatgpt.com.evil.com/share/abc",
        "http://chatgpt.com/share/abc",
        "https://chatgpt.com/share/",
        "https://chatgpt.com/share/a/b",
        "https://chatgpt.com/",
        "https://claude.ai/share/not-a-uuid",
        "https://claude.ai/chat/0f8e6a52-1c2b-4d3e-9f40-5a6b7c8d9e0f",
        "file:///etc/passwd",
        "not a url",
    ])
    def test_rejects_everything_else(self, url):
        with pytest.raises(ValueError, match="Unsupported URL"):
            resolve_share_url(url)

    def test_private_chatgpt_link_has_specific_message(self):
        with pytest.raises(ValueError, match="private ChatGPT conversation"):
            resolve_share_url("https://chatgpt.com/c/abc")


class TestImportUrl:
    def test_chatgpt_share(self, monkeypatch):
        calls = []
        monkeypatch.setattr(url_fetcher, "fetch_share_page",
                            lambda url, **kw: calls.append(url) or fixture("chatgpt_share_modern.html"))
        doc = import_url("https://chatgpt.com/share/abc?x=1")
        assert calls == ["https://chatgpt.com/share/abc?x=1"]
        assert doc.source_type == "chatgpt_share"
        assert doc.metadata["file_hash"] == import_url("https://chatgpt.com/share/abc/").metadata["file_hash"]

    def test_claude_share_uses_snapshot_api(self, monkeypatch):
        monkeypatch.setattr(url_fetcher, "fetch_claude_snapshot",
                            lambda url, **kw: fixture("claude_snapshot.json"))
        monkeypatch.setattr(url_fetcher, "fetch_share_page", lambda *a, **kw: pytest.fail("HTML fetched"))
        doc = import_url(CLAUDE_URL)
        assert doc.source_type == "claude_share"
        assert doc.title == "Debugging a FastAPI lifespan"

    def test_does_not_fetch_disallowed_urls(self, monkeypatch):
        monkeypatch.setattr(url_fetcher, "fetch_share_page", lambda *a, **kw: pytest.fail("fetched"))
        with pytest.raises(ValueError):
            import_url("http://169.254.169.254/latest/meta-data")

    def test_rejects_oversized_response(self, monkeypatch):
        monkeypatch.setattr(url_fetcher, "MAX_RESPONSE_CHARS", 10)
        monkeypatch.setattr(url_fetcher, "fetch_share_page", lambda *a, **kw: "x" * 11)
        with pytest.raises(ValueError, match="too large"):
            import_url("https://chatgpt.com/share/abc")


class TestImportUrlEndpoint:
    @pytest.fixture
    def client(self):
        return TestClient(create_app())

    def _post(self, client, url="https://chatgpt.com/share/abc"):
        return client.post("/api/documents/import-url", json={"url": url})

    def test_unsupported_url_is_422(self, client):
        response = self._post(client, "https://example.com")
        assert response.status_code == 422
        assert "Unsupported URL" in response.json()["detail"]

    @pytest.mark.parametrize("exc,status", [
        (ShareAccessError("private"), 403),
        (http_error(404), 404),
        (http_error(500), 502),
        (requests.Timeout(), 504),
        (requests.ConnectionError("down"), 502),
    ])
    def test_fetch_errors_map_to_status(self, client, monkeypatch, exc, status):
        def boom(*args, **kwargs):
            raise exc
        monkeypatch.setattr(url_fetcher, "fetch_share_page", boom)
        assert self._post(client).status_code == status

    def test_unparseable_page_is_422(self, client, monkeypatch):
        monkeypatch.setattr(url_fetcher, "fetch_share_page", lambda *a, **kw: "<html>Log in</html>")
        response = self._post(client)
        assert response.status_code == 422
        assert "No conversation found" in response.json()["detail"]
