import os
from typing import List
import numpy as np

class EmbeddingService:
    def __init__(self):
        self._local_fn = None

    def _get_local_embedding_function(self):
        if self._local_fn is None:
            from chromadb.utils import embedding_functions
            self._local_fn = embedding_functions.DefaultEmbeddingFunction()
        return self._local_fn

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using local ONNX model.
        Returns a list of float vectors.
        """
        if not texts:
            return []
        
        # Clean texts
        cleaned_texts = [t.replace("\n", " ").strip() or "empty" for t in texts]
        
        # Use fast, local, dependency-free embedding function
        fn = self._get_local_embedding_function()
        raw_embeddings = fn(cleaned_texts)
        
        # Convert numpy arrays to standard python float lists
        result = []
        for emb in raw_embeddings:
            if isinstance(emb, np.ndarray):
                result.append(emb.tolist())
            else:
                result.append(list(emb))
        return result

    def get_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for a single search query."""
        results = self.get_embeddings([query])
        return results[0] if results else []

embedding_service = EmbeddingService()
