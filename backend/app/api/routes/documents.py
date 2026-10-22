"""
Document import pipeline routes: file upload + URL import.
"""

import hashlib
import numpy as np
import requests

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import Document, Chunk
from app.parsers import get_parser, detect_source_type
from app.parsers.url_fetcher import import_url
from app.processors.chunker import chunk_document
from app.vendor.chatpeek import ShareAccessError

router = APIRouter()


class ImportUrlRequest(BaseModel):
    url: str


def _index_document(
    parsed,
    filename: str,
    source_type: str,
    file_hash: str,
    request: Request,
    db: Session,
):
    existing = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing:
        return {
            "status": "duplicate",
            "document_id": existing.id,
            "title": existing.title,
            "source_type": existing.source_type,
            "chunks": existing.chunk_count,
        }

    doc = Document(
        filename=filename,
        source_type=source_type,
        file_hash=file_hash,
        title=parsed.title,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        chunks = chunk_document(parsed)
        if not chunks:
            raise ValueError("No chunks produced from document")

        texts = [c.content for c in chunks]
        encoder = request.app.state.encoder
        embeddings = encoder.encode_documents(texts)

        db_chunks: list[Chunk] = []
        for chunk in chunks:
            db_chunk = Chunk(
                document_id=doc.id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                token_count=chunk.token_count,
                metadata_=chunk.metadata,
            )
            db.add(db_chunk)
            db_chunks.append(db_chunk)

        db.commit()

        faiss_index = request.app.state.faiss_index
        ntotal_before = faiss_index.total_vectors
        chunk_ids = [c.id for c in db_chunks]
        faiss_index.add(embeddings.astype(np.float32), chunk_ids)
        faiss_index.save()

        for i, db_chunk in enumerate(db_chunks):
            db_chunk.faiss_id = ntotal_before + i
        doc.chunk_count = len(db_chunks)
        doc.status = "indexed"
        db.commit()

    except Exception as e:
        doc.status = "error"
        doc.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Indexing error: {e}")

    return {
        "status": "ok",
        "document_id": doc.id,
        "title": parsed.title,
        "source_type": source_type,
        "chunks": len(db_chunks),
    }


@router.post("/import")
async def import_file(request: Request, file: UploadFile, db: Session = Depends(get_db)):
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    source_type = detect_source_type(file.filename or "unknown.txt", file_bytes)

    try:
        parser = get_parser(source_type)
        parsed = parser.parse(file_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Parse error: {e}")

    return _index_document(parsed, file.filename, source_type, file_hash, request, db)


@router.post("/import-url")
async def import_from_url(req: ImportUrlRequest, request: Request, db: Session = Depends(get_db)):
    if not req.url.strip():
        raise HTTPException(status_code=422, detail="URL cannot be empty")

    try:
        parsed = await run_in_threadpool(import_url, req.url)
    except ShareAccessError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Timed out fetching the share link")
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 404:
            raise HTTPException(status_code=404, detail="Share link not found (deleted or unshared?)")
        raise HTTPException(status_code=502, detail=f"Share host returned HTTP {status}")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

    file_hash = parsed.metadata["file_hash"]
    filename = parsed.metadata.get("url", req.url)

    return _index_document(parsed, filename, parsed.source_type, file_hash, request, db)


@router.get("/")
async def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [d.to_dict() for d in docs]


@router.delete("/{document_id}")
async def delete_document(document_id: int, request: Request, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk_ids = {c.id for c in doc.chunks}

    faiss_index = request.app.state.faiss_index
    faiss_index.remove_by_chunk_ids(chunk_ids)
    faiss_index.save()

    db.delete(doc)
    db.commit()
    return {"status": "deleted", "document_id": document_id}