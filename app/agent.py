from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.rag import ProviderConfigError, load_bot_instructions, query_knowledge


def _normalized_provider(value: str, allowed: set[str], env_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ProviderConfigError(f"{env_name} must be one of: {allowed_values}.")
    return normalized


def _llm_provider() -> str:
    return _normalized_provider(settings.llm_provider, {"groq", "openai"}, "LLM_PROVIDER")


def _build_system_prompt() -> str:
    instructions = load_bot_instructions()
    base_prompt = (
        "You are a friendly and efficient customer support agent for Agtaaly.\n"
        "You assist travelers and transport agencies.\n"
        "Speak like a real human on WhatsApp.\n"
        "Keep replies short, natural, calm, and proactive.\n"
        "Always reply in the same language as the user. If the user mixes languages, use the dominant one.\n"
        "If the user writes in Arabic, always reply in Formal/Classical Arabic only. Do not use dialect, slang, or colloquial Arabic.\n"
        "If the language is unclear, ask: 'Tu preferes francais, \u0627\u0644\u0639\u0631\u0628\u064a\u0629 ou English ?'\n"
        "Do not mention systems, APIs, backend, or internal implementation.\n"
        "Stay within Agtaaly services and prioritize action over explanation.\n"
        "If the answer is not in the knowledge base, say you do not know and ask only for the missing info needed to continue."
    )
    if instructions:
        return f"{base_prompt}\n\nAdditional operator instructions:\n{instructions}"
    return base_prompt


def _build_context(documents: list) -> str:
    return "\n\n".join(
        f"Source: {(doc.get('metadata') or {}).get('source', 'unknown')}\n{(doc.get('page_content') or '').strip()}"
        for doc in documents
    )


def create_agent():
    provider = _llm_provider()
    if provider == "groq":
        if not settings.groq_api_key:
            raise ProviderConfigError("GROQ_API_KEY is required when LLM_PROVIDER=groq.")
        return ChatOpenAI(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            temperature=0.2,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise ProviderConfigError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.2,
        )
    raise ProviderConfigError(f"Unsupported LLM provider: {provider}")


def answer_query(question: str) -> str:
    documents = query_knowledge(question)
    context_text = _build_context(documents)
    messages = [
        SystemMessage(content=_build_system_prompt()),
        SystemMessage(
            content=(
                "Use the following AGTAALY knowledge base context to answer the user. "
                "Answer only from this context. If the context does not contain the answer, "
                "ask one concise follow-up question or say you do not know."
                f"\n\nContext:\n{context_text}"
            )
        ),
        HumanMessage(content=question),
    ]
    response = create_agent().invoke(messages)
    return getattr(response, "content", str(response)).strip()
