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
    embedding_provider: str = "bge-m3"
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    bge_model: str = "BAAI/bge-m3"
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    top_k_retrieval: int = 4
    whatsapp_api_version: str = "v21.0"
    processed_events_db: Path = Path("./data/processed_events.db")
    # Deprecated: provider selection now controls live model usage.
    mock_ingest: bool = False
    # When True, skip WhatsApp Graph API calls and log outbound messages locally
    mock_whatsapp_send: bool = False
    # Deprecated: embeddings now come from bge-m3 or OpenAI.
    mock_embedding_dim: int = 1536

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
