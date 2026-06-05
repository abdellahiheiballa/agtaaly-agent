from pathlib import Path
import re
from typing import Dict, Iterable, List

import chromadb
from langchain_openai.embeddings import OpenAIEmbeddings
from sentence_transformers import SentenceTransformer

from app.config import settings


class ProviderConfigError(RuntimeError):
    pass


class SentenceTransformerEmbeddingFunction:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def _embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [embedding.tolist() for embedding in embeddings]

    def embed_documents(self, documents, **_kwargs):
        return self._embed([str(document) for document in documents])

    def embed_query(self, query=None, **kwargs):
        if query is None and "input" in kwargs:
            query = kwargs.get("input")
        if isinstance(query, (list, tuple)):
            return self._embed([str(item) for item in query])
        return self._embed([str(query or "")])[0]

    def __call__(self, input):
        return self._embed([str(item) for item in input])


class OpenAIEmbeddingFunction:
    def __init__(self):
        if not settings.openai_api_key:
            raise ProviderConfigError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai."
            )
        self.embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )

    def embed_documents(self, documents, **_kwargs):
        return [list(item) for item in self.embeddings.embed_documents(list(documents))]

    def embed_query(self, query=None, **kwargs):
        if query is None and "input" in kwargs:
            query = kwargs.get("input")
        if isinstance(query, (list, tuple)):
            return [list(item) for item in self.embeddings.embed_documents(list(query))]
        return list(self.embeddings.embed_query(query or ""))

    def __call__(self, input):
        return [list(item) for item in self.embeddings.embed_documents(list(input))]


def _normalized_provider(value: str, allowed: set[str], env_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ProviderConfigError(f"{env_name} must be one of: {allowed_values}.")
    return normalized


def _embedding_provider() -> str:
    return _normalized_provider(
        settings.embedding_provider,
        {"bge-m3", "openai"},
        "EMBEDDING_PROVIDER",
    )


def _collection_name() -> str:
    provider = re.sub(r"[^a-z0-9_]+", "_", _embedding_provider().replace("-", "_"))
    return f"agtaaly_{provider}"


def _embedding_function():
    provider = _embedding_provider()
    if provider == "bge-m3":
        return SentenceTransformerEmbeddingFunction(settings.bge_model)
    if provider == "openai":
        return OpenAIEmbeddingFunction()
    raise ProviderConfigError(f"Unsupported embedding provider: {provider}")


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
    return _get_client().create_collection(
        name=_collection_name(),
        embedding_function=_embedding_function(),
        get_or_create=True,
    )


def has_documents() -> bool:
    try:
        collection = _get_client().get_collection(name=_collection_name())
        return collection.count() > 0
    except Exception:
        return False


def _reset_collection() -> chromadb.api.models.Collection.Collection:
    client = _get_client()
    try:
        client.delete_collection(name=_collection_name())
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
    collection.add(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[chunk["metadata"] for chunk in chunks],
    )


def query_knowledge(question: str, k: int | None = None) -> List[Dict[str, object]]:
    collection = _get_collection()
    result = collection.query(
        query_texts=[question],
        n_results=k or settings.top_k_retrieval,
        include=["metadatas", "documents"],
    )
    documents = []
    for metadata, document in zip(result["metadatas"][0], result["documents"][0]):
        documents.append({"metadata": metadata or {}, "page_content": document or ""})
    return documents
