import json
from app.whatsapp import parse_whatsapp_message

payload = {
    "object": "whatsapp_business_account",
    "entry": [{
        "changes": [{
            "value": {
                "messages": [{
                    "from": "22220265393",
                    "id": "test123",
                    "type": "text",
                    "text": {"body": "Hello from WhatsApp"}
                }]
            }
        }]
    }]
}
event = parse_whatsapp_message(payload)
print("Parsed event:", event)