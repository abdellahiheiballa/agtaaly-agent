import json
import httpx
from app.config import settings


WHATSAPP_BASE_URL = (
    f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
    f"{settings.whatsapp_phone_number_id}"
)


def _log_send(to: str, payload: dict, response: httpx.Response | None, exc: Exception | None) -> None:
    entry = {
        "to": to,
        "url": f"{WHATSAPP_BASE_URL}/messages",
        "payload": payload,
    }
    if response is not None:
        entry["status"] = response.status_code
        entry["response_preview"] = (response.text or "")[:500]
    if exc is not None:
        entry["error"] = str(exc)
    label = "[MOCK_SEND]" if settings.mock_whatsapp_send else "[SEND]"
    print(f"{label} {json.dumps(entry, ensure_ascii=False)}", flush=True)


def _log_parse(step: str, detail: str | None = None) -> None:
    extra = f" detail={detail}" if detail else ""
    print(f"[PARSE] {step}{extra}", flush=True)


async def send_text_message(phone_number: str, message: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message},
    }

    if settings.mock_whatsapp_send:
        _log_send(phone_number, payload, None, None)
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

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    url = f"{WHATSAPP_BASE_URL}/messages"
    response = None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        _log_send(phone_number, payload, response, exc)
        raise

    _log_send(phone_number, payload, response, None)
    return result


def parse_whatsapp_message(payload: dict) -> dict | None:
    if payload.get("object") != "whatsapp_business_account":
        _log_parse("object_mismatch", repr(payload.get("object")))
        return None

    entries = payload.get("entry")
    if not entries or not isinstance(entries, list):
        _log_parse("no_entry")
        return None
    _log_parse("entry_count", str(len(entries)))

    for entry_idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _log_parse("entry_not_dict", f"idx={entry_idx}")
            continue
        changes = entry.get("changes")
        if not changes or not isinstance(changes, list):
            _log_parse("no_changes", f"entry_idx={entry_idx}")
            continue
        _log_parse("changes_count", f"entry_idx={entry_idx} count={len(changes)}")

        for change_idx, change in enumerate(changes):
            if not isinstance(change, dict):
                _log_parse("change_not_dict", f"entry_idx={entry_idx} change_idx={change_idx}")
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                _log_parse("no_value_dict", f"entry_idx={entry_idx} change_idx={change_idx}")
                continue

            messages = value.get("messages") or []
            if not messages or not isinstance(messages, list):
                _log_parse("no_messages", f"entry_idx={entry_idx} change_idx={change_idx}")
                continue
            _log_parse("messages_count", f"entry_idx={entry_idx} change_idx={change_idx} count={len(messages)}")

            for msg_idx, message in enumerate(messages):
                if not isinstance(message, dict):
                    _log_parse("message_not_dict", f"entry_idx={entry_idx} change_idx={change_idx} msg_idx={msg_idx}")
                    continue
                msg_type = message.get("type")
                sender = message.get("from")
                msg_id = message.get("id")
                _log_parse("message_candidate", f"type={msg_type} from={sender} id={msg_id}")

                if msg_type != "text":
                    _log_parse("non_text_ignored", f"type={msg_type} from={sender}")
                    continue
                text = (message.get("text") or {}).get("body")
                if not text:
                    _log_parse("no_text_body", f"from={sender}")
                    continue
                if not sender or not msg_id:
                    _log_parse("missing_sender_or_id", f"from={sender} id={msg_id}")
                    continue

                return {
                    "phone_number": sender,
                    "message_id": msg_id,
                    "text": text,
                    "timestamp": message.get("timestamp"),
                }

    return None
