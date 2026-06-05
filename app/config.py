from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "local_verify_token"
    chroma_persist_dir: Path = Path("./chroma_db")
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    top_k_retrieval: int = 4
    whatsapp_api_version: str = "v21.0"
    processed_events_db: Path = Path("./data/processed_events.db")
    # When True, skip the OpenAI chat call and return a local test reply.
    mock_ingest: bool = False
    # When True, skip WhatsApp Graph API calls and log outbound messages locally
    mock_whatsapp_send: bool = False
    # Dimension for the local deterministic retrieval embeddings.
    mock_embedding_dim: int = 1536

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
