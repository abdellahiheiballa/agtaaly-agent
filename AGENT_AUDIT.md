# AGTAALY Agent Audit

Generated: 2026-06-13  
Repository: `C:\Users\pc\Desktop\Agtaaly\agtaaly-agent`  
Audit scope: agent behavior, configuration, parameters, functions, libraries, environment variables, Docker setup, and usage.

## 1. Executive summary

AGTAALY Agent is a FastAPI WhatsApp bot that receives WhatsApp Cloud API webhook events, answers questions using a local RAG knowledge base, and sends replies back through the WhatsApp Cloud API.

Current implementation status:
- Main app is syntactically valid; `python -m compileall app scripts test_parse.py test_send_message.py` completed successfully.
- The current `.env` uses local AI mode: `AI_PROVIDER=local`.
- WhatsApp test mode is enabled in `.env`, so webhook messages currently receive the configured test reply instead of using RAG/LLM.
- The project has important dependency and Docker configuration gaps:
  - `requirements.txt` is missing runtime packages imported by the code: `chromadb`, `langchain-huggingface`, and `langchain-ollama`.
  - `providers.py` imports local LangChain packages unconditionally, so even OpenAI mode requires local provider packages to be installed.
  - `ingest_knowledge()` refuses to run unless `AI_PROVIDER=local`, so the documented OpenAI provider path is not actually implemented.
  - `.env` is not excluded by `.dockerignore`, so secrets can be baked into the Docker image if the image is built from the current workspace.

## 2. What the agent does

### Runtime behavior

1. FastAPI starts on port `8000`.
2. On startup, it logs masked configuration and initializes SQLite duplicate tracking.
3. If `WHATSAPP_TEST_MODE` is false, it checks whether the active ChromaDB collection has documents.
4. If no documents exist, it tries to ingest `knowledge/*.txt`.
5. WhatsApp Cloud API sends a `POST /webhook` event.
6. `app/whatsapp.py` parses only incoming text messages.
7. `app/main.py` ignores non-text or malformed webhook payloads.
8. Message IDs are tracked in SQLite to avoid duplicate replies.
9. If not a duplicate, the agent answers the message:
   - If `WHATSAPP_TEST_MODE=true`, it returns `WHATSAPP_TEST_REPLY`.
   - Otherwise it retrieves RAG context and calls the configured LLM.
10. The answer is sent back to the sender through WhatsApp Cloud API unless `MOCK_WHATSAPP_SEND=true`.

### Main flow

```text
WhatsApp Cloud API
  -> POST /webhook
  -> parse_whatsapp_message()
  -> duplicate check in data/processed_events.db
  -> BackgroundTasks._handle_incoming_message()
  -> _get_answer()
     -> RAG query from ChromaDB
     -> LLMProvider.create().invoke()
  -> send_text_message()
  -> WhatsApp Cloud API
```

## 3. Project files and responsibilities

| File | Purpose |
|---|---|
| `app/main.py:14` | FastAPI app definition, startup, health/status, webhook, ingest endpoints, duplicate handling, background message processing. |
| `app/config.py:5` | Pydantic settings class and environment variable mapping. |
| `app/whatsapp.py:32` | Sends WhatsApp text messages and parses incoming WhatsApp webhook payloads. |
| `app/agent.py:33` | Builds the RAG prompt and calls the configured LLM. |
| `app/rag.py:99` | Loads knowledge files, chunks text, manages ChromaDB collection, ingests and queries knowledge. |
| `app/providers.py:6` | Creates embedding and LLM providers. Currently only local provider is implemented. |
| `scripts/ingest.py:5` | CLI entrypoint to refresh the ChromaDB knowledge base. |
| `knowledge/agtaaly_info.txt:1` | Current plaintext knowledge source for RAG. |
| `data/processed_events.db` | SQLite database used to prevent duplicate webhook replies. |
| `Dockerfile:1` | Multi-stage Docker build for the FastAPI service. |
| `.env.example:1` | Documented environment variable template. |
| `.dockerignore:1` | Docker build context exclusions. Currently does not ignore `.env`. |
| `run_agent.ps1:3` | Local PowerShell helper that ingests knowledge then starts Uvicorn. |
| `test_parse.py:4` | Small parser test using a sample WhatsApp payload. |
| `test_send_message.py:11` | Async helper to send a WhatsApp message to a phone number. |

