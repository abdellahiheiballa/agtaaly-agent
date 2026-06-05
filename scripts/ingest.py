from app.rag import ingest_knowledge
from app.config import settings


if __name__ == "__main__":
    ingest_knowledge()
    print(
        "Knowledge base ingested into ChromaDB "
        f"with {settings.embedding_provider} embeddings."
    )
