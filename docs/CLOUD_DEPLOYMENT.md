# NARAD — Cloud Deployment & Future Laptop Migration Guide

This document specifies the deployment architecture, configuration, operation, and migration lifecycle for the **NARAD Phase 2.5 / Phase 3 Production Backend**.

---

## 1. Architectural Strategy

NARAD is designed with a **zero-rewrite portable backend**:

```
[CURRENT PHASE: TEMPORARY CLOUD HOST]
iPhone / Web Client
       │ (HTTPS / Bearer Auth / SSE)
       ▼
Cloud NARAD Backend (Render / Docker / Linux VPS)
       ├── Model Router -> Cloud LLMs (Groq, NVIDIA, Gemini, OpenRouter)
       ├── Persistent DB -> Managed PostgreSQL
       └── Local Capabilities -> UNAVAILABLE_MAC_OFFLINE (truthful)

[FUTURE PHASE: SELF-HOSTED LAPTOP MIGRATION]
iPhone / Web Client
       │ (HTTPS / Tailscale / LAN / Cloud Bridge)
       ▼
Self-Hosted Laptop NARAD Backend (macOS / Linux)
       ├── Model Router -> Local Ollama + Cloud LLMs
       ├── Computer Control -> AppleScript & macOS System Events
       ├── Vision -> Trinetra Screen Analysis
       ├── Voice -> Local Whisper STT & Chatterbox TTS
       └── Persistent DB -> PostgreSQL or Local SQLite
```

The iOS client uses the exact same `/api/v1/...` contract in both phases.

---

## 2. Local Development

### Prerequisites
- Python 3.12+
- Node.js 18+ (for Web HUD)

### Backend Setup
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run dev server with auto-reload
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Local Authentication (Web HUD → Backend)
If `NARAD_API_KEY` is set, every non-public endpoint requires
`Authorization: Bearer <key>` (or `X-Narad-Key: <key>`); otherwise it returns `401`.

- **Canonical local secret:** `backend/.env` → `NARAD_API_KEY=...` (gitignored).
- **How the HUD authenticates:** the Vite dev/preview server proxies `/api` to
  `http://127.0.0.1:8000` and injects the Bearer header **server-side**
  (`frontend/naradDevAuth.js`). It resolves the key with the same precedence as the backend
  (process env, then `backend/.env`, `backend/.venv/.env`, root `.env`; later wins), so both
  always agree. Edits to `backend/.env` apply without restarting Vite (restart the backend).
- **Why not `VITE_NARAD_API_KEY`:** `VITE_*` values are inlined into the browser bundle and
  `dist/`. The proxy approach also covers `<img src="/api/...">`/audio requests that can't
  carry headers.
- **Safety:** the key value is never logged (Vite prints only its source file), auth is
  injected only for loopback clients, and client-supplied credentials are never overwritten.
- **Test:** `npm run test:auth`

---

## 3. Cloud Deployment

NARAD is vendor-neutral and can run on **Render, Railway, Fly.io, AWS, GCP, or any Docker-compatible host**.

### Option A: Render (Native Python)
1. Fork or push repository to GitHub.
2. In Render Dashboard, click **New** -> **Blueprint**.
3. Select this repository. Render will automatically read `render.yaml`:
   - Provisions a Web Service (`narad-api`) using Python 3.12.
   - Provisions a managed PostgreSQL database (`narad-db`).
   - Links `DATABASE_URL` automatically.
4. Set your provider API keys under Environment Variables (`GROQ_API_KEY`, etc.).
5. Deploy.

### Render service identity
| | Name | URL | Managed by |
| :--- | :--- | :--- | :--- |
| Canonical Blueprint service | `narad-api` | `narad-api[-xxxx].onrender.com` (assigned on creation) | `render.yaml` |
| Canonical Blueprint database | `narad-db` | internal | `render.yaml` |
| **Currently live service** | dashboard-defined | `https://narad-gqtp.onrender.com` | Render dashboard (not `render.yaml`) |

- Render matches Blueprint resources **by name**. Do not rename `narad-api`/`narad-db` in
  `render.yaml` to "match" the live URL — a Blueprint sync would create new resources
  (including an empty database).
- The live service's subdomain does not derive from `narad-api`, so it was most likely
  created manually. Confirm under **Service → Settings** (a Blueprint-managed service shows
  its Blueprint). For a dashboard service, configure env vars, start command
  (`uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`), root directory
  (`backend`) and health check (`/health`) in the dashboard; `render.yaml` edits do not apply
  and `autoDeploy` is whatever the dashboard says.
