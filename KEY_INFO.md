# KEY_INFO — agent context for ReFound (repo: Memory-Trace-)

Read this before starting work. Keep it current: when you make an intentional/architectural
decision or discover a gotcha, add it here in the same terse style.

## 1. What this is
- Local-first "memory retrieval": import chats/notes → chunk → embed → FAISS → rerank → Gemini answer with citations.
- Product name in code/UI: **ReFound**. Repo name: Memory-Trace-.
- Backend: FastAPI (Python 3.12+, tested on 3.13), `backend/`. Frontend: React+Vite+TS+Tailwind, `frontend/`.
- Human-facing overview: `EXPLAINER.md`. Keep both files in sync when status changes.

## 2. Layout (backend)
```
main.py                 create_app(); lifespan loads EmbeddingEncoder + FAISSIndex into app.state
config.py               pydantic-settings Settings, get_settings() is @lru_cache (restart to pick up .env changes)
app/api/routes/         documents.py (import/list/delete), query.py (stream), settings.py (stub), health.py
app/parsers/            one parser per source_type; __init__.py = PARSER_MAP, EXT_MAP, detect_source_type
app/parsers/conversation.py   Chat (ChatPeek) → ParsedDocument; shared section layout for all chat sources
app/parsers/url_fetcher.py    share-URL allowlist + fetch + parse (blocking)
app/vendor/chatpeek.py  VENDORED third-party (MIT). Do not edit. See §4.
app/processors/         cleaner.py, chunker.py (sentence-aware sliding window, chunk_size/overlap in chars)
app/embeddings/         BAAI/bge-small-en-v1.5; query gets BGE prefix (asymmetric search)
app/retrieval/index.py  FAISS IndexFlatIP + parallel _ids list (row → Chunk.id), persisted to faiss_index.{index,ids.npy}
app/reranker/           cross-encoder ms-marco-MiniLM-L-6-v2, lazy singleton
app/llm/gemini.py       GeminiClient: synthesize (stream/non-stream), describe_image, summarize_memories, generate_topics
app/database/           SQLAlchemy models Document, Chunk, QueryHistory; init_db() = create_all (no migrations run)
tests/                  pytest; fixtures/ holds synthetic share pages (see §5)
```

## 3. Data contracts
- Parser output: `ParsedDocument(title, raw_text, source_type, metadata, sections=[{"heading","text"}])`.
  Chunker iterates `sections` (falls back to raw_text); `heading` → `Chunk.metadata["section"]`.
- File parsers: `parse(file_bytes, filename)`. Share parsers: `parse(body: str, url)` (body = HTML for ChatGPT, snapshot JSON for Claude).
- Conversation section layout (all chat sources): heading `"USER — <first 60 chars>"`, text `"[USER]\n<turns joined by \n\n>"`.
  Consecutive same-speaker replies are merged. Speakers: USER / ASSISTANT (ChatGPT) / CLAUDE / TOOL.
  Multi-conversation Claude exports prefix headings with `"[<conversation name>] "`.
- Dedup: `Document.file_hash` unique. Files: sha256(bytes). Share links: sha256(f"{source_type}:{share_id}") so
  query strings / trailing slashes don't create duplicates.
- source_type values: chatgpt, chatgpt_share, claude, claude_share, markdown, txt, pdf, image.
- `.json` uploads: `_detect_json_type` → "claude" if first object has `chat_messages`, else "chatgpt".

## 4. ChatGPT / Claude parsing (decisions — do not regress)
- All ChatGPT-share and Claude parsing goes through **vendored ChatPeek** (`app/vendor/chatpeek.py`).
  - Kept byte-identical to upstream below its license header, including unused CLI/`save_markdown` code,
    so updating = paste new upstream over it. ReFound glue lives in `conversation.py`, the parsers, `url_fetcher.py`.
  - Upstream repo URL/copyright holder was not recorded when vendored — fill it into the header when known.
  - Maintenance: check upstream ~weekly / whenever a share import starts failing. Share page formats change without notice.
- ChatGPT share: `parse_share_html` handles React Router stream (`streamController.enqueue`), post shares (`/s/<id>`),
  and legacy `__NEXT_DATA__`. Follows `linear_conversation` → correct order, no abandoned branches.
  System msgs, tool-addressed msgs, reasoning, tool output are excluded (ExportOptions defaults). Intentional: noise hurts retrieval.
