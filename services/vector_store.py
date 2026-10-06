import re
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from config import VECTOR_STORE_DIR

class VectorStoreService:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(VECTOR_STORE_DIR),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="document_chunks",
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Add document chunks to the Chroma vector store."""
        if not chunks:
            return 0

        # Process in batches of 200
        batch_size = 200
        total_added = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            ids = [c["chunk_id"] for c in batch]
            documents = [c["text"] for c in batch]
            metadatas = [
                {
                    "doc_id": c["doc_id"],
                    "filename": c["filename"],
                    "page": int(c["page"]),
                    "chapter": str(c.get("chapter", "General Content")),
                    "chunk_index": int(c["chunk_index"])
                }
                for c in batch
            ]
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            total_added += len(batch)

        return total_added

    def search(
        self,
        query: str,
        doc_ids: Optional[List[str]] = None,
        chapter: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Hybrid semantic & keyword search with document/chapter filtering.
        """
        if self.collection.count() == 0:
            return []

        # Build Chroma 'where' filter
        where_filter = None
        filters = []

        if doc_ids:
            if len(doc_ids) == 1:
                filters.append({"doc_id": doc_ids[0]})
            elif len(doc_ids) > 1:
                filters.append({"doc_id": {"$in": doc_ids}})

        if chapter and chapter != "All Chapters" and chapter != "General Content":
            filters.append({"chapter": chapter})

        if len(filters) == 1:
            where_filter = filters[0]
        elif len(filters) > 1:
            where_filter = {"$and": filters}

        # Query more candidates for re-ranking
        fetch_k = min(top_k * 3, max(20, top_k))

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=fetch_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            print(f"Error querying Chroma collection: {e}")
            return []

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0] if "distances" in results else [0.5] * len(docs)
        ids = results["ids"][0]

        # Re-score using hybrid retrieval (cosine distance + keyword matching)
        query_words = set(re.findall(r'\w+', query.lower()))
        scored_chunks = []

        for text, meta, dist, chunk_id in zip(docs, metas, distances, ids):
            # Cosine distance in Chroma: similarity = 1.0 - (dist / 2.0) or (1 - dist)
            semantic_sim = max(0.0, 1.0 - float(dist))

            # Keyword lexical overlap
            text_words = set(re.findall(r'\w+', text.lower()))
            overlap = len(query_words.intersection(text_words)) / max(len(query_words), 1)

            # Combined hybrid score (75% semantic, 25% lexical)
            hybrid_score = round((0.75 * semantic_sim) + (0.25 * overlap), 4)

            scored_chunks.append({
                "chunk_id": chunk_id,
                "doc_id": meta.get("doc_id", ""),
                "filename": meta.get("filename", ""),
                "page": int(meta.get("page", 1)),
                "chapter": meta.get("chapter", "General Content"),
                "chunk_index": int(meta.get("chunk_index", 0)),
                "text": text,
                "score": hybrid_score,
                "semantic_sim": round(semantic_sim, 4),
                "keyword_overlap": round(overlap, 4)
            })

        # Sort descending by hybrid score
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)

        return scored_chunks[:top_k]

    def delete_document_chunks(self, doc_id: str) -> bool:
        """Delete all indexed chunks for a document."""
        try:
            self.collection.delete(where={"doc_id": doc_id})
            return True
        except Exception as e:
            print(f"Error deleting chunks for {doc_id}: {e}")
            return False

    def get_document_chunks(self, doc_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        """Retrieve all chunks belonging to a document (e.g. for summarization)."""
        try:
            results = self.collection.get(
                where={"doc_id": doc_id},
                limit=limit,
                include=["documents", "metadatas"]
            )
            chunks = []
            if results and results["documents"]:
                for text, meta in zip(results["documents"], results["metadatas"]):
                    chunks.append({
                        "doc_id": meta.get("doc_id"),
                        "filename": meta.get("filename"),
                        "page": int(meta.get("page", 1)),
                        "chapter": meta.get("chapter", ""),
                        "chunk_index": int(meta.get("chunk_index", 0)),
                        "text": text
                    })
            chunks.sort(key=lambda x: (x["page"], x["chunk_index"]))
            return chunks
        except Exception as e:
            print(f"Error fetching chunks for {doc_id}: {e}")
            return []

vector_store_service = VectorStoreService()
