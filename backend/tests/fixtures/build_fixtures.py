"""
Regenerates the synthetic share-page fixtures in this folder.

    cd backend && python -m tests.fixtures.build_fixtures

The fixtures mirror the real formats ChatPeek parses. They are synthetic
because CI cannot reach chatgpt.com / claude.ai; drop a real saved page next to
them (e.g. chatgpt_share_real.html) and add a test when you capture one.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent


def _message(mid: str, role: str, text: str, t: float, **extra) -> dict:
    return {
        "id": mid,
        "author": {"role": role},
        "content": {"content_type": "text", "parts": [text]},
        "create_time": t,
        "recipient": "all",
        **extra,
    }


CHATGPT_DATA = {
    "title": "FAISS index tuning",
    "update_time": 1700000500.5,
    "model": {"slug": "gpt-4o"},
    "mapping": {
        "sys": {"id": "sys", "message": _message("sys", "system", "You are ChatGPT.", 1700000000.1)},
        "u1": {"id": "u1", "message": _message("u1", "user", "How do I pick nlist for an IVF index?", 1700000001.1)},
        "a1": {"id": "a1", "message": _message("a1", "assistant", "A common rule of thumb is nlist ≈ 4·√N.", 1700000002.1)},
        # Abandoned branch: present in mapping, absent from linear_conversation.
        "a1_old": {"id": "a1_old", "message": _message("a1_old", "assistant", "STALE BRANCH ANSWER", 1700000002.0)},
        "tool": {"id": "tool", "message": {
            "id": "tool", "author": {"role": "assistant"}, "recipient": "python",
            "content": {"content_type": "code", "language": "python", "text": "print(1)"},
        }},
        "u2": {"id": "u2", "message": _message("u2", "user", "And nprobe?", 1700000003.1)},
        "a2": {"id": "a2", "message": _message("a2", "assistant", "Start with nprobe = 8 and raise it until recall plateaus.", 1700000004.1)},
    },
}
CHATGPT_ORDER = ["sys", "u1", "a1", "tool", "u2", "a2"]


def _flatten(value, table: list) -> int:
    """Encode value React-Router-turbo-stream style: objects/lists/strings by index."""

    index = len(table)
    table.append(None)
    if isinstance(value, dict):
        encoded = {}
        for key, item in value.items():
            key_index = len(table)
            table.append(key)
            encoded[f"_{key_index}"] = _ref(item, table)
        table[index] = encoded
    elif isinstance(value, list):
        table[index] = [_ref(item, table) for item in value]
    else:
        table[index] = value
    return index


def _ref(value, table: list):
    # Floats / bools / None are inlined; ints would be read as references.
    if isinstance(value, (dict, list, str)):
        return _flatten(value, table)
    return value


def build_chatgpt_modern() -> str:
    data = {**CHATGPT_DATA, "linear_conversation": [{"id": i} for i in CHATGPT_ORDER]}
    root = {"loaderData": {"routes/share.$shareId.($action)": {
        "sharedConversationId": "6a1b2c3d-share",
        "serverResponse": {"data": data},
    }}}
    table: list = []
    _flatten(root, table)
    stream = json.dumps(json.dumps(table))
    return (
        "<!DOCTYPE html><html><head><title>ChatGPT - FAISS index tuning</title></head>"
        "<body><div id=\"root\"></div>"
        "<script>window.__reactRouterContext = {};</script>"
        f"<script>window.__reactRouterContext.streamController.enqueue({stream});</script>"
        "</body></html>"
    )


def build_chatgpt_legacy() -> str:
    data = {
        "conversation_id": "legacy-123",
        "title": CHATGPT_DATA["title"],
        "update_time": CHATGPT_DATA["update_time"],
        "model": CHATGPT_DATA["model"],
        "linear_conversation": [
            {"id": i, "message": CHATGPT_DATA["mapping"][i]["message"]} for i in CHATGPT_ORDER
        ],
    }
    next_data = {"props": {"pageProps": {"serverResponse": {"data": data}}}}
    return (
        "<html><head><title>FAISS index tuning</title></head><body>"
        f"<script id=\"__NEXT_DATA__\" type=\"application/json\">{json.dumps(next_data)}</script>"
        "</body></html>"
    )


CLAUDE_SNAPSHOT = {
    "uuid": "0f8e6a52-1c2b-4d3e-9f40-5a6b7c8d9e0f",
    "snapshot_name": "Debugging a FastAPI lifespan",
    "created_at": "2026-09-01T10:00:00Z",
    "updated_at": "2026-09-01T10:05:00.123456Z",
    "chat_messages": [
        # Deliberately out of order: index decides position.
        {"index": 1, "sender": "assistant", "text": "", "created_at": "2026-09-01T10:00:05Z",
         "content": [
             {"type": "thinking", "thinking": "PRIVATE REASONING"},
             {"type": "text", "text": "TestClient only runs lifespan inside a `with` block."},
             {"type": "tool_use", "name": "artifacts", "input": {
                 "command": "create", "title": "conftest.py", "type": "application/vnd.ant.code",
                 "language": "python", "content": "with TestClient(app) as client:\n    yield client",
             }},
         ]},
        {"index": 0, "sender": "human", "text": None, "created_at": "2026-09-01T10:00:00Z",
         "content": [{"type": "text", "text": "Why is app.state.encoder missing in my tests?"}],
         "attachments": [{"file_name": "error.log", "extracted_content": "AttributeError: encoder"}]},
        {"index": 2, "sender": "human", "text": "Thanks, that fixed it.", "created_at": "2026-09-01T10:01:00Z"},
    ],
}

CLAUDE_EXPORT = [
    {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "name": "Rust lifetimes",
        "chat_messages": [
            {"sender": "human", "text": None,
             "content": [{"type": "text", "text": "What does 'a mean in fn f<'a>?"}]},
            {"sender": "assistant", "text": "It names a lifetime parameter.", "content": []},
        ],
    },
    {"uuid": "22222222-2222-2222-2222-222222222222", "name": "Empty chat", "chat_messages": []},
    {
        "uuid": "33333333-3333-3333-3333-333333333333",
        "name": "SQLite WAL",
        "chat_messages": [
            {"sender": "human", "text": "Should I enable WAL mode?"},
            {"sender": "assistant", "text": None,
             "content": [{"type": "text", "text": "Yes for concurrent readers; PRAGMA journal_mode=WAL."}]},
        ],
    },
]


def main() -> None:
    (HERE / "chatgpt_share_modern.html").write_text(build_chatgpt_modern(), encoding="utf-8")
    (HERE / "chatgpt_share_legacy.html").write_text(build_chatgpt_legacy(), encoding="utf-8")
    (HERE / "claude_snapshot.json").write_text(json.dumps(CLAUDE_SNAPSHOT, indent=2), encoding="utf-8")
    (HERE / "claude_export.json").write_text(json.dumps(CLAUDE_EXPORT, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
