import re

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.rag import load_bot_instructions, query_knowledge


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


def _detect_language(text: str) -> str:
    lowered = text.lower()
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"
    french_markers = [
        "bonjour",
        "salut",
        "trajet",
        "voyage",
        "reserver",
        "r\u00e9server",
        "agence",
        "quand",
        "demain",
        "prix",
    ]
    if any(marker in lowered for marker in french_markers):
        return "fr"
    return "en"


def _simple_context_answer(question: str, documents: list) -> str:
    language = _detect_language(question)
    lowered = question.lower()
    context = _build_context(documents)
    route_markers = [
        "nouakchott",
        "nouadhibou",
        "atar",
        "rosso",
        "kaedi",
        "kiffa",
        "nema",
        "zouerate",
        "selibaby",
        "to ",
        "->",
        "\u2192",
    ]

    if "agtaaly" in lowered and any(
        word in lowered for word in ["what", "quoi", "c'est", "\u0634\u0646\u0648", "\u0645\u0627"]
    ):
        if language == "fr":
            return (
                "Agtaaly facilite les trajets entre les villes :)\n"
                "Je peux chercher, comparer les prix et reserver pour toi.\n"
                "Tu veux voyager ou gerer une agence ?"
            )
        if language == "ar":
            return (
                "تُسهّل Agtaaly السفر بين المدن :)\n"
                "يمكنني البحث عن الرحلات، مقارنة الأسعار، وإتمام الحجز لك.\n"
                "هل ترغب في السفر أم في إدارة وكالة؟"
            )
        return (
            "Agtaaly makes intercity travel easier :)\n"
            "I can search trips, compare prices, and book for you.\n"
            "Are you traveling or managing an agency?"
        )

    if any(word in lowered for word in ["seat", "seats", "si\u00e8ge", "places", "\u0645\u0642\u0627\u0639\u062f"]):
        if language == "fr":
            return "Bien sur :) C'est pour quel trajet ?"
        if language == "ar":
            return "بكل تأكيد :) لأي رحلة تريد تحديث المقاعد؟"
        return "Sure :) Which trip is it for?"

    if any(
        word in lowered
        for word in ["booking", "reservation", "r\u00e9servation", "problem", "probl\u00e8me", "\u0645\u0634\u0643\u0644\u0629"]
    ):
        if language == "fr":
            return "Ah desole pour ca. Dis-moi ce qui ne va pas et je te le corrige."
        if language == "ar":
            return "أعتذر عن ذلك. أخبرني بالمشكلة وسأعمل على حلّها لك."
        return "Ah sorry about that. Tell me what's wrong and I'll fix it for you."

    if any(
        word in lowered
        for word in [
            "trip",
            "travel",
            "trajet",
            "voyager",
            "route",
            "\u0633\u0641\u0631",
            "\u0631\u062d\u0644\u0629",
        ]
    ):
        if language == "fr":
            return "Parfait :) Tu voyages quand ?"
        if language == "ar":
            return "حسنًا :) متى ترغب في السفر؟"
        return "Got it :) When do you want to travel?"

    if any(marker in lowered for marker in route_markers):
        if language == "fr":
            return "Parfait :) Tu voyages quand ?"
        if language == "ar":
            return "حسنًا :) متى ترغب في السفر؟"
        return "Got it :) When do you want to travel?"

    phone_numbers = re.findall(r"\b\d{8}\b", context)
    if any(
        word in lowered
        for word in ["phone", "number", "contact", "telephone", "t\u00e9l\u00e9phone", "\u0631\u0642\u0645"]
    ):
        if phone_numbers:
            numbers = ", ".join(dict.fromkeys(phone_numbers[:3]))
            if language == "fr":
                return f"Bien sur :) Tu peux contacter Agtaaly ici : {numbers}"
            if language == "ar":
                return f"بكل تأكيد :) أرقام Agtaaly هي: {numbers}"
            return f"Sure :) You can contact Agtaaly here: {numbers}"

    if language == "fr":
        return "Je m'en occupe :) Dis-moi juste ce que tu veux faire sur Agtaaly."
    if language == "ar":
        return "حسنًا :) أخبرني فقط بما تريد إنجازه على Agtaaly."
    return "I'll handle it :) Tell me what you want to do on Agtaaly."


def create_agent():
    return init_chat_model(
        model=settings.openai_model,
        model_provider="openai",
        temperature=0.2,
    )


def answer_query(question: str) -> str:
    documents = query_knowledge(question)
    if settings.mock_ingest:
        context_hint = _build_context(documents)
        return (
            "Mock AGTAALY reply: I received your message and I can use the knowledge base.\n"
            f"Question: {question}\n"
            f"Context preview: {context_hint[:220] if context_hint else 'no knowledge context available'}"
        )

    system_prompt = _build_system_prompt()
    context_text = _build_context(documents)
    llm = create_agent()
    messages = [
        SystemMessage(content=system_prompt),
        SystemMessage(
            content=(
                "Use the following knowledge base context to answer the user. "
                "If the context does not contain the answer, ask one concise follow-up question or say you do not know."
                f"\n\nContext:\n{context_text}"
            )
        ),
        HumanMessage(content=question),
    ]
    try:
        response = llm.invoke(messages)
        return getattr(response, "content", str(response)).strip()
    except Exception:
        return _simple_context_answer(question, documents)
