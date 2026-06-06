#!/usr/bin/env python
"""
Test script to send a WhatsApp message via the AGTAALY agent
"""
import asyncio
import sys
from app.whatsapp import send_text_message
from app.config import settings


async def test_send_message(phone_number: str, message: str):
    """Send a test message to a WhatsApp number"""
    print(f"Sending message to {phone_number}...")
    print(f"Message: {message}")
    print(f"MOCK_WHATSAPP_SEND: {settings.mock_whatsapp_send}")
    print()
    
    try:
        result = await send_text_message(phone_number, message)
        print("✅ Message sent successfully!")
        print(f"Response: {result}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_send_message.py <phone_number> [message]")
        print("Example: python test_send_message.py +201001234567 'Hello from AGTAALY'")
        sys.exit(1)
    
    phone = sys.argv[1]
    msg = sys.argv[2] if len(sys.argv) > 2 else "Hello from AGTAALY Agent! 🚀"
    
    asyncio.run(test_send_message(phone, msg))
