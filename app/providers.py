from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from app.config import settings


class EmbeddingsProvider:
    @classmethod
    def create(cls):
        if settings.ai_provider != "local":
            raise RuntimeError("set AI_PROVIDER=local")
        return HuggingFaceEmbeddings(model_name=settings.bge_model)



class LLMProvider:
    @classmethod
    def create(cls):
        if settings.ai_provider != "local":
            raise RuntimeError(
                "AI_PROVIDER must be set to 'local'. Current value: "
                f"{settings.ai_provider!r}. Set AI_PROVIDER=local."
            )
        return OllamaLLM(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )
