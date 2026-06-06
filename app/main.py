import json
import sqlite3
import traceback
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.agent import answer_query
from app.config import settings
from app.rag import has_documents, ingest_knowledge
from app.whatsapp import parse_whatsapp_message, send_text_message


app = FastAPI(
    title="AGTAALY WhatsApp Agent",
    description="FastAPI service that receives WhatsApp webhooks, runs RAG against AGTAALY knowledge, and replies via WhatsApp Cloud API.",
)


@app.exception_handler(Exception)
async def log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    _log_error(f"Unhandled error on {request.method} {request.url.path}", exc)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)

PROCESSED_DB_PATH = settings.processed_events_db
PROCESSED_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(PROCESSED_DB_PATH), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_events (
            message_id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


db = _init_db()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_in(event: dict) -> None:
    timestamp = event.get("timestamp") or _now_iso()
    payload = {
        "timestamp": timestamp,
        "from": event["phone_number"],
        "text": event["text"],
    }
    print(f"[IN] {json.dumps(payload, ensure_ascii=False)}", flush=True)


def _log_out(phone_number: str, message: str) -> None:
    payload = {
        "timestamp": _now_iso(),
        "to": phone_number,
        "text": message,
    }
    print(f"[OUT] {json.dumps(payload, ensure_ascii=False)}", flush=True)


def _log_duplicate(message_id: str) -> None:
    print(f"[DUP] DUPLICATE skipped: {message_id}", flush=True)


def _log_ignored_webhook(payload: dict) -> None:
    entry_count = len(payload.get("entry") or []) if isinstance(payload.get("entry"), list) else 0
    keys = sorted(payload.keys())
    print(f"[IGN] webhook payload ignored: entries={entry_count}, keys={keys}", flush=True)


def _log_error(message: str, exc: Exception) -> None:
    print(f"[ERR] {message}: {exc}", flush=True)
    print(traceback.format_exc(), flush=True)


def is_duplicate(message_id: str) -> bool:
    try:
        db.execute("INSERT INTO processed_events (message_id) VALUES (?)", (message_id,))
        db.commit()
        return False
    except sqlite3.IntegrityError:
        return True


@app.on_event("startup")
async def startup_event() -> None:
    if settings.whatsapp_test_mode:
        print("[INIT] WhatsApp test mode enabled; skipping knowledge ingestion.", flush=True)
        return
    if not has_documents():
        try:
            ingest_knowledge()
        except Exception as exc:
            # Do not fail startup on missing OpenAI config or ingestion issues.
            _log_error("Unable to ingest knowledge at startup", exc)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "has_documents": has_documents(),
            "mock_ingest": settings.mock_ingest,
            "mock_whatsapp_send": settings.mock_whatsapp_send,
            "whatsapp_test_mode": settings.whatsapp_test_mode,
            "llm_provider": settings.llm_provider,
            "embedding_provider": settings.embedding_provider,
            "groq_model": settings.groq_model,
            "current_time": _now_iso(),
        }
    )


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Any:
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(payload: dict, background_tasks: BackgroundTasks) -> JSONResponse:
    event = parse_whatsapp_message(payload)
    if not event:
        _log_ignored_webhook(payload)
        return JSONResponse({"status": "ignored"}, status_code=200)

    _log_in(event)

    if is_duplicate(event["message_id"]):
        _log_duplicate(event["message_id"])
        return JSONResponse({"status": "duplicate"}, status_code=200)

    background_tasks.add_task(_handle_incoming_message, event)
    return JSONResponse({"status": "accepted"}, status_code=200)


async def _handle_incoming_message(event: dict) -> None:
    try:
        if settings.whatsapp_test_mode:
            answer = settings.whatsapp_test_reply
        else:
            answer = answer_query(event["text"])
        await send_text_message(event["phone_number"], answer)
        _log_out(event["phone_number"], answer)
    except Exception as exc:
        # If answering fails (OpenAI quota, ingestion error, etc.), send a
        # short fallback message so the sender can verify connectivity.
        _log_error("Failed to process WhatsApp message", exc)
        try:
            fallback_message = (
                "AGTAALY agent is temporarily unavailable. We received your message and will reply when ready."
            )
            await send_text_message(event["phone_number"], fallback_message)
            _log_out(event["phone_number"], fallback_message)
        except Exception as send_exc:
            _log_error("Also failed to send fallback message", send_exc)


@app.post("/ingest")
async def trigger_ingest() -> JSONResponse:
    ingest_knowledge()
    return JSONResponse(
        {"status": "ingested", "mock_ingest": settings.mock_ingest},
        status_code=200,
    )
