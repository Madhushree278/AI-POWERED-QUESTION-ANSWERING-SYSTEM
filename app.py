import os
import uuid
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import settings, UPLOADS_DIR, BASE_DIR
from database.database import (
    init_db,
    create_document,
    get_document,
    get_document_by_hash,
    update_document_details,
    update_document_status,
    list_documents,
    delete_document,
    create_conversation,
    list_conversations,
    get_conversation,
    rename_conversation,
    delete_conversation,
    add_message,
    get_messages,
    clear_conversation_messages,
    get_setting,
    set_setting,
    get_all_settings,
    get_dashboard_stats
)
from utils.helpers import calculate_file_hash, sanitize_filename, format_bytes
from services.document_processor import DocumentProcessor
from services.vector_store import vector_store_service
from services.rag_engine import rag_engine
from services.summarizer import summarizer_service
from services.quiz_service import quiz_service
from services.flashcard_service import flashcard_service
from services.concept_map_service import concept_map_service

# Initialize Database
init_db()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Full-Featured AI-Powered Document Question Answering System"
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

processor = DocumentProcessor(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP
)

# ----------------- Request / Response Models -----------------

class AskRequest(BaseModel):
    conversation_id: Optional[str] = None
    question: str
    doc_ids: Optional[List[str]] = None
    chapter: Optional[str] = None
    style: str = "Detailed"

class SummarizeRequest(BaseModel):
    summary_type: str = "short"  # short, detailed, key_points, concepts, definitions, chapter_wise
    chapter: Optional[str] = None

class SmartSummarizeRequest(BaseModel):
    doc_ids: List[str]
    mode: str = "detailed"       # short, detailed, bullet_points, exam_notes
    length: str = "detailed"     # 5_points, 10_points, detailed
    chapter: Optional[str] = None

class ConceptMapRequest(BaseModel):
    doc_ids: List[str]
    topic: Optional[str] = None

class QuizRequest(BaseModel):
    chapter: Optional[str] = None
    num_questions: int = 5
    difficulty: str = "Medium"

class FlashcardRequest(BaseModel):
    chapter: Optional[str] = None
    num_cards: int = 8

class RenameConvRequest(BaseModel):
    title: str

class SettingsUpdateRequest(BaseModel):
    active_provider: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    openai_model: Optional[str] = None
    groq_model: Optional[str] = None

class TestProviderRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    model: Optional[str] = None

# ----------------- Document Endpoints -----------------

