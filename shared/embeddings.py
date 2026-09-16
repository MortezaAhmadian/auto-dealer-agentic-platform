"""
Local embedding model for the RAG layer.

Deliberately uses a local sentence-transformers model instead of a hosted
embedding API: it keeps the whole search/RAG path runnable offline and free,
while the *reasoning* agents (which need real language understanding) still
call Claude. Swap this for a hosted embedding model if you need higher
recall at scale.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, small and fast enough for CPU


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed(text: str) -> list[float]:
    vector = _model().encode(text, normalize_embeddings=True)
    return vector.tolist()
