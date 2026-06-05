from pathlib import Path
import hashlib
import math
import re
from typing import Dict, Iterable, List

import chromadb

from app.config import settings


class LocalEmbeddingFunction:
    def __init__(self, dimension: int):
        self.dimension = dimension

    def _tokens(self, text: str) -> List[str]:
        return re.findall(r"[A-Za-z0-9_À-ÿ\u0600-\u06FF]+", text.lower())

    def _embedding(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokens(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def embed_documents(self, documents, **_kwargs):
        return [self._embedding(document) for document in documents]

    def embed_query(self, query=None, **kwargs):
        if query is None and "input" in kwargs:
            query = kwargs.get("input")
        if isinstance(query, (list, tuple)):
            return [self._embedding(item) for item in query]
        return self._embedding(query or "")

    def __call__(self, input):
        return [self._embedding(item) for item in input]


def _split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> Iterable[str]:
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        if end == text_length:
            break
        start = max(end - chunk_overlap, start + 1)


def _get_client() -> chromadb.api.ClientAPI:
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_persist_dir))


def _get_collection() -> chromadb.api.models.Collection.Collection:
    client = _get_client()
    embedding_function = LocalEmbeddingFunction(settings.mock_embedding_dim)
    return client.create_collection(
        name="agtaaly",
        embedding_function=embedding_function,
        get_or_create=True,
    )


def has_documents() -> bool:
    try:
        collection = _get_client().get_collection(name="agtaaly")
        return collection.count() > 0
    except Exception:
        return False


def _reset_collection() -> chromadb.api.models.Collection.Collection:
    client = _get_client()
    try:
        client.delete_collection(name="agtaaly")
    except Exception:
        pass
    return _get_collection()


def load_knowledge_chunks() -> List[Dict[str, object]]:
    knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge"
    chunks: List[Dict[str, object]] = []
    text_files = sorted(knowledge_dir.glob("*.txt"))
    for file_path in text_files:
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        for chunk in _split_text(text, chunk_size=800, chunk_overlap=100):
            if chunk:
                chunks.append(
                    {
                        "id": f"{file_path.stem}-{len(chunks) + 1}",
                        "text": chunk,
                        "metadata": {"source": str(file_path)},
                    }
                )
    return chunks


def load_bot_instructions() -> str:
    instructions_path = Path(__file__).resolve().parents[1] / "knowledge" / "bot_instructions.txt"
    if not instructions_path.exists():
        return ""
    return instructions_path.read_text(encoding="utf-8").strip()


def ingest_knowledge() -> None:
    chunks = load_knowledge_chunks()
    if not chunks:
        raise FileNotFoundError(
            "Knowledge base files not found or empty in the knowledge/ directory"
        )
    collection = _reset_collection()
    add_kwargs = {
        "ids": [chunk["id"] for chunk in chunks],
        "documents": [chunk["text"] for chunk in chunks],
        "metadatas": [chunk["metadata"] for chunk in chunks],
    }
    collection.add(**add_kwargs)


def query_knowledge(question: str, k: int | None = None) -> List[Dict[str, object]]:
    collection = _get_collection()
    query_kwargs = {
        "n_results": k or settings.top_k_retrieval,
        "include": ["metadatas", "documents"],
    }
    query_kwargs["query_texts"] = [question]
    result = collection.query(**query_kwargs)
    documents = []
    for metadata, document in zip(result["metadatas"][0], result["documents"][0]):
        documents.append({"metadata": metadata or {}, "page_content": document or ""})
    return documents
