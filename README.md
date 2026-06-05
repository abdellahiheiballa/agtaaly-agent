# AGTAALY WhatsApp Agent (Phase 1)

## Architecture

- `app/main.py`: FastAPI service that handles WhatsApp webhook verification, message ingestion, duplicate event filtering, and background replies.
- `app/config.py`: Settings for model providers, WhatsApp Cloud API, and ChromaDB persistence.
- `app/rag.py`: Loads plaintext knowledge files, creates semantic embeddings with BGE-M3 or OpenAI, and stores/retrieves chunks in ChromaDB.
- `app/agent.py`: Combines the Agtaaly operator instructions, retrieved knowledge chunks, and the user message to answer in a WhatsApp support style.
- `app/whatsapp.py`: Parses incoming WhatsApp webhook payloads and sends outbound WhatsApp text messages using the WhatsApp Cloud API.
- `scripts/ingest.py`: A deployable script to create or refresh the local ChromaDB knowledge base.
- `knowledge/`: Place `.txt` knowledge files here for ingestion.

## Run locally

1. Create a `.env` file from `.env.example` and fill in your credentials.
2. Create and activate a virtual environment:
   - `python -m venv .venv`
   - Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
   - macOS/Linux: `source .venv/bin/activate`
3. Install dependencies:
   - `python -m pip install -r requirements.txt`
4. Ingest the knowledge base:
   - `python -m scripts.ingest`
5. Start the API:
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

Default model stack:

- `EMBEDDING_PROVIDER=bge-m3`
- `LLM_PROVIDER=groq`
- `BGE_MODEL=BAAI/bge-m3`
- `GROQ_MODEL=llama-3.1-8b-instant`

To switch back to OpenAI:

```dotenv
EMBEDDING_PROVIDER=openai
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Provider failures are not silently hidden. If BGE-M3, Groq, or OpenAI is misconfigured or unavailable, the service logs a clear error.

### Mock WhatsApp mode

Set `MOCK_WHATSAPP_SEND=true` to skip WhatsApp Graph API calls and print outbound messages locally. This is useful for testing RAG and LLM behavior without sending real WhatsApp messages.

PowerShell:

```powershell
$env:MOCK_WHATSAPP_SEND = "true"
python -m scripts.ingest
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env`:

```dotenv
MOCK_WHATSAPP_SEND=true
```

## Endpoints

- `GET /health`: health check
- `GET /webhook`: WhatsApp webhook verification
- `POST /webhook`: receive incoming WhatsApp notifications
- `POST /ingest`: manually refresh the knowledge base

## Sample cURL requests

Verify webhook:

```bash
curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=CHALLENGE"
```

Trigger knowledge ingest:

```bash
curl -X POST http://localhost:8000/ingest
```

`/ingest` returns the active embedding provider.

## WhatsApp Setup

- Configure Facebook App / WhatsApp Cloud API webhook URL to `http://<host>:8000/webhook`.
- Use `WHATSAPP_VERIFY_TOKEN` in `.env` as the verification token.
- `WHATSAPP_TOKEN` is the page access token used for sending messages.
- `WHATSAPP_PHONE_NUMBER_ID` is the WhatsApp Business phone number ID.

## Sample flow

1. WhatsApp sends a GET request to `/webhook` for verification.
2. User sends a message to the WhatsApp number.
3. WhatsApp Cloud forwards the event to `POST /webhook`.
4. The service parses the event, answers via RAG, and replies back.

## Notes

- Edit `knowledge/agtaaly_info.txt` for Agtaaly facts.
- Edit `knowledge/bot_instructions.txt` for tone, language, and operator behavior.
- Run `python -m scripts.ingest` after changing knowledge files.