## 4. API endpoints

### `GET /health`

Reference: `app/main.py:131`

Purpose: Basic liveness check.

Response:

```json
{"status": "ok"}
```

### `GET /status`

Reference: `app/main.py:136`

Purpose: Shows current RAG/provider state.

Response fields:
- `has_documents`: whether the active ChromaDB collection has documents.
- `mock_ingest`: whether mock embeddings are active.
- `mock_whatsapp_send`: whether WhatsApp sends are mocked.
- `whatsapp_test_mode`: whether WhatsApp replies use the test reply.
- `ai_provider`: current AI provider.
- `collection`: active ChromaDB collection name.
- `current_time`: ISO timestamp.

### `GET /webhook`

Reference: `app/main.py:153`

Purpose: WhatsApp webhook verification.

Query parameters:
- `hub.mode`
- `hub.verify_token`
- `hub.challenge`

Behavior:
- Returns `hub.challenge` as plain text when `hub.mode=subscribe` and `hub.verify_token` matches `WHATSAPP_VERIFY_TOKEN`.
- Returns HTTP `403` otherwise.

Example:

```bash
curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=CHALLENGE"
```

### `POST /webhook`

Reference: `app/main.py:164`

Purpose: Receives WhatsApp Cloud API message notifications.

Behavior:
- Parses JSON body.
- Ignores non-message payloads with HTTP `200` and `{"status":"ignored"}`.
- Parses only incoming text messages.
- Deduplicates by `message.id`.
- Queues handling in FastAPI `BackgroundTasks`.
- Returns HTTP `200` with one of:
  - `{"status":"accepted"}`
  - `{"status":"duplicate"}`
  - `{"status":"ignored"}`
  - `{"status":"parse_error"}`

