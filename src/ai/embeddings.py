"""Local text embeddings (sentence-transformers all-MiniLM-L6-v2) and the ChromaDB vector store.

Embeddings are lists of numbers that capture meaning: "charged twice" and "duplicate payment" land close together.
The model runs on this computer (free, nothing is sent anywhere). ChromaDB stores the vectors on disk.
"""
from functools import lru_cache

from src.ingest.cfpb import ROOT

MODEL_NAME = "all-MiniLM-L6-v2"
CHROMA_DIR = ROOT / "data" / "chroma_db"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # heavy import: only when embeddings are really needed
    return SentenceTransformer(MODEL_NAME)


def embed(texts, batch_size=64):
    """Return normalised vectors (unit length, so cosine similarity = dot product)."""
    return _model().encode(list(texts), batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False).tolist()


def collection(name):
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"}, embedding_function=None)
