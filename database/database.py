import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Enable WAL mode for high concurrency
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    # Documents table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        file_hash TEXT NOT NULL,
        page_count INTEGER DEFAULT 1,
        chunk_count INTEGER DEFAULT 0,
        is_scanned INTEGER DEFAULT 0,
        chapters_json TEXT DEFAULT '[]',
        suggested_questions_json TEXT DEFAULT '[]',
        status TEXT DEFAULT 'uploading',
        error_message TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    """)
    
    # Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    
    # Messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        style TEXT DEFAULT 'Detailed',
        confidence TEXT DEFAULT 'High',
        sources_json TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
    );
    """)
    
    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    
    conn.commit()
    conn.close()

# ----------------- Document CRUD -----------------

def create_document(doc_id: str, filename: str, file_type: str, file_size: int, file_hash: str) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO documents (id, filename, file_type, file_size, file_hash, created_at, status)
    VALUES (?, ?, ?, ?, ?, ?, 'uploading')
    """, (doc_id, filename, file_type, file_size, file_hash, now))
    conn.commit()
    conn.close()
    return get_document(doc_id)

def get_document_by_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE file_hash = ? AND status = 'ready' LIMIT 1", (file_hash,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_document_status(doc_id: str, status: str, error_message: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET status = ?, error_message = ? WHERE id = ?", (status, error_message, doc_id))
    conn.commit()
    conn.close()

def update_document_details(
    doc_id: str, 
    page_count: int, 
    chunk_count: int, 
    is_scanned: bool, 
    chapters: List[Dict[str, Any]], 
    suggested_questions: List[str]
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE documents 
    SET page_count = ?, chunk_count = ?, is_scanned = ?, chapters_json = ?, suggested_questions_json = ?, status = 'ready'
    WHERE id = ?
    """, (
        page_count,
        chunk_count,
        1 if is_scanned else 0,
        json.dumps(chapters),
        json.dumps(suggested_questions),
        doc_id
    ))
    conn.commit()
    conn.close()

def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['chapters'] = json.loads(d.get('chapters_json') or '[]')
        d['suggested_questions'] = json.loads(d.get('suggested_questions_json') or '[]')
        return d
    return None

def list_documents(search: str = "") -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if search:
        cursor.execute("SELECT * FROM documents WHERE filename LIKE ? ORDER BY created_at DESC", (f"%{search}%",))
    else:
        cursor.execute("SELECT * FROM documents ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d['chapters'] = json.loads(d.get('chapters_json') or '[]')
        d['suggested_questions'] = json.loads(d.get('suggested_questions_json') or '[]')
        result.append(d)
    return result

def delete_document(doc_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

# ----------------- Conversation CRUD -----------------

def create_conversation(title: str = "New Conversation") -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    conv_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cursor.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)", (conv_id, title, now, now))
    conn.commit()
    conn.close()
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

def list_conversations() -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def rename_conversation(conv_id: str, new_title: str):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (new_title, now, conv_id))
    conn.commit()
    conn.close()

def delete_conversation(conv_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()

# ----------------- Message CRUD -----------------

def add_message(
    conversation_id: str, 
    role: str, 
    content: str, 
    style: str = "Detailed", 
    confidence: str = "High", 
    sources: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    sources_json = json.dumps(sources or [])
    
    cursor.execute("""
    INSERT INTO messages (id, conversation_id, role, content, style, confidence, sources_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (msg_id, conversation_id, role, content, style, confidence, sources_json, now))
    
    # Update conversation's updated_at
    cursor.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
    
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "style": style,
        "confidence": confidence,
        "sources": sources or [],
        "created_at": now
    }

def get_messages(conversation_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['sources'] = json.loads(d.get('sources_json') or '[]')
        results.append(d)
    return results

def clear_conversation_messages(conversation_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    conn.commit()
    conn.close()

# ----------------- Settings & Stats -----------------

def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()
    conn.close()

def get_all_settings() -> Dict[str, str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM app_settings")
    rows = cursor.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def get_dashboard_stats() -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(page_count), 0), COALESCE(SUM(chunk_count), 0) FROM documents WHERE status = 'ready'")
    doc_count, page_count, chunk_count = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'")
    questions_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM conversations")
    conversations_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        "documents_count": doc_count,
        "pages_processed": page_count,
        "chunks_indexed": chunk_count,
        "questions_asked": questions_count,
        "conversations_count": conversations_count
    }
