"""
Knowledge Base REST API Router for NARAD V2.2.
Provides endpoints for document upload/ingestion, listing, inspection, search, and safe deletion.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.db.database import get_db
from app.services.knowledge import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


class SearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 4


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Ingest a local document (PDF, TXT, MD, DOCX) into the NARAD Knowledge Base.
    Executes the full pipeline: validation -> disk write -> text extraction -> chunking -> FTS5 indexing.
    Returns the document metadata and telemetry lifecycle trace.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename in upload.")

    try:
        file_bytes = await file.read()
    except Exception as read_err:
        raise HTTPException(status_code=400, detail=f"Failed reading uploaded file: {str(read_err)}")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    try:
        result = await knowledge_service.ingest_document(
            file_bytes=file_bytes,
            filename=file.filename,
            db=db
        )
        if result.get("status") == "failed":
            raise HTTPException(status_code=422, detail=result.get("error", "Ingestion failed."))
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Knowledge ingestion failed: {str(e)}")


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    """Retrieve all indexed documents in the local Knowledge Base."""
    docs = knowledge_service.list_documents(db=db)
    return {
        "count": len(docs),
        "documents": docs
    }


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db)):
    """Retrieve metadata and ingestion status for a specific document."""
    doc = knowledge_service.get_document(doc_id, db=db)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document with ID '{doc_id}' not found.")
    return doc


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """
    Safely delete a document, its disk file, its indexed chunks, and FTS5 entries.
    """
    success = knowledge_service.delete_document(doc_id, db=db)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document with ID '{doc_id}' not found or could not be deleted.")
    return {
        "success": True,
        "message": f"Document '{doc_id}' successfully removed from Knowledge Base."
    }


@router.post("/search")
def search_knowledge(payload: SearchRequest, db: Session = Depends(get_db)):
    """Direct search endpoint to query indexed Knowledge Base passages."""
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")
    
    return knowledge_service.search_knowledge(
        query=query,
        max_results=payload.max_results or 4,
        db=db
    )