- `CORS_ORIGINS` accepts comma-separated values or a JSON array. Include the origin of any
  **hosted** frontend that calls the API directly from a browser. The local HUD goes through
  the Vite proxy (server-to-server), so it does not need a CORS entry on the cloud service.
- The cloud `NARAD_API_KEY` must differ from the local one.

### Option B: Docker Container
Build and run the container locally or on any server:
```bash
# Build image
docker build -t narad-backend -f backend/Dockerfile backend/

# Run container with PostgreSQL and an API key
docker run -d \
  -p 8000:8000 \
  -e ENVIRONMENT=CLOUD \
  -e NARAD_RUNTIME_MODE=cloud \
  -e NARAD_API_KEY="your-secret-token-here" \
  -e DATABASE_URL="postgresql://user:password@db-host:5432/narad" \
  -e GROQ_API_KEY="gsk_..." \
  --name narad-app \
  narad-backend
```

---

## 4. Environment Variables Reference

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `LOCAL` | `LOCAL`, `CLOUD`, or `SELF_HOSTED` |
| `NARAD_RUNTIME_MODE` | `hybrid` | `cloud` (disables Mac local tools), `local` (offline-first), `hybrid` |
| `DATABASE_URL` | `sqlite:///./narad.db` | SQLite URI locally; `postgresql://...` in cloud |
| `NARAD_API_KEY` | *(empty)* | Single-user bearer authentication token |
| `PORT` | `8000` | HTTP listening port (assigned by cloud host) |
| `HOST` | `0.0.0.0` | Bind host |
| `CORS_ORIGINS` | *(localhost)* | Comma-separated list of allowed web origins |
| `RATE_LIMIT_ENABLED` | `True` | Sliding-window in-memory rate limiter |
| `RATE_LIMIT_PER_MINUTE` | `120` | Max requests per minute per IP |
| `MAX_REQUEST_SIZE_BYTES` | `15728640` | Request body limit (15 MB) |
| `GROQ_API_KEY` | *(empty)* | Fast cloud inference |
| `NVIDIA_API_KEY` | *(empty)* | Alternative cloud inference |
| `GEMINI_API_KEY` | *(empty)* | Alternative multimodal inference |

---

## 5. Health & Readiness Probes

The backend provides non-blocking, zero-token probes for load balancers and orchestrators:

- **Root Health**: `GET /health`
  ```json
  { "status": "online", "app": "NARAD", "version": "3.2.0", "database": "connected", "dialect": "postgresql" }
  ```
- **Readiness Probe**: `GET /ready`
  Verifies active database ping query. Returns HTTP 200 if ready, HTTP 503 if database unreachable.
- **Version Info**: `GET /version`
- **Mobile Runtime Status**: `GET /api/v1/runtime/status`
  Returns operational status (`ONLINE`, `CLOUD`, `LOCAL`, `OFFLINE`, `DEGRADED`) and truthful local/cloud capability reach.

---

## 6. Migration: Cloud → Future Self-Hosted Laptop

When your old laptop is ready to take over as the permanent host:

### Step 1: Export Data from Cloud
Run an authenticated backup export from your cloud backend:
```bash
curl -H "Authorization: Bearer <YOUR_API_KEY>" \
     https://<YOUR_CLOUD_URL>/api/backup/export \
     -o narad_backup.json
```

### Step 2: Set Up Laptop Environment
1. Clone the repository onto the laptop.
2. Install Python 3.12 and Ollama.
3. Configure `backend/.env`:
   ```ini
   ENVIRONMENT=SELF_HOSTED
   NARAD_RUNTIME_MODE=hybrid
   DATABASE_URL=sqlite:///./narad.db
   NARAD_API_KEY=<SAME_KEY_AS_CLOUD>
   OLLAMA_ENABLED=true
   TTS_LOCAL=true
   ```

### Step 3: Import Persistent Data
```bash
curl -X POST \
     -H "Authorization: Bearer <YOUR_API_KEY>" \
     -H "Content-Type: application/json" \
     -d @narad_backup.json \
     http://localhost:8000/api/backup/import
```

### Step 4: Point iPhone / Clients to Laptop
Simply update the Base URL in the iOS application from `https://<YOUR_CLOUD_URL>` to your laptop's URL (e.g. `https://narad.<your-tailscale-tailnet>.ts.net` or local IP).
**Zero mobile code changes or contract modifications required.**
