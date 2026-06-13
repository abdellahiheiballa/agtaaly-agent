from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    bge_model: str = "BAAI/bge-m3"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3"
    ai_provider: str = "openai"
    top_k_retrieval: int = 4
    whatsapp_api_version: str = "v22.0"
    processed_events_db: Path = Path("./data/processed_events.db")
    mock_ingest: bool = False
    mock_whatsapp_send: bool = False
    whatsapp_test_mode: bool = False
    whatsapp_test_reply: str = "AGTAALY test reply: WhatsApp connection is working."
    mock_embedding_dim: int = 1536

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()