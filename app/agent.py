from langchain.chat_models import init_chat_model

from app.config import settings
from app.rag import query_knowledge


def _build_prompt(question: str, documents: list) -> str:
    system_prompt = (
        "You are AGTAALY's helpful assistant for bus travel in Mauritania. "
        "Use the knowledge base to answer questions about routes, schedules, reservations, payments, agencies, and customer support. "
        "If the answer is not contained in the knowledge base, be honest and say you do not know."
    )
    # documents may be dicts produced by `query_knowledge()` with keys
    # `metadata` and `page_content`.
    context_text = "\n\n".join(
        f"Source: { (doc.get('metadata') or {}).get('source', 'unknown') }\n{ (doc.get('page_content') or '').strip() }"
        for doc in documents
    )
    prompt = (
        f"{system_prompt}\n\n"
        "The following context is from the AGTAALY knowledge base. Answer the user's question using only the information in the context. "
        "If the question is unrelated to the context, say you do not know.\n\n"
        f"Context:\n{context_text}\n\n"
        f"Question: {question}\n"
        "Answer concisely:"
    )
    return prompt


def create_agent():
    return init_chat_model(
        model=settings.openai_model,
        model_provider="openai",
        temperature=0.2,
    )


def answer_query(question: str) -> str:
    documents = query_knowledge(question)
    if settings.mock_ingest:
        return (
            "Mock AGTAALY reply: your WhatsApp message was received and the bot "
            "can send responses. Live AI answers are disabled while MOCK_INGEST=true."
        )
    prompt = _build_prompt(question, documents)
    llm = create_agent()
    response = llm.invoke(prompt)
    return getattr(response, "content", str(response)).strip()
