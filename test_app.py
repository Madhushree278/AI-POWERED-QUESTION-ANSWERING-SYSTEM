from pathlib import Path
from fastapi.testclient import TestClient
from app import app
from services.document_processor import DocumentProcessor
from services.vector_store import vector_store_service
from services.rag_engine import rag_engine
from services.summarizer import summarizer_service
from services.concept_map_service import concept_map_service
from database.database import init_db, list_documents, list_conversations

client = TestClient(app)

def test_startup_and_stats():
    init_db()
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert "documents_count" in data
    assert "pages_processed" in data

def test_document_processor_pdf():
    pdf_path = Path("sample_documents/AI_and_ML_Handbook.pdf")
    assert pdf_path.exists()
    
    proc = DocumentProcessor(chunk_size=500, chunk_overlap=100)
    data = proc.process_file(pdf_path, "AI_and_ML_Handbook.pdf", "test_doc_1")
    
    assert data["page_count"] == 4
    assert data["chunk_count"] > 0
    assert len(data["chapters"]) == 4
    assert data["chapters"][0]["title"] == "Chapter 1: Introduction to Artificial Intelligence"
    assert not data["is_scanned"]
    assert len(data["suggested_questions"]) > 0

    # Test PDF page image rendering
    img_bytes = proc.render_pdf_page_image(pdf_path, 1)
    assert len(img_bytes) > 1000
    assert img_bytes[:8] == b'\x89PNG\r\n\x1a\n'

def test_document_processor_docx():
    docx_path = Path("sample_documents/AWS_Cloud_Essentials.docx")
    assert docx_path.exists()
    
    proc = DocumentProcessor(chunk_size=500, chunk_overlap=100)
    data = proc.process_file(docx_path, "AWS_Cloud_Essentials.docx", "test_doc_2")
    
    assert data["page_count"] >= 1
    assert data["chunk_count"] > 0
    assert len(data["chapters"]) >= 2
    assert "Chapter 1: Introduction to Cloud Infrastructure" in data["chapters"][0]["title"]

def test_vector_store_and_search():
    pdf_path = Path("sample_documents/AI_and_ML_Handbook.pdf")
    proc = DocumentProcessor(chunk_size=500, chunk_overlap=100)
    data = proc.process_file(pdf_path, "AI_and_ML_Handbook.pdf", "test_doc_ai")
    
    # Index
    added = vector_store_service.add_chunks(data["chunks"])
    assert added == len(data["chunks"])

    # Search
    results = vector_store_service.search("What is the Turing test?", doc_ids=["test_doc_ai"], top_k=3)
    assert len(results) > 0
    assert "Turing" in results[0]["text"]
    assert results[0]["page"] == 1

def test_rag_answering_and_grounding():
    # Direct Question
    res = rag_engine.answer_question(
        question="What is the Turing Test and when was it introduced?",
        doc_ids=["test_doc_ai"],
        style="Concise"
    )
    assert res["confidence"] in ["High", "Medium"]
    assert len(res["sources"]) > 0
    assert res["sources"][0]["page"] == 1
    assert "Turing" in res["answer"]

    # Answer Styles
    bullet_res = rag_engine.answer_question(
        question="What are the three paradigms of machine learning?",
        doc_ids=["test_doc_ai"],
        style="Bullet Points"
    )
    assert "-" in bullet_res["answer"] or "•" in bullet_res["answer"] or "Supervised" in bullet_res["answer"]

    exam_res = rag_engine.answer_question(
        question="Explain deep neural networks and backpropagation",
        doc_ids=["test_doc_ai"],
        style="Exam Answer"
    )
    assert "Definition" in exam_res["answer"] or "Principles" in exam_res["answer"] or "Neural" in exam_res["answer"]

def test_anti_hallucination_rule():
    # Question on something not in the document
    res = rag_engine.answer_question(
        question="What is the secret recipe for Kentucky Fried Chicken original chicken spice blend?",
        doc_ids=["test_doc_ai"]
    )
    assert "I couldn't find this information in the uploaded documents." in res["answer"]
    assert res["confidence"] == "Low"

def test_followup_question_query_rewriting():
    history = [
        {"role": "user", "content": "What is supervised learning?"},
        {"role": "assistant", "content": "Supervised learning algorithms are trained on labeled datasets."}
    ]
    rewritten = rag_engine.rewrite_query_for_context("Give an example", history)
    assert "supervised learning" in rewritten.lower()

def test_summarization_service():
    summary = summarizer_service.summarize(
        doc_id="test_doc_ai",
        filename="AI_and_ML_Handbook.pdf",
        summary_type="key_points"
    )
    assert len(summary["summary"]) > 50
    assert "Key" in summary["summary"] or "Summary" in summary["summary"]

