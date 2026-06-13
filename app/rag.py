from pathlib import Path
from typing import Dict, Iterable, List

import chromadb

from app.config import settings
from app.providers import EmbeddingsProvider


# Adapter to make LangChain embeddings compatible with Chroma's embedding
# function API. Chroma may call `embed_query(input=...)` or `__call__(input=...)`,
# so the adapter supports both positional and keyword arguments.
class LangchainEmbeddingAdapter:
    def __init__(self, lc_embeddings):
        self.lc = lc_embeddings

    def embed_documents(self, documents, **_kwargs):
        return list(self.lc.embed_documents(list(documents)))

    def embed_query(self, query=None, **kwargs):
        # Accept either positional or keyword 'input' parameter
        if query is None and "input" in kwargs:
            query = kwargs.get("input")
        # Chroma may pass a single string or a list of strings here.
        if isinstance(query, (list, tuple)):
            # Use embed_documents for batch queries and return list of embeddings
            return list(self.lc.embed_documents(list(query)))
        return list(self.lc.embed_query(query))

    def __call__(self, input):
        # Chroma passes either a sequence of texts or ('images', uris)
        if isinstance(input, tuple) and len(input) == 2 and input[0] == "images":
            # images handling not supported here
            raise ValueError("Image embeddings not supported by Langchain adapter")
        return [list(e) for e in self.lc.embed_documents(list(input))]


class MockEmbeddingFunction:
    def __init__(self, dimension: int):
        self.dimension = dimension

    def _embedding(self) -> List[float]:
        return [0.0] * self.dimension

    def embed_documents(self, documents, **_kwargs):
        return [self._embedding() for _ in documents]

    def embed_query(self, query=None, **kwargs):
        if query is None and "input" in kwargs:
            query = kwargs.get("input")
        if isinstance(query, (list, tuple)):
            return [self._embedding() for _ in query]
        return self._embedding()

    def __call__(self, input):
        return [self._embedding() for _ in input]


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
        start = max(end - chunk_overlap, end)


def _get_client() -> chromadb.api.ClientAPI:
    settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_persist_dir))


def _get_collection_name() -> str:
    """Return provider-specific collection name to avoid embedding dimension conflicts."""
    if settings.mock_ingest:
        return "agtaaly-mock"
    if settings.ai_provider == "local":
        return "agtaaly-local"
    return "agtaaly"


def _get_collection() -> chromadb.api.models.Collection.Collection:
    client = _get_client()
    if settings.mock_ingest:
        embedding_function = MockEmbeddingFunction(settings.mock_embedding_dim)
    else:
        embedding_function = LangchainEmbeddingAdapter(EmbeddingsProvider.create())
    return client.create_collection(
        name=_get_collection_name(),
        embedding_function=embedding_function,
        get_or_create=True,
    )


def has_documents() -> bool:
    try:
        collection = _get_client().get_collection(name=_get_collection_name())
        return collection.count() > 0
    except Exception:
        return False


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


def _query_knowledge_lexical(question: str, k: int | None = None) -> List[Dict[str, object]]:
    query_terms = {term.casefold() for term in question.split() if len(term) > 2}
    chunks = load_knowledge_chunks()
    if not query_terms:
        selected = chunks[: k or settings.top_k_retrieval]
    else:
        scored = []
        for chunk in chunks:
            text = str(chunk["text"])
            text_folded = text.casefold()
            score = sum(text_folded.count(term) for term in query_terms)
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [chunk for score, chunk in scored if score > 0][: k or settings.top_k_retrieval]
        if not selected:
            selected = chunks[: k or settings.top_k_retrieval]

    return [
        {"metadata": chunk["metadata"], "page_content": str(chunk["text"])}
        for chunk in selected
    ]


def ingest_knowledge() -> None:
    # Only ingest real embeddings when MOCK_INGEST=false.
    # When MOCK_INGEST=true, we intentionally use zero embeddings.
    chunks = load_knowledge_chunks()
    if not chunks:
        raise FileNotFoundError(
            "Knowledge base files not found or empty in the knowledge/ directory"
        )
    # Ensure we never accidentally call the embedding provider when local is not selected.
    if settings.ai_provider != "local":
        raise RuntimeError("set AI_PROVIDER=local")

    collection = _get_collection()

    try:
        collection.delete()
    except Exception:
        pass
    add_kwargs = {
        "ids": [chunk["id"] for chunk in chunks],
        "documents": [chunk["text"] for chunk in chunks],
        "metadatas": [chunk["metadata"] for chunk in chunks],
    }
    if settings.mock_ingest:
        add_kwargs["embeddings"] = [[0.0] * settings.mock_embedding_dim for _ in chunks]
    collection.add(**add_kwargs)
    return _get_collection_name()


def query_knowledge(question: str, k: int | None = None) -> List[Dict[str, object]]:
    if settings.ai_provider == "local":
        try:
            import langchain_huggingface  # noqa: F401
        except ImportError:
            return _query_knowledge_lexical(question, k)

    collection = _get_collection()
    query_kwargs = {
        "n_results": k or settings.top_k_retrieval,
        "include": ["metadatas", "documents"],
    }
    if settings.mock_ingest:
        query_kwargs["query_embeddings"] = [[0.0] * settings.mock_embedding_dim]
    else:
        query_kwargs["query_texts"] = [question]
    result = collection.query(**query_kwargs)
    documents = []
    for metadata, document in zip(result["metadatas"][0], result["documents"][0]):
        documents.append({"metadata": metadata or {}, "page_content": document or ""})
    return documents
