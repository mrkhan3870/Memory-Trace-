# ReFound — Explained Simply

## The idea in one sentence
ReFound is your **personal search engine for things you already figured out**: you feed it your old
ChatGPT/Claude chats, notes and documents, then ask a question and it finds the relevant bits and
writes you an answer, showing exactly where each piece came from.

Everything runs **on your own computer**. The only thing that talks to the internet is the AI that writes
the final answer (Google Gemini), and that part is optional.

## What it should do when it's finished
| Feature | What it means for the user |
|---|---|
| Import | Drop in ChatGPT/Claude exports, share links, Markdown, text, PDFs or images |
| Semantic search | Search by *meaning*, not exact words ("that bug with the database lock" finds the right chat) |
| Memory Assistant | An AI reads the best matches and writes one clear answer |
| Source citations | Every answer shows which document it came from |
| Similar Problem Detector | "You asked something like this before, here's what you found then" |
| 100% local | Your data stays in a local database on your machine |

## How it works (the pipeline)
Think of it like a librarian:

1. **Import → read the book.** Each file type has a "parser" that pulls out clean text (for chats it keeps who said what).
2. **Chunk → cut it into index cards.** Long text is split into small overlapping pieces (~500 characters).
3. **Embed → give each card a "meaning fingerprint".** A small AI model turns each card into a list of numbers;
   cards about similar things get similar numbers.
4. **Store → file the cards.** Text goes into a SQLite database; fingerprints go into FAISS, a fast "find similar numbers" index.
5. **Ask → find the closest cards.** Your question gets a fingerprint too; FAISS returns the 20 closest cards.
6. **Rerank → double-check them.** A second, more careful model re-reads those 20 and keeps the best 5.
7. **Answer → write it up.** Gemini reads the 5 cards and writes the answer, word by word, with sources.

## How importing a share link works (just rebuilt)
- **ChatGPT link** (`chatgpt.com/share/...`): we download the page and pull out the conversation data that's hidden
  inside it, in the right order, skipping system messages and dead-end branches.
- **Claude link** (`claude.ai/share/...`): the page itself is empty, so we ask Claude's public "snapshot" address for the
  conversation data directly.
- Both use a small open-source library called **ChatPeek**, copied into the project (`backend/app/vendor/`).
  If ChatGPT or Claude change their websites, updating that one file is usually the fix.
- Only real ChatGPT/Claude share links are accepted. Random websites are refused on purpose (safety).
- If something goes wrong, the user gets a clear error ("this is a private link", "link was deleted",
  "Claude blocked the request") instead of junk being saved.

## Where things stand

### ✅ Working and tested
- **ChatGPT share links**, **Claude share links**, and **Claude JSON exports**: rebuilt on ChatPeek and covered by tests.
  Known limit: Claude sometimes blocks requests from cloud servers/VPNs. It works from a normal home connection.

### 🟡 Built, but not yet checked properly
These exist in the code, but the team has reported most of them don't work, or don't work correctly.
Each one still needs testing and fixing:
- Uploading files (ChatGPT export, Markdown, TXT, PDF) and the duplicate check
- Chunking, embeddings, FAISS search, reranking
- Asking questions and getting streamed answers from Gemini
- Query history (only saved when a Gemini key is set)
- Image import (describes images with Gemini; not tested end-to-end)
- Some automated tests already fail: the API tests are set up incorrectly, and two image tests are broken.

### 🟡 Half-built
- **Settings page**: the screen exists, but the backend just says "not implemented"; settings only live in the browser.
- **Auto topic tags**: the AI function exists but is never called, and there's nowhere to save topics.
- **Memory summaries**: the AI function exists, but there's no button or API to use it.

### ❌ Not built yet
- **Similar Problem Detector**: the headline feature. There's a place in the database for it, but nothing fills it.
- **Bulk/folder import**
- **Export/backup** of your data

## What's next
1. ✅ Fix ChatGPT + Claude importing (done)
2. Go through each "built but unchecked" feature one by one: test it, fix it
3. Build the Similar Problem Detector
4. Real Settings API
5. Topics, summaries, image import check
6. Bulk import, export/backup

## Running it
- Backend: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000`
- Frontend: `cd frontend && npm install && npm run dev` → http://localhost:5173
- Tests: `cd backend && python -m pytest -q`
- Put `GEMINI_API_KEY=...` in `backend/.env` (copy `backend/.env.example`).