def test_api_upload_and_chat_flow():
    pdf_path = Path("sample_documents/AI_and_ML_Handbook.pdf")
    
    with open(pdf_path, "rb") as f:
        res = client.post("/api/documents/upload", files={"files": ("AI_Handbook_Upload.pdf", f, "application/pdf")})
    assert res.status_code == 200
    upload_data = res.json()
    assert len(upload_data["uploaded"]) == 1
    doc_id = upload_data["uploaded"][0]["id"]
    assert upload_data["uploaded"][0]["status"] == "ready"

    # Ask a question via API
    chat_res = client.post("/api/chat/ask", json={
        "question": "What is the Transformer architecture and who introduced it?",
        "doc_ids": [doc_id],
        "style": "Detailed"
    })
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "answer" in chat_data
    assert len(chat_data["sources"]) > 0
    assert "conversation_id" in chat_data

    # Cleanup doc
    del_res = client.delete(f"/api/documents/{doc_id}")
    assert del_res.status_code == 200

def test_concept_map_generation():
    # Test service level
    res = concept_map_service.generate_concept_map(["test_doc_ai"])
    assert "nodes" in res
    assert "edges" in res
    assert len(res["nodes"]) >= 3
    assert len(res["edges"]) >= 2
    assert "main_topic" in res
    
    # Check node structure
    root_node = res["nodes"][0]
    assert "id" in root_node
    assert "label" in root_node
    assert "explanation" in root_node
    assert "source_doc" in root_node
    assert "source_page" in root_node

    # Test API endpoint
    api_res = client.post("/api/concept-map/generate", json={"doc_ids": ["test_doc_ai"]})
    assert api_res.status_code == 200
    api_data = api_res.json()
    assert len(api_data["nodes"]) >= 3
    assert len(api_data["edges"]) >= 2

    # Test error handling on empty doc_ids
    err_res = client.post("/api/concept-map/generate", json={"doc_ids": []})
    assert err_res.status_code == 400

    # Test on real uploaded document if exists
    real_docs = list_documents()
    if real_docs:
        real_id = real_docs[0]["id"]
        real_res = concept_map_service.generate_concept_map([real_id])
        assert len(real_res["nodes"]) >= 3
        assert len(real_res["edges"]) >= 2

def test_smart_summarizer_modes_and_lengths():
    # Test all 4 modes
    for mode in ["short", "detailed", "bullet_points", "exam_notes"]:
        for length in ["5_points", "10_points", "detailed"]:
            res = summarizer_service.generate_smart_summary(
                doc_ids=["test_doc_ai"],
                mode=mode,
                length=length
            )
            assert len(res["summary"]) > 40
            assert res["mode"] == mode
            assert "AI_and_ML_Handbook" in res["summary"] or "Handbook" in res["summary"] or "Summary" in res["summary"]
            # Verify citations are present
            assert ", p." in res["summary"]

    # Test API endpoint with multi-doc / single-doc
    api_res = client.post("/api/summarizer/smart", json={
        "doc_ids": ["test_doc_ai"],
        "mode": "exam_notes",
        "length": "detailed"
    })
    assert api_res.status_code == 200
    api_data = api_res.json()
    assert "summary" in api_data
    assert api_data["mode"] == "exam_notes"
    assert len(api_data["summary"]) > 50

    # Test API error handling on empty doc_ids
    err_res = client.post("/api/summarizer/smart", json={
        "doc_ids": [],
        "mode": "short",
        "length": "detailed"
    })
    assert err_res.status_code == 400

    # Test on real uploaded document if available
    real_docs = list_documents()
    if real_docs:
        real_id = real_docs[0]["id"]
        for mode in ["short", "detailed", "bullet_points", "exam_notes"]:
            real_res = summarizer_service.generate_smart_summary([real_id], mode=mode, length="5_points")
            assert len(real_res["summary"]) > 50
            assert ", p." in real_res["summary"]

if __name__ == "__main__":
    print("Running tests...")
    test_startup_and_stats()
    print("[OK] test_startup_and_stats passed")
    test_document_processor_pdf()
    print("[OK] test_document_processor_pdf passed")
    test_document_processor_docx()
    print("[OK] test_document_processor_docx passed")
    test_vector_store_and_search()
    print("[OK] test_vector_store_and_search passed")
    test_rag_answering_and_grounding()
    print("[OK] test_rag_answering_and_grounding passed")
    test_anti_hallucination_rule()
    print("[OK] test_anti_hallucination_rule passed")
    test_followup_question_query_rewriting()
    print("[OK] test_followup_question_query_rewriting passed")
    test_summarization_service()
    print("[OK] test_summarization_service passed")
    test_concept_map_generation()
    print("[OK] test_concept_map_generation passed")
    test_smart_summarizer_modes_and_lengths()
    print("[OK] test_smart_summarizer_modes_and_lengths passed")
    test_api_upload_and_chat_flow()
    print("[OK] test_api_upload_and_chat_flow passed")
    print("\nALL TESTS PASSED SUCCESSFULLY!")
