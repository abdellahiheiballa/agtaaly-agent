import json
import sqlite3
import traceback
from datetime import datetime, timezone
from typing import Any
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from app.config import settings
from app.whatsapp import parse_whatsapp_message, send_text_message

app = FastAPI()

import pathlib
pathlib.Path("./data").mkdir(parents=True, exist_ok=True)
db = sqlite3.connect("./data/processed_events.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS processed_events (message_id TEXT PRIMARY KEY)")
db.commit()

def is_duplicate(message_id: str) -> bool:
    try:
        db.execute("INSERT INTO processed_events (message_id) VALUES (?)", (message_id,))
        db.commit()
        return False
    except sqlite3.IntegrityError:
        return True

@app.on_event("startup")
async def startup():
    print(f"[CONFIG] token={'SET' if settings.whatsapp_token else 'MISSING'} phone_id={'SET' if settings.whatsapp_phone_number_id else 'MISSING'} mock_send={settings.mock_whatsapp_send}", flush=True)
    print("[STARTUP] Agent ready", flush=True)

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})

@app.get("/webhook")
async def verify(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Any:
    print(f"[VERIFY] mode={hub_mode} match={hub_verify_token == settings.whatsapp_verify_token}", flush=True)
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Token mismatch")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception as e:
        print(f"[ERR] Bad JSON: {e}", flush=True)
        return JSONResponse({"status": "error"}, status_code=200)
    print(f"[WEBHOOK_RAW] {json.dumps(payload)[:300]}", flush=True)
    event = parse_whatsapp_message(payload)
    if not event:
        print("[IGN] no message found in payload", flush=True)
        return JSONResponse({"status": "ignored"}, status_code=200)
    print(f"[IN] from={event['phone_number']} text={event['text']}", flush=True)
    if is_duplicate(event["message_id"]):
        print(f"[DUP] {event['message_id']}", flush=True)
        return JSONResponse({"status": "duplicate"}, status_code=200)
    background_tasks.add_task(reply, event["phone_number"])
    return JSONResponse({"status": "accepted"}, status_code=200)

async def reply(phone_number: str):
    msg = "Message received!"
    try:
        await send_text_message(phone_number, msg)
        print(f"[OUT] to={phone_number} text={msg}", flush=True)
    except Exception as e:
        print(f"[ERR] send failed: {e}", flush=True)
        print(traceback.format_exc(), flush=True)