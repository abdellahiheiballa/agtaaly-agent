import httpx
from app.config import settings


class WhatsAppSendError(RuntimeError):
    pass


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
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise WhatsAppSendError(
                f"WhatsApp send failed with {response.status_code}: {response.text}"
            ) from exc
        return response.json()


def parse_whatsapp_message(payload: dict) -> dict | None:
    entries = payload.get("entry")
    if not entries or not isinstance(entries, list):
        return None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not changes or not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            messages = value.get("messages") or []
            if not messages or not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict):
                    continue
                sender = message.get("from")
                msg_id = message.get("id")
                text = None
                if message.get("type") == "text":
                    text = (message.get("text") or {}).get("body")
                if sender and msg_id and text:
                    return {
                        "phone_number": sender,
                        "message_id": msg_id,
                        "text": text,
                        "timestamp": message.get("timestamp"),
                    }

    return None
