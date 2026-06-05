import sqlite3
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from app.agent import answer_query
from app.config import settings
from app.rag import has_documents, ingest_knowledge
from app.whatsapp import parse_whatsapp_message, send_text_message


app = FastAPI(
    title="AGTAALY WhatsApp Agent",
    description="FastAPI service that receives WhatsApp webhooks, runs RAG against AGTAALY knowledge, and replies via WhatsApp Cloud API.",
)

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


def is_duplicate(message_id: str) -> bool:
    try:
        db.execute("INSERT INTO processed_events (message_id) VALUES (?)", (message_id,))
        db.commit()
        return False
    except sqlite3.IntegrityError:
        return True


@app.on_event("startup")
async def startup_event() -> None:
    if not has_documents():
        try:
            ingest_knowledge()
        except Exception as exc:
            # Do not fail startup on missing OpenAI config or ingestion issues.
            print(f"Warning: unable to ingest knowledge at startup: {exc}")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


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
        return JSONResponse({"status": "ignored"}, status_code=200)

    if is_duplicate(event["message_id"]):
        return JSONResponse({"status": "duplicate"}, status_code=200)

    background_tasks.add_task(_handle_incoming_message, event)
    return JSONResponse({"status": "accepted"}, status_code=200)


async def _handle_incoming_message(event: dict) -> None:
    try:
        answer = answer_query(event["text"])
        await send_text_message(event["phone_number"], answer)
    except Exception as exc:
        # If answering fails (OpenAI quota, ingestion error, etc.), send a
        # short fallback message so the sender can verify connectivity.
        print(f"Failed to process WhatsApp message: {exc}")
        try:
            await send_text_message(
                event["phone_number"],
                "AGTAALY agent is temporarily unavailable. We received your message and will reply when ready.",
            )
        except Exception as send_exc:
            print(f"Also failed to send fallback message: {send_exc}")


@app.post("/ingest")
async def trigger_ingest() -> JSONResponse:
    ingest_knowledge()
    return JSONResponse(
        {"status": "ingested", "mock_ingest": settings.mock_ingest},
        status_code=200,
    )
