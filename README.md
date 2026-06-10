# AGTAALY WhatsApp Agent (Phase 1)

## Architecture

- `app/main.py`: FastAPI service that handles WhatsApp webhook verification, message ingestion, duplicate event filtering, and background replies.
- `app/config.py`: Settings for OpenAI, WhatsApp Cloud API, and ChromaDB persistence.
- `app/rag.py`: Responsible for loading knowledge content from plaintext files, embedding text, and storing/retrieving it in ChromaDB.
- `app/agent.py`: Uses LangChain with OpenAI embeddings and GPT-4o to answer user questions using retrieval-augmented generation.
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

If the OpenAI API key is missing at startup, the service will still launch, but knowledge ingestion and response generation will require `OPENAI_API_KEY` to be set.

### AI Provider Configuration

Set `AI_PROVIDER=openai` (default) to use OpenAI embeddings and GPT-4o model, or `AI_PROVIDER=local` to use BGE-M3 embeddings and Ollama Qwen3 for a fully local stack.

```dotenv
# Use OpenAI (default)
AI_PROVIDER=openai

# Or use local stack (BGE-M3 + Ollama)
AI_PROVIDER=local
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3
```

When switching providers, the system automatically uses separate ChromaDB collections (`agtaaly-openai` vs `agtaaly-local`) to avoid embedding dimension mismatches. Visit `/status` to see the active collection.

### Local AI Setup

1. Install [Ollama](https://ollama.com)
2. Pull the Qwen3 model: `ollama pull qwen3`
3. Start Ollama server: `ollama serve`
4. Install local dependencies: `pip install langchain-huggingface langchain-ollama`
5. Ingest knowledge: `python -m scripts.ingest` (uses the local collection)

## Mock ingestion mode

Set `MOCK_INGEST=true` to skip OpenAI embeddings and write zero-vector mock embeddings into ChromaDB. In this mode, incoming WhatsApp messages receive a simple mock reply instead of calling the OpenAI chat model.

Set `MOCK_WHATSAPP_SEND=true` to skip WhatsApp Graph API calls and print outbound messages locally. Use both mock flags together to test that the webhook receives messages and the bot can produce replies without OpenAI or WhatsApp credentials.

PowerShell:

```powershell
$env:MOCK_INGEST = "true"
$env:MOCK_WHATSAPP_SEND = "true"
python -m scripts.ingest
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env`:

```dotenv
MOCK_INGEST=true
MOCK_EMBEDDING_DIM=1536
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

When `MOCK_INGEST=true`, `/ingest` returns `"mock_ingest": true`.

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

- This is a Phase 1 proof-of-concept.
- Replace the placeholder knowledge content in `knowledge/` with actual AGTAALY bus route, ticketing, and customer service information.
