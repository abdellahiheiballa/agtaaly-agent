from app.rag import ingest_knowledge, _get_collection_name
from app.config import settings


if __name__ == "__main__":
    collection_name = ingest_knowledge()
    if settings.mock_ingest:
        print(f"Knowledge base ingested into ChromaDB collection '{collection_name}' with mock embeddings.")
    else:
        print(f"Knowledge base ingested into ChromaDB collection '{collection_name}'.")