- Claude share: page HTML is an empty shell. We fetch `https://claude.ai/api/chat_snapshots/<uuid>` JSON directly.
  Cloudflare may 403 from cloud/VPN IPs → surfaces as ShareAccessError (HTTP 403 to the client). Not fixable server-side.
- Claude JSON export: reuses `parse_claude_snapshot` per conversation (same message shape). Prefers `content[]`,
  falls back to `text`; null-safe; artifacts included, thinking excluded; empty conversations skipped.
- **Fail loudly**: no conversation found / zero readable messages → ValueError → HTTP 422. Never fall back to
  scraping page text (old behaviour indexed login-page junk).
- URL import is an **allowlist**, not a generic webpage fetcher (SSRF guard):
  `https://chatgpt.com|www.chatgpt.com|chat.openai.com` + `/share/<id>` or `/s/<id>`; `http(s)://claude.ai/share/<uuid>`.
  `/c/<id>` (private ChatGPT chat) gets a specific error. Generic webpage import was intentionally dropped
  (frontend already only accepts share links). bs4/lxml removed from deps.
- Fetch is blocking `requests` → route calls `import_url` via `run_in_threadpool`. 2 attempts, 20s timeout (ChatGPT),
  25M-char post-fetch size cap (hosts are allowlisted, so no streaming cap).
- `/import-url` error mapping: ValueError→422, ShareAccessError→403, upstream 404→404, other HTTPError→502,
  Timeout→504, other RequestException→502.

## 5. Testing
- `cd backend && python -m pytest -q` (needs requirements installed; sentence-transformers pulls torch).
- `tests/test_share_parsers.py` covers all chat parsers, URL allowlist, import_url, and /import-url error mapping
  (fetchers monkeypatched on `app.parsers.url_fetcher`; no network).
- Fixtures in `tests/fixtures/` are **synthetic** (CI/agent sandboxes can't reach chatgpt.com/claude.ai).
  Regenerate: `python -m tests.fixtures.build_fixtures`. When you capture a real saved page, add it + a test.
- Agent sandbox: outbound proxy blocks chatgpt.com and 403s claude.ai — do not try live share fetches there.
- Pre-existing failures (not caused by parser work, unfixed as of this writing):
  - `test_api.py` 8 failures: `TestClient(app)` without `with` → lifespan never runs → no tables, no `app.state.encoder`.
    Fix needs `with TestClient(...)` + test DB/encoder override (and the encoder downloads a HF model).
  - `test_parsers.py::TestImageParser` 2 failures: `monkeypatch.setattr(Settings, "gemini_api_key", "")` fails on
    pydantic v2 classes; also `get_settings()` is cached so it'd need `get_settings.cache_clear()` / patching the function.

## 6. Known issues / traps (verified by reading code unless noted)
- Settings API: `GET /api/settings` returns `{"message": "not implemented"}`; frontend Settings uses localStorage only.
- Similar Problem Detector: `QueryHistory.similar_problems` column never written; nothing computes it.
- `generate_topics` / `summarize_memories` exist in GeminiClient but nothing calls them; no topics column.
- Query history persisted only on the Gemini path; no-API-key path never saves history.
- Query route iterates a sync Gemini stream inside an async generator, and import does embedding synchronously in
  async routes → blocks the event loop under load.
- `history persisted in StreamingResponse finally` uses the request's DB session; with FastAPI ≥0.106 the dependency
  may already be closed by then (unverified — test it).
- `Chunk.faiss_id` goes stale after any delete (index is rebuilt and rows shift). Search uses the in-memory `_ids`
  map, so results are correct; just don't trust `faiss_id`.
- Default `gemini_model = "gemini-1.5-flash"` is likely retired → synthesis may fail until updated (unverified).
- Frontend `api.ts` shows raw error body (`{"detail": ...}` JSON) in toasts.
- README says `cp ../.env.example`; the file is `backend/.env.example`. `backend/test.txt` is a stray UTF-16 file.
- No Alembic migrations despite alembic in requirements; schema changes need create_all on a fresh DB or a migration.

## 7. Work order (agreed plan)
1. ✅ ChatGPT + Claude parsers via ChatPeek (this change).
2. Verify/fix each remaining "implemented" feature one by one (most are reported not working correctly):
   file import pipeline, chunking quality, embeddings, FAISS persistence/delete, rerank, query stream, history.
3. Similar Problem Detector. 4. Settings API. 5. Auto-topics. 6. Summarization endpoint. 7. Image import E2E.
8. Batch import. 9. Export/backup.