Expected WhatsApp text payload shape:

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "changes": [
        {
          "value": {
            "messages": [
              {
                "from": "22220265393",
                "id": "test123",
                "type": "text",
                "text": {"body": "Hello from WhatsApp"},
                "timestamp": "1710000000"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### `POST /ingest`

Reference: `app/main.py:205`

Purpose: Manually refreshes the ChromaDB knowledge base.

Behavior:
- Calls `ingest_knowledge()`.
- Returns:

```json
{
  "status": "ingested",
  "mock_ingest": false,
  "collection": "agtaaly-local"
}
```

Security note: `/ingest` has no authentication or authorization.

## 5. Functions and parameters

### `app/main.py`

| Function | Parameters | Purpose |
|---|---|---|
| `log_unhandled_exception(request, exc)` | `request: Request`, `exc: Exception` | Global exception handler; logs traceback and returns HTTP 500. |
| `_init_db()` | None | Creates SQLite duplicate-tracking table. |
| `is_duplicate(message_id)` | `message_id: str` | Checks and records message IDs in SQLite. |
| `_now_iso()` | None | Returns current UTC ISO timestamp. |
| `_log_in(event)` | `event: dict` | Logs incoming message phone number and text. |
| `_log_out(phone_number, message)` | `phone_number: str`, `message: str` | Logs outbound message phone number and text. |
| `_log_duplicate(message_id)` | `message_id: str` | Logs duplicate webhook skip. |
| `_log_ignored_webhook(payload)` | `payload: dict` | Summarizes ignored webhook payload. |
| `_log_error(message, exc)` | `message: str`, `exc: Exception` | Logs errors and traceback. |
| `_log_masked_config()` | None | Logs masked config values without printing secrets. |
| `startup_event()` | None | Logs config, initializes duplicate DB, and optionally ingests knowledge. |
| `_get_answer(question)` | `question: str` | Returns test reply or RAG/LLM answer. |
| `health()` | None | Health endpoint. |
| `status()` | None | Status endpoint. |
| `verify_webhook(hub_mode, hub_verify_token, hub_challenge)` | `hub_mode`, `hub_verify_token`, `hub_challenge` | WhatsApp verification endpoint. |
| `receive_webhook(request, background_tasks)` | `request: Request`, `background_tasks: BackgroundTasks` | Receives and queues incoming WhatsApp messages. |
| `_handle_incoming_message(event)` | `event: dict` | Answers message and sends WhatsApp reply; sends fallback on failure. |
| `trigger_ingest()` | None | Manual knowledge ingest endpoint. |

### `app/config.py`

| Function/class | Parameters | Purpose |
|---|---|---|
| `Settings(BaseSettings)` | Environment variables | Defines all configurable values and defaults. |
| `settings` | None | Singleton settings instance loaded from `.env`. |

### `app/whatsapp.py`

| Function | Parameters | Purpose |
|---|---|---|
| `_log_send(to, payload, response, exc)` | `to: str`, `payload: dict`, `response: httpx.Response | None`, `exc: Exception | None` | Logs mocked or real WhatsApp send attempts. |
| `_log_parse(step, detail)` | `step: str`, `detail: str | None` | Logs webhook parsing decisions. |
| `send_text_message(phone_number, message)` | `phone_number: str`, `message: str` | Sends text message via WhatsApp Cloud API or mock mode. |
| `parse_whatsapp_message(payload)` | `payload: dict` | Extracts first incoming text message from a WhatsApp webhook payload. |

### `app/agent.py`

| Function | Parameters | Purpose |
|---|---|---|
| `_build_prompt(question, documents)` | `question: str`, `documents: list` | Builds system prompt with retrieved context. |
| `create_agent()` | None | Creates the configured LLM provider. |
| `answer_query(question)` | `question: str` | Retrieves knowledge and calls LLM unless mock ingest is enabled. |

### `app/rag.py`

| Function/class | Parameters | Purpose |
|---|---|---|
| `LangchainEmbeddingAdapter(lc_embeddings)` | `lc_embeddings` | Adapts LangChain embeddings to ChromaDB API. |
| `MockEmbeddingFunction(dimension)` | `dimension: int` | Produces zero-vector embeddings for mock mode. |
| `_split_text(text, chunk_size=800, chunk_overlap=100)` | `text: str`, `chunk_size: int`, `chunk_overlap: int` | Splits knowledge text into chunks. |
| `_get_client()` | None | Creates ChromaDB persistent client. |
| `_get_collection_name()` | None | Chooses ChromaDB collection by mode/provider. |
| `_get_collection()` | None | Creates/gets ChromaDB collection with embedding function. |
| `has_documents()` | None | Checks whether active collection has documents. |
| `load_knowledge_chunks()` | None | Reads all non-empty `knowledge/*.txt` files. |
| `_query_knowledge_lexical(question, k=None)` | `question: str`, `k: int | None` | Keyword fallback retrieval. |
| `ingest_knowledge()` | None | Loads chunks, deletes collection contents, and adds documents. |
| `query_knowledge(question, k=None)` | `question: str`, `k: int | None` | Queries ChromaDB and returns retrieved context. |

### `app/providers.py`

| Class/function | Parameters | Purpose |
|---|---|---|
| `EmbeddingsProvider.create()` | None | Currently returns `HuggingFaceEmbeddings(model_name=settings.bge_model)` only when `AI_PROVIDER=local`. |
| `LLMProvider.create()` | None | Returns `OllamaLLM(model=settings.ollama_model, base_url=settings.ollama_base_url)` only when `AI_PROVIDER=local`. |

## 6. Environment variables

Source of truth: `app/config.py:5` and `.env.example:1`.

| Variable | Default | Current status | Used by | Notes |
|---|---:|---|---|---|
| `AI_PROVIDER` | `openai` | `local` | `app/config.py:18`, `app/providers.py:9`, `app/rag.py:161` | Controls provider and Chroma collection. OpenAI mode is documented but not implemented. |
| `OPENAI_API_KEY` | empty | not set in current `.env` | `app/config.py:6` | Defined but unused by current implementation. |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | not set in current `.env` | `app/config.py:14` | Defined but unused. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | not set in current `.env` | `app/providers.py:25` | In Docker, `localhost` means the container, not the host. Use host networking or `host.docker.internal` if Ollama runs on host. |
| `OLLAMA_MODEL` | `qwen3` | not set in current `.env` | `app/providers.py:24` | Must be pulled in Ollama before use. |
| `BGE_MODEL` | `BAAI/bge-m3` | not set in current `.env` | `app/providers.py:11` | Embedding model for local mode. |
| `WHATSAPP_TOKEN` | empty | set, redacted | `app/whatsapp.py:48` | Sensitive. Do not commit or bake into images. |
| `WHATSAPP_PHONE_NUMBER_ID` | empty | set, partially redacted | `app/whatsapp.py:7` | WhatsApp Business phone number ID. |
| `WHATSAPP_VERIFY_TOKEN` | `local_verify_token` | set, redacted | `app/main.py:158` | Used for WhatsApp webhook verification. |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | not set in current `.env` | `app/config.py:10`, `app/rag.py:73` | Local vector database directory. |
| `APP_HOST` | `0.0.0.0` | not set in current `.env` | `app/config.py:11` | Defined but not used by Uvicorn command. |
| `APP_PORT` | `8000` | not set in current `.env` | `app/config.py:12` | Defined but not used by Uvicorn command. |
| `TOP_K_RETRIEVAL` | `4` | not set in current `.env` | `app/rag.py:131`, `app/rag.py:188` | Number of retrieved chunks. |
| `WHATSAPP_API_VERSION` | `v22.0` | `v22.0` | `app/whatsapp.py:6` | Graph API version. |
| `MOCK_INGEST` | `false` | not set in current `.env` | `app/rag.py:79`, `app/agent.py:35` | Uses zero-vector embeddings and mock replies. |
| `MOCK_EMBEDDING_DIM` | `1536` | not set in current `.env` | `app/rag.py:26` | Dimension for mock embeddings. |
| `MOCK_WHATSAPP_SEND` | `false` | `false` | `app/whatsapp.py:40` | Skips WhatsApp API sends and logs payloads. |
| `WHATSAPP_TEST_MODE` | `false` | `true` | `app/main.py:113` | Skips startup ingest and returns fixed test reply. |
| `WHATSAPP_TEST_REPLY` | `AGTAALY test reply: WhatsApp connection is working.` | Arabic test reply configured | `app/main.py:25`, `app/main.py:126` | Current reply: `مرحباً! وصلت رسالتك. سيرد عليك فريق AGTAALY قريباً.` |

Current `.env` contains sensitive values. They are intentionally redacted in this audit file.

## 7. Libraries and dependencies

### Declared in `requirements.txt`

| Package | Version | Used for |
|---|---:|---|
| `fastapi` | `0.111.0` | Web API framework. |
| `uvicorn[standard]` | `0.30.0` | ASGI server. |
| `httpx` | `0.27.0` | Async WhatsApp Graph API HTTP client. |
| `python-dotenv` | `1.0.1` | `.env` loading support. |
| `pydantic-settings` | `2.4.0` | Settings management. |

### Imported by code but not declared in `requirements.txt`

| Package | Imported by | Issue |
|---|---|---|
| `chromadb` | `app/rag.py:4` | Required for RAG vector storage. Missing from `requirements.txt`. |
| `langchain_huggingface` | `app/providers.py:1`, `app/rag.py:182` | Required for local BGE-M3 embeddings. Missing from `requirements.txt`. |
| `langchain_ollama` | `app/providers.py:2` | Required for local Ollama LLM. Missing from `requirements.txt`. |

### Current dependency risk

The Docker build is likely to fail or the container may fail at import/runtime because `requirements.txt` does not include all packages imported by the code.

## 8. Docker audit

### Current Dockerfile

Reference: `Dockerfile:1`

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix /usr/local -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app /app
COPY . .

RUN mkdir -p /app/chroma_db /app/data

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "300", "--log-level", "info"]
```

### Docker behavior

- Base image: `python:3.11-slim`.
- Exposed port: `8000`.
- Server command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 300 --log-level info`.
- Creates directories:
  - `/app/chroma_db`
  - `/app/data`
- Uses multi-stage build to install dependencies in a builder stage.
- Copies installed Python packages from builder into final image.
- Copies full project into final image with `COPY . .`.

### Current `.dockerignore`

Reference: `.dockerignore:1`

```text
__pycache__
*.py[cod]
chroma_db
data
.DS_Store
```

Important issue: `.env` is not ignored. Because `Dockerfile:14` uses `COPY . .`, the current `.env` can be baked into the image.

### Docker build command

```powershell
docker build -t agtaaly-agent .
```

### Docker run command requested

```powershell
docker run -d -p 8000:8000 --name agtaaly-agent agtaaly-agent
```

This maps host port `8000` to container port `8000`.

### Recommended Docker run command with env file

```powershell
docker run -d --rm --name agtaaly-agent -p 8000:8000 --env-file .env agtaaly-agent
```

Security recommendation: add `.env` to `.dockerignore` and pass secrets at runtime with `--env-file` or another secret manager.

### Docker notes for local AI mode

If `AI_PROVIDER=local` and Ollama runs on the host machine:
- On Docker Desktop Windows/macOS, use:
  ```powershell
  OLLAMA_BASE_URL=http://host.docker.internal:11434
  ```
- On Linux, use `--network=host` or configure `host.docker.internal` depending on Docker setup.

## 9. Local usage

### Basic local run

```powershell
python -m pip install -r requirements.txt
python -m scripts.ingest
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### PowerShell helper

Reference: `run_agent.ps1:3`

```powershell
.\run_agent.ps1
```

This runs:
```powershell
python -m scripts.ingest
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Test parser

```powershell
python test_parse.py
```

### Test WhatsApp send

```powershell
python test_send_message.py <phone_number> "message"
```

Example:

```powershell
python test_send_message.py +201001234567 "Hello from AGTAALY"
```

## 10. RAG and knowledge base behavior

### Knowledge source

- Directory: `knowledge/`
- Current file: `knowledge/agtaaly_info.txt:1`
- Reads all non-empty `.txt` files sorted by filename.

### Chunking

Reference: `app/rag.py:59`

- Chunk size: `800`
- Chunk overlap: `100`
- Empty chunks are skipped.

### ChromaDB collections

Reference: `app/rag.py:77`

| Mode/provider | Collection |
|---|---|
| `MOCK_INGEST=true` | `agtaaly-mock` |
| `AI_PROVIDER=local` | `agtaaly-local` |
| default/OpenAI path | `agtaaly` |

Current effective collection with `.env`: `agtaaly-local`.

### Retrieval

Reference: `app/rag.py:179`

- Uses ChromaDB query by default.
- If local provider imports are unavailable, falls back to lexical keyword search.
- Returns up to `TOP_K_RETRIEVAL` chunks.

### Prompting

Reference: `app/agent.py:6`

The agent prompt instructs the LLM to:
- Act as AGTAALY's bus travel assistant for Mauritania.
- Use only retrieved knowledge.
- Answer questions about routes, schedules, reservations, payments, agencies, and support.
- Say it does not know if the answer is not in the knowledge base.

## 11. Current operational mode

Based on current `.env`:

| Setting | Current value |
|---|---|
| `AI_PROVIDER` | `local` |
| `WHATSAPP_TEST_MODE` | `true` |
| `MOCK_WHATSAPP_SEND` | `false` |
| `WHATSAPP_API_VERSION` | `v22.0` |
| `WHATSAPP_TOKEN` | set, redacted |
| `WHATSAPP_PHONE_NUMBER_ID` | set, partially redacted |
| `WHATSAPP_VERIFY_TOKEN` | set, redacted |
| `WHATSAPP_TEST_REPLY` | `مرحباً! وصلت رسالتك. سيرد عليك فريق AGTAALY قريباً.` |

Effective behavior:
- Startup skips knowledge ingestion because `WHATSAPP_TEST_MODE=true`.
- Incoming WhatsApp messages receive the fixed Arabic test reply.
- No RAG query or LLM call is performed while test mode is enabled.

## 12. Security and privacy observations

1. `.env` contains sensitive WhatsApp credentials and is not ignored by Docker build context.
2. `app/whatsapp.py:18` logs outbound payload, including recipient phone number and message body.
3. `app/main.py:179` logs raw webhook payload, including sender phone number and message text.
4. `/ingest` and `/status` have no authentication.
5. `OPENAI_API_KEY` is not used by the current implementation.
6. Current `.env` has `WHATSAPP_TEST_MODE=true`; production should set this to `false`.
7. Current `.env` has `MOCK_WHATSAPP_SEND=false`; production sends real WhatsApp messages.
8. SQLite duplicate DB and ChromaDB contain operational data; they are ignored by `.dockerignore`, but not by `.gitignore` for `.env`.

## 13. Known gaps and risks

| Priority | Issue | Location | Impact |
|---|---|---|---|
| High | `requirements.txt` missing `chromadb`, `langchain-huggingface`, `langchain-ollama`. | `requirements.txt:1` | Local/Docker runtime may fail. |
| High | `.env` can be copied into Docker image. | `.dockerignore:1`, `Dockerfile:14` | Secrets may be embedded in image layers. |
| High | OpenAI mode is documented but not implemented. | `app/providers.py:9`, `app/rag.py:161` | `AI_PROVIDER=openai` cannot actually generate answers or ingest embeddings. |
| Medium | `providers.py` imports local provider packages unconditionally. | `app/providers.py:1` | OpenAI mode still requires local packages installed. |
| Medium | `/ingest` has no authentication. | `app/main.py:205` | Anyone with network access can rebuild knowledge base. |
| Medium | `/status` exposes internal mode/collection state. | `app/main.py:136` | May leak configuration details. |
| Medium | Logs contain message bodies and phone numbers. | `app/main.py:179`, `app/whatsapp.py:18` | Privacy risk. |
| Medium | Local Ollama URL may be wrong inside Docker. | `.env.example:14`, `Dockerfile:1` | Container may not reach host Ollama. |
| Low | `APP_HOST` and `APP_PORT` are settings but not used by Uvicorn command. | `app/config.py:11`, `Dockerfile:22` | Docker image cannot adjust port via env without command override. |
| Low | `test_webhook.json` appears to be a malformed JSON sample. | `test_webhook.json:1` | May fail if used directly with `curl --data-binary @test_webhook.json`. |

## 14. Recommended fixes

1. Add missing runtime dependencies to `requirements.txt`:
   - `chromadb`
   - `langchain-huggingface`
   - `langchain-ollama`

2. Add `.env` to `.dockerignore`:
   ```text
   .env
   ```

3. Decide provider strategy:
   - If OpenAI mode should work, implement OpenAI embeddings and chat model using `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, and `OPENAI_MODEL`.
   - If local mode is the only supported mode, update README and `.env.example` to remove OpenAI claims.

4. Avoid logging raw WhatsApp payloads or redact:
   - sender phone number
   - message body
   - outbound message body
   - API response previews

5. Add authentication for:
   - `POST /ingest`
   - `GET /status`

6. Use runtime env passing instead of baking `.env`:
   ```powershell
   docker run -d --rm --name agtaaly-agent -p 8000:8000 --env-file .env agtaaly-agent
   ```

7. For Docker + host Ollama, set:
   ```dotenv
   OLLAMA_BASE_URL=http://host.docker.internal:11434
   ```

8. Set production mode:
   ```dotenv
   WHATSAPP_TEST_MODE=false
   MOCK_INGEST=false
   MOCK_WHATSAPP_SEND=false
   ```

## 15. Minimal production Docker checklist

```powershell
# 1. Update .dockerignore to include .env
# 2. Build image
docker build -t agtaaly-agent .

# 3. Run with env file
docker run -d --rm --name agtaaly-agent -p 8000:8000 --env-file .env agtaaly-agent

# 4. Check logs
docker logs -f agtaaly-agent

# 5. Health check
curl http://localhost:8000/health

# 6. Status check
curl http://localhost:8000/status
```

## 16. Minimal local production checklist

```powershell
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Ensure knowledge files exist in knowledge/

# 3. Ingest knowledge
python -m scripts.ingest

# 4. Start service
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. Verify WhatsApp webhook
curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=CHALLENGE"

# 6. Test status
curl http://localhost:8000/status
```

## 17. Final audit conclusion

AGTAALY Agent is a working FastAPI WhatsApp webhook service with RAG-backed reply logic and local/Ollama-focused implementation. The current `.env` puts it in WhatsApp test mode, so it does not use RAG or LLM responses yet. The most important production blockers are missing dependency declarations, incomplete OpenAI provider support, unauthenticated management endpoints, privacy-sensitive logs, and the risk of baking `.env` secrets into the Docker image.