@app.post("/api/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """
    Multi-file upload endpoint:
    Processes each document, extracts text, detects chapters, chunks, creates embeddings & indexes into vector store.
    """
    results = []
    
    for file in files:
        safe_name = sanitize_filename(file.filename)
        ext = Path(safe_name).suffix.lower()
        
        if ext not in [".pdf", ".docx", ".txt", ".md"]:
            results.append({
                "filename": safe_name,
                "status": "error",
                "message": f"Unsupported format '{ext}'. Only PDF, DOCX, TXT, MD are supported."
            })
            continue

        temp_id = str(uuid.uuid4())
        dest_filename = f"{temp_id}_{safe_name}"
        dest_path = UPLOADS_DIR / dest_filename

        try:
            # Save file to disk
            contents = await file.read()
            if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                results.append({
                    "filename": safe_name,
                    "status": "error",
                    "message": f"File exceeds maximum size limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
                })
                continue

            with open(dest_path, "wb") as f:
                f.write(contents)

            # Deduplication check
            file_hash = calculate_file_hash(dest_path)
            existing_doc = get_document_by_hash(file_hash)
            if existing_doc:
                # Remove duplicate physical file
                if dest_path.exists():
                    dest_path.unlink()
                results.append({
                    "id": existing_doc["id"],
                    "filename": safe_name,
                    "status": "ready",
                    "message": "Document already exists and was indexed previously (deduplicated).",
                    "page_count": existing_doc["page_count"],
                    "chunk_count": existing_doc["chunk_count"],
                    "is_scanned": bool(existing_doc["is_scanned"]),
                    "chapters": existing_doc.get("chapters", []),
                    "suggested_questions": existing_doc.get("suggested_questions", [])
                })
                continue

            # Record document in DB
            doc_record = create_document(
                doc_id=temp_id,
                filename=safe_name,
                file_type=ext.lstrip('.'),
                file_size=len(contents),
                file_hash=file_hash
            )

            # Update status: extracting
            update_document_status(temp_id, "extracting")

            # Process document
            processed_data = processor.process_file(dest_path, safe_name, temp_id)

            # Update status: indexing
            update_document_status(temp_id, "indexing")

            # Index chunks in vector store
            vector_store_service.add_chunks(processed_data["chunks"])

            # Save finalized details to DB
            update_document_details(
                doc_id=temp_id,
                page_count=processed_data["page_count"],
                chunk_count=processed_data["chunk_count"],
                is_scanned=processed_data["is_scanned"],
                chapters=processed_data["chapters"],
                suggested_questions=processed_data["suggested_questions"]
            )

            results.append({
                "id": temp_id,
                "filename": safe_name,
                "file_size": format_bytes(len(contents)),
                "status": "ready",
                "page_count": processed_data["page_count"],
                "chunk_count": processed_data["chunk_count"],
                "is_scanned": processed_data["is_scanned"],
                "chapters": processed_data["chapters"],
                "suggested_questions": processed_data["suggested_questions"],
                "message": "Processed and indexed successfully."
            })

        except Exception as e:
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except Exception:
                    pass
            update_document_status(temp_id, "error", str(e))
            results.append({
                "id": temp_id,
                "filename": safe_name,
                "status": "error",
                "message": str(e)
            })

    return {"uploaded": results}

@app.get("/api/documents")
def get_documents(search: str = Query("", description="Filter documents by filename")):
    """List all uploaded documents."""
    docs = list_documents(search)
    for d in docs:
        d["file_size_formatted"] = format_bytes(d["file_size"])
    return {"documents": docs}

@app.get("/api/documents/{doc_id}")
def get_document_details(doc_id: str):
    """Retrieve details for a single document."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc["file_size_formatted"] = format_bytes(doc["file_size"])
    return doc

@app.delete("/api/documents/{doc_id}")
def delete_document_endpoint(doc_id: str):
    """Delete document from database, vector store, and disk."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 1. Delete chunks from Chroma
    vector_store_service.delete_document_chunks(doc_id)

    # 2. Delete record from SQLite
    delete_document(doc_id)

    # 3. Delete physical file from disk
    for f in UPLOADS_DIR.glob(f"{doc_id}_*"):
        try:
            f.unlink()
        except Exception:
            pass

    return {"status": "success", "message": f"Document '{doc['filename']}' deleted successfully."}

@app.get("/api/documents/{doc_id}/page/{page_num}/image")
def get_pdf_page_image(doc_id: str, page_num: int):
    """Render a PDF page as a PNG image for the integrated PDF viewer."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    matching_files = list(UPLOADS_DIR.glob(f"{doc_id}_*"))
    if not matching_files:
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    filepath = matching_files[0]
    if filepath.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Page image preview only supported for PDF documents")

    try:
        img_bytes = processor.render_pdf_page_image(filepath, page_num)
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/documents/{doc_id}/file")
def get_raw_document_file(doc_id: str):
    """Serve the raw document file (for PDF preview/download)."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    matching_files = list(UPLOADS_DIR.glob(f"{doc_id}_*"))
    if not matching_files:
        raise HTTPException(status_code=404, detail="Document file missing")

    return FileResponse(
        path=matching_files[0],
        filename=doc["filename"],
        media_type="application/pdf" if doc["file_type"] == "pdf" else "application/octet-stream"
    )

# ----------------- Question Answering (RAG) -----------------

@app.post("/api/chat/ask")
def ask_question_endpoint(req: AskRequest):
    """
    RAG Question Answering Endpoint:
    Processes query, searches vector store, retrieves source chunks, calls LLM, saves to conversation history.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Create conversation if not provided
    conv_id = req.conversation_id
    if not conv_id or not get_conversation(conv_id):
        # Generate title from first question
        title = req.question.strip()[:40] + ("..." if len(req.question.strip()) > 40 else "")
        conv = create_conversation(title=title)
        conv_id = conv["id"]

    # Retrieve chat history for query rewriting & conversational context
    history = get_messages(conv_id)

    # Execute RAG pipeline
    rag_result = rag_engine.answer_question(
        question=req.question,
        doc_ids=req.doc_ids,
        chapter=req.chapter,
        style=req.style,
        chat_history=history
    )

    # Persist User message
    user_msg = add_message(
        conversation_id=conv_id,
        role="user",
        content=req.question,
        style=req.style
    )

    # Persist Assistant message
    assistant_msg = add_message(
        conversation_id=conv_id,
        role="assistant",
        content=rag_result["answer"],
        style=req.style,
        confidence=rag_result["confidence"],
        sources=rag_result["sources"]
    )

    return {
        "conversation_id": conv_id,
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "answer": rag_result["answer"],
        "confidence": rag_result["confidence"],
        "sources": rag_result["sources"],
        "rewritten_query": rag_result.get("rewritten_query", req.question)
    }

# ----------------- Document Summarization -----------------

@app.post("/api/documents/{doc_id}/summarize")
def summarize_document_endpoint(doc_id: str, req: SummarizeRequest):
    """Summarize entire book or a selected chapter (legacy endpoint preserved)."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = summarizer_service.summarize(
        doc_id=doc_id,
        filename=doc["filename"],
        summary_type=req.summary_type,
        chapter=req.chapter
    )
    return result

@app.post("/api/summarizer/smart")
def smart_summarize_endpoint(req: SmartSummarizeRequest):
    """AI-Powered Smart Summarizer supporting single & multi-document synthesis and 4 modes."""
    if not req.doc_ids:
        raise HTTPException(status_code=400, detail="Please select at least one document.")
    result = summarizer_service.generate_smart_summary(
        doc_ids=req.doc_ids,
        mode=req.mode,
        length=req.length,
        chapter=req.chapter
    )
    return result

@app.post("/api/concept-map/generate")
def generate_concept_map_endpoint(req: ConceptMapRequest):
    """Generate an interconnected visual concept map dynamically from document content."""
    if not req.doc_ids:
        raise HTTPException(status_code=400, detail="Please select at least one document.")
    result = concept_map_service.generate_concept_map(
        doc_ids=req.doc_ids,
        focus_topic=req.topic
    )
    return result

@app.post("/api/documents/{doc_id}/quiz")
def generate_quiz_endpoint(doc_id: str, req: QuizRequest):
    """Generate multiple-choice quiz questions from a document."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = quiz_service.generate_quiz(
        doc_id=doc_id,
        filename=doc["filename"],
        chapter=req.chapter,
        num_questions=req.num_questions,
        difficulty=req.difficulty
    )
    return result

