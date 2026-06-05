from pathlib import Path
from typing import Dict, Iterable, List

import chromadb
from langchain_openai.embeddings import OpenAIEmbeddings

from app.config import settings


# Adapter to make LangChain OpenAIEmbeddings compatible with Chroma's embedding
# function API. Chroma may call `embed_query(input=...)` or `__call__(input=...)`,
# so the adapter supports both positional and keyword arguments.
class LangchainEmbeddingAdapter:
    def __init__(self, lc_embeddings: OpenAIEmbeddings):
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


def _get_collection() -> chromadb.api.models.Collection.Collection:
    client = _get_client()
    if settings.mock_ingest:
        embedding_function = MockEmbeddingFunction(settings.mock_embedding_dim)
    else:
        embeddings = OpenAIEmbeddings(model=settings.openai_embedding_model)
        embedding_function = LangchainEmbeddingAdapter(embeddings)
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


def ingest_knowledge() -> None:
    chunks = load_knowledge_chunks()
    if not chunks:
        raise FileNotFoundError(
            "Knowledge base files not found or empty in the knowledge/ directory"
        )
    collection = _get_collection()
    try:
        # If the collection is empty, some Chroma versions raise an error
        # when calling delete() without filters. Ignore that case.
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


def query_knowledge(question: str, k: int | None = None) -> List[Dict[str, object]]:
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
