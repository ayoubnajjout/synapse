# Synapse

**One Interface. Every Model. Shared Memory.**

A lightweight, self-hosted AI chat workspace. Switch between cloud and local models inside a conversation, with persistent history and explicit, shared memory. No accounts, analytics, or external memory service.

## Run with Docker

Requires Docker Engine/Desktop and Docker Compose v2 or newer.

```bash
cp .env.example .env
docker compose up -d --build
```

Open **http://localhost:3000**. The first build downloads dependencies and may take several minutes. Open **Settings → Providers** to connect a provider and choose from its automatically discovered models. You need either a cloud API key or a running local model server to generate responses.

Three containers run: `frontend` (compiled React served by Caddy), `backend` (FastAPI/LiteLLM), and `db` (PostgreSQL). Only the frontend publishes a port, bound to `127.0.0.1`. Backend and database traffic stays inside the Compose network. To use another local port, set `SYNAPSE_PORT` in `.env`.

```bash
docker compose ps
docker compose logs --tail=50 frontend backend
docker compose down       # preserves database volume
docker compose up -d      # restores your workspace
```

Do not use `docker compose down -v` unless you intend to delete the entire database. Back up before upgrading:

```bash
docker compose exec -T db pg_dump -U synapse synapse > synapse-backup.sql
```

Conversation JSON exports omit memories and settings. Use a database backup to preserve everything.

## Configure providers

API keys are environment-only. Put keys in `.env`, never in the browser or Git. Recreate the backend after changing environment variables:

```bash
docker compose up -d --force-recreate backend
```

| Provider | Key variable | Model variable | LiteLLM routing |
| --- | --- | --- | --- |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_MODELS` | `openai/<model>` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODELS` | `anthropic/<model>` |
| Google Gemini | `GEMINI_API_KEY` | `GEMINI_MODELS` | `gemini/<model>` |
| xAI | `XAI_API_KEY` | `XAI_MODELS` | `xai/<model>` |
| Ollama | `OLLAMA_API_KEY` (optional) | `OLLAMA_MODELS` | `ollama_chat/<model>` |
| LM Studio | `LMSTUDIO_API_KEY` (optional) | `LMSTUDIO_MODELS` | `openai/<model>` |

Each provider also accepts `<PREFIX>_API_BASE`. Model environment variables are optional comma-separated fallback IDs **without** the LiteLLM routing prefix. Synapse discovers models from each connected provider automatically. There is no fixed model allowlist, so newly available model IDs appear when you refresh. A connected badge means credentials or an endpoint are present. Catalog discovery lists available models without sending a chat prompt. Actual model access is verified when you send a message.

Choose your default model in Settings → Providers. Use the searchable chat model chooser to switch models or refresh the catalog. Your last selection is remembered in this browser. Endpoints, saved choices, and custom model IDs can also be changed in Settings; manual IDs are tucked into Advanced options. These overrides persist in PostgreSQL and take precedence over environment defaults. Live catalogs are cached for 60 seconds per endpoint and credentials; refresh bypasses the cache. During an outage, cached and saved/custom model choices remain available with a notice. Catalog requests are bounded to 15 seconds, 10 pages and 1,000 discovered models. Clearly non-chat models are excluded where possible; account access and provider catalogs can still vary. Keys are never stored in the settings table or returned by settings endpoints. Endpoint URLs must not contain credentials or query parameters. Other OpenAI-compatible servers can use the LM Studio slot with a custom base URL and model ID.

### Local models

Install and start Ollama or LM Studio independently. Pull/load a model before using Synapse. Example configuration:

```dotenv
OLLAMA_API_BASE=http://localhost:11434
# Or:
LMSTUDIO_API_BASE=http://localhost:1234
```

Enter your normal local server address in Settings, such as `http://localhost:11434`. In the Synapse Docker image, loopback addresses for Ollama and LM Studio are automatically routed through `host.docker.internal`; native development keeps localhost unchanged. The original address remains saved. Discovery and chat always use the same resolved address. Ollama accepts its server root or copied `/api/tags`, `/api/chat`, and `/v1` URLs; LM Studio automatically adds `/v1` when only its server root is provided.

The chooser lists installed chat models, not the entire downloadable Ollama library. Embedding-only models are excluded where their name or capabilities identify them. Install a chat model in Ollama or LM Studio, then click **Connect & find models** or **Refresh models**. No model ID configuration is required.

- **Docker Desktop:** `host.docker.internal` normally resolves to the host. The inference server must accept connections from Docker.
- **Linux Docker Engine:** Compose adds `host.docker.internal:host-gateway`. A server listening only on host loopback may still be unreachable from the bridge network. Bind it to an interface reachable by that bridge and restrict access with your firewall. For Ollama, configure its `OLLAMA_HOST`; for LM Studio, enable serving on the local network. Do not expose inference ports to an untrusted network.
- **Another machine/container:** use its reachable hostname/address and correct port. Add `/v1` for OpenAI-compatible LM Studio endpoints; use Ollama's root endpoint for `ollama_chat`.

Connection failures are shown in the UI without losing saved messages.

### GPU preference and CPU fallback

The model server owns GPU access; the Synapse containers do not run inference and do not need GPU passthrough.

- **Ollama:** Synapse requests automatic GPU placement (`num_gpu=-1`). Ollama uses available GPU memory and CPU capacity as needed. A recognized GPU initialization/allocation error before the first visible response triggers one CPU-only retry (`num_gpu=0`). Authentication, connection errors, cancellation, and failures after text has streamed do not trigger this retry. Check actual placement with `ollama ps` on the model-server host.
- **LM Studio:** OpenAI-compatible chat uses the model's load settings. Keep GPU offload on **Auto** in LM Studio's model defaults for automatic device placement. You can also load a model with `lms load <model-key> --gpu auto`; changing an already loaded model's offload settings requires reloading it in LM Studio. Synapse cannot override GPU load settings through the OpenAI-compatible chat endpoint. See [LM Studio load settings](https://lmstudio.ai/docs/cli/local-models/load).