@app.post("/api/documents/{doc_id}/flashcards")
def generate_flashcards_endpoint(doc_id: str, req: FlashcardRequest):
    """Generate study flashcards from a document."""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    result = flashcard_service.generate_flashcards(
        doc_id=doc_id,
        filename=doc["filename"],
        chapter=req.chapter,
        num_cards=req.num_cards
    )
    return result

# ----------------- Conversation History -----------------

@app.get("/api/conversations")
def get_conversations():
    return {"conversations": list_conversations()}

@app.post("/api/conversations")
def new_conversation(title: str = "New Conversation"):
    conv = create_conversation(title)
    return conv

@app.get("/api/conversations/{conv_id}")
def get_conversation_endpoint(conv_id: str):
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_messages(conv_id)
    return {
        "conversation": conv,
        "messages": messages
    }

@app.patch("/api/conversations/{conv_id}")
def rename_conversation_endpoint(conv_id: str, req: RenameConvRequest):
    rename_conversation(conv_id, req.title)
    return {"status": "success", "title": req.title}

@app.delete("/api/conversations/{conv_id}")
def delete_conversation_endpoint(conv_id: str):
    delete_conversation(conv_id)
    return {"status": "success", "message": "Conversation deleted"}

@app.post("/api/conversations/{conv_id}/clear")
def clear_conversation_endpoint(conv_id: str):
    clear_conversation_messages(conv_id)
    return {"status": "success", "message": "Conversation cleared"}

# ----------------- Dashboard & Settings -----------------

