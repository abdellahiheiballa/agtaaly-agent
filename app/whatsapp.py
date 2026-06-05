import httpx
from app.config import settings


WHATSAPP_BASE_URL = (
    f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
    f"{settings.whatsapp_phone_number_id}"
)


async def send_text_message(phone_number: str, message: str) -> dict:
    if settings.mock_whatsapp_send:
        print(f"Mock WhatsApp send to {phone_number}: {message}", flush=True)
        return {
            "mock": True,
            "to": phone_number,
            "message": message,
        }

    if not settings.whatsapp_token or not settings.whatsapp_phone_number_id:
        raise RuntimeError(
            "WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required unless "
            "MOCK_WHATSAPP_SEND=true."
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message},
    }
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{WHATSAPP_BASE_URL}/messages", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def parse_whatsapp_message(payload: dict) -> dict | None:
    entry = payload.get("entry")
    if not entry or not isinstance(entry, list):
        return None
    change = entry[0].get("changes")
    if not change or not isinstance(change, list):
        return None
    value = change[0].get("value", {})
    messages = value.get("messages") or []
    if not messages:
        return None
    message = messages[0]
    sender = message.get("from")
    msg_id = message.get("id")
    text = None
    if message.get("type") == "text":
        text = message.get("text", {}).get("body")
    if not sender or not msg_id or not text:
        return None
    return {
        "phone_number": sender,
        "message_id": msg_id,
        "text": text,
        "timestamp": message.get("timestamp"),
    }