Actual GPU use depends on the server's hardware, drivers, model format and available memory. CPU-only machines remain supported.

## Features

- Streaming chat through LiteLLM with Stop and regenerate/retry.
- Provider and model selection within the same conversation.
- Persistent conversations, stable message ordering, rename, search and delete.
- Manual memory creation, editing, per-memory toggles, global toggle and clearing.
- Bounded context with a visible notice when messages or memories are excluded.
- Validated JSON import and single/all conversation export. Imports always create fresh IDs.
- A minimal chat interface with a non-scrolling welcome screen, light/dark themes, safe Markdown, copy buttons for messages and individual code blocks, code wrapping, and a jump-to-latest control.
- Automatic model discovery for all six providers, searchable model selection and remembered choices. Advanced custom IDs keep gateways and future models usable.

Messages are saved before generation. Only completed assistant responses are saved; cancellation or failure rolls back assistant writes. Regeneration replaces the previous answer only after success. Client-generated message and generation UUIDs make retries idempotent. PostgreSQL row locks reject concurrent writes to a conversation while generation is active, including across application processes. Other conversations remain available.

### Context policy

Each chat has its own stored message history. Explicit saved memories are global and shared across all chats; there is no automatic per-chat memory extraction. Each request gets one application system message, enabled shared memories, and a contiguous suffix of that chat’s recent messages in chronological order, independent of their original provider. Defaults are **24,000 input characters**, **40 messages**, and **2,048 output tokens**. Change them in Settings → General.

Enabled memories are considered oldest-first and use up to 25% of the character budget; entries are never split. The rest is filled with newest whole messages, stopping at the first message that cannot fit or the message count limit. Leading assistant turns at the cutoff are removed for provider compatibility. If the latest user message cannot fit, generation fails rather than silently omitting it. Excluded content remains stored and the UI shows counts. Character budgeting is approximate; select limits below your model's actual context window. No automatic extraction, summarization, embeddings or semantic retrieval is performed.

## Architecture

```text
Browser → frontend (Caddy + React) → /api → backend (FastAPI + LiteLLM)
                                               ├── db (PostgreSQL)
                                               └── Cloud APIs / local model servers
```

The frontend and backend have independent Dockerfiles and builds. Caddy serves the compiled frontend and forwards `/api/*` without buffering model streams. FastAPI handles only API requests. PostgreSQL readiness is checked before the backend starts; the frontend waits for backend health. The existing `postgres_data` volume retains conversations, messages, memories, and settings.

If upgrading from the original combined application container, run:

```bash
docker compose up -d --build --remove-orphans
```

This removes the old `app` container while retaining the database volume. You can rebuild just one service with `docker compose up -d --build frontend` or `docker compose up -d --build backend`.

Source: `frontend/src`, `backend/app`, and `backend/tests`. The API schema is at `/api/openapi.json`. Dependencies are locked. Tables initialize on startup; future incompatible schema changes will need migrations.

## Local development

Requires Python 3.12+, Node 20.19+/22.12+, npm, and a reachable PostgreSQL instance. The production path is Docker; Vite is only a development server.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt

# Use the credentials/address for your development PostgreSQL instance.
export DATABASE_URL=postgresql+psycopg://synapse:synapse@localhost:5432/synapse
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to port 8000. Export provider variables in the backend's shell; Compose's `.env` is not automatically read by direct Uvicorn. The backend no longer serves frontend files. Use Vite for local development or the frontend container for production.

## Tests

```bash
.venv/bin/python -m pytest -q
cd frontend && npm ci && npm run build
docker compose config --quiet
```

The portable backend suite uses SQLite only as a test fixture and mocks the LiteLLM boundary. The application uses PostgreSQL. To run the same suite against real PostgreSQL, including row locking and JSONB, start an isolated test database:

```bash
docker run -d --name synapse-test-db \
  -e POSTGRES_USER=synapse -e POSTGRES_PASSWORD=synapse -e POSTGRES_DB=synapse_test \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
# Wait for: docker exec synapse-test-db pg_isready -U synapse -d synapse_test
TEST_DATABASE_URL=postgresql+psycopg://synapse:synapse@localhost:55432/synapse_test \
  .venv/bin/python -m pytest -q
docker rm -fv synapse-test-db
```

Tests use a fresh schema per test and clean it up. They cover CRUD, ordered persistence, provider switching, memory inclusion/exclusion, context truncation, idempotency, import validation, secret exclusion, stream errors and cancellation. Real-provider calls require your own credentials/server; mocked tests do not verify external model availability.

## Privacy and deployment limits

This is an **unauthenticated, single-user application for trusted local/private environments**. Do not expose it directly to the public internet. Any client with access can read and change the workspace and invoke configured providers. Loopback publication, same-origin checks and response headers provide baseline protection, not user authentication.

Cloud providers receive the included messages and enabled memories. Local inference keeps model requests on your chosen local endpoint. Remote Markdown images are not loaded; raw HTML is not executed. No analytics or telemetry integrations are enabled. Provider errors shown to users are sanitized rather than forwarding SDK error details.

Database backups and exports contain private conversation content. `.env` contains provider credentials and must be protected. Use an alphanumeric PostgreSQL password with the supplied Compose URL, or update the URL construction to encode reserved characters correctly. Changing the password variable does not change credentials in an already-initialized PostgreSQL volume; rotate the database password explicitly.

Licensed under [MIT](LICENSE).