@app.get("/api/dashboard/stats")
def get_stats():
    return get_dashboard_stats()

@app.get("/api/settings")
def get_settings_endpoint():
    current = get_all_settings()
    gemini_key = current.get("gemini_api_key", settings.GEMINI_API_KEY)
    openai_key = current.get("openai_api_key", settings.OPENAI_API_KEY)
    groq_key = current.get("groq_api_key", settings.GROQ_API_KEY)

    return {
        "active_provider": current.get("active_provider", settings.DEFAULT_PROVIDER),
        "has_gemini_key": bool(gemini_key),
        "has_openai_key": bool(openai_key),
        "has_groq_key": bool(groq_key),
        "gemini_key_masked": f"••••••••{gemini_key[-4:]}" if len(gemini_key) > 4 else ("configured" if gemini_key else "not set"),
        "openai_key_masked": f"••••••••{openai_key[-4:]}" if len(openai_key) > 4 else ("configured" if openai_key else "not set"),
        "groq_key_masked": f"••••••••{groq_key[-4:]}" if len(groq_key) > 4 else ("configured" if groq_key else "not set"),
        "gemini_model": current.get("gemini_model", settings.GEMINI_MODEL),
        "openai_model": current.get("openai_model", settings.OPENAI_MODEL),
        "groq_model": current.get("groq_model", settings.GROQ_MODEL),
        "default_chunk_size": settings.CHUNK_SIZE,
        "default_overlap": settings.CHUNK_OVERLAP,
        "top_k": settings.TOP_K
    }

@app.post("/api/settings")
def update_settings_endpoint(req: SettingsUpdateRequest):
    if req.active_provider:
        set_setting("active_provider", req.active_provider)
    if req.gemini_api_key is not None:
        set_setting("gemini_api_key", req.gemini_api_key.strip())
    if req.openai_api_key is not None:
        set_setting("openai_api_key", req.openai_api_key.strip())
    if req.groq_api_key is not None:
        set_setting("groq_api_key", req.groq_api_key.strip())
    if req.gemini_model:
        set_setting("gemini_model", req.gemini_model.strip())
    if req.openai_model:
        set_setting("openai_model", req.openai_model.strip())
    if req.groq_model:
        set_setting("groq_model", req.groq_model.strip())

    return {"status": "success", "message": "Settings updated successfully."}

@app.post("/api/settings/test")
def test_provider_endpoint(req: TestProviderRequest):
    """Test LLM API key and connection."""
    key = req.api_key
    if not key:
        saved_keys = {
            "gemini": get_setting("gemini_api_key", settings.GEMINI_API_KEY),
            "openai": get_setting("openai_api_key", settings.OPENAI_API_KEY),
            "groq": get_setting("groq_api_key", settings.GROQ_API_KEY),
        }
        key = saved_keys.get(req.provider, "")

    if not key:
        return {"status": "error", "message": f"No API key provided or saved for {req.provider}."}

    try:
        if req.provider == "gemini":
            from google import genai
            client = genai.Client(api_key=key)
            model = req.model or settings.GEMINI_MODEL
            res = client.models.generate_content(
                model=model,
                contents="Respond with 'Connection successful!' in 2 words."
            )
            return {"status": "success", "message": f"Gemini connection verified! Model '{model}' responded: {res.text.strip()}"}

        elif req.provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=key)
            model = req.model or settings.OPENAI_MODEL
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Respond with 'Connection successful!'"}]
            )
            return {"status": "success", "message": f"OpenAI connection verified! Response: {res.choices[0].message.content.strip()}"}

        elif req.provider == "groq":
            from groq import Groq
            client = Groq(api_key=key)
            model = req.model or settings.GROQ_MODEL
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Respond with 'Connection successful!'"}]
            )
            return {"status": "success", "message": f"Groq connection verified! Response: {res.choices[0].message.content.strip()}"}

        else:
            return {"status": "error", "message": f"Unknown provider: {req.provider}"}

    except Exception as e:
        return {"status": "error", "message": f"Connection failed: {str(e)}"}

# ----------------- Static Frontend Mount -----------------

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "DocuMind AI Backend is running. Frontend static assets will be served here."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=settings.HOST, port=settings.PORT, reload=True)
