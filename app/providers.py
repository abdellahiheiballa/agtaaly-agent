from langchain_openai.embeddings import OpenAIEmbeddings
from app.config import settings


class EmbeddingsProvider:
    """Centralized embeddings provider based on ai_provider setting."""

    @classmethod
    def create(cls):
        if settings.ai_provider == "local":
            from langchain_huggingface.embeddings import HuggingFaceEmbeddings

            return HuggingFaceEmbeddings(model_name=settings.bge_model)
        return OpenAIEmbeddings(model=settings.openai_embedding_model)


class LLMProvider:
    """Centralized LLM provider based on ai_provider setting."""

    @classmethod
    def create(cls):
        if settings.ai_provider == "local":
            from langchain_ollama import OllamaLLM

            return OllamaLLM(
                model=settings.ollama_model,
                base_url=settings.ollama_base_url,
            )
        from langchain.chat_models import init_chat_model

        return init_chat_model(
            model=settings.openai_model,
            model_provider="openai",
            temperature=0.2,
        )