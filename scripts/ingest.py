from app.rag import ingest_knowledge
from app.config import settings


if __name__ == "__main__":
    ingest_knowledge()
    if settings.mock_ingest:
        print("Knowledge base ingested into ChromaDB with mock embeddings.")
    else:
        print("Knowledge base ingested into ChromaDB.")
