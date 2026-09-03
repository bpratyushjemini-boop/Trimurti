# 🌐 NARAD (Networked Agent for Retrieval, Analysis & Dissemination)

> **V1 Private AI Core & Agentic Orchestrator of the TRIMURTI AI Ecosystem**

NARAD is a private, single-user personal AI assistant and desktop intelligence interaction gateway designed for retrieval, synthesis, execution, and communication across local and networked intelligence nodes. Built with a sleek, technical **JARVIS-inspired** visual language, NARAD combines a responsive 3-column HUD command interface with a robust, model-agnostic FastAPI backend and local SQLite persistence.

---

## 🏛️ The TRIMURTI Vision

NARAD is the foundational interaction layer of the broader TRIMURTI ecosystem:
- **NARAD**: Networked Agent for Retrieval, Analysis & Dissemination *(V1 Core Live)*
- **Smriti**: Persistent Context, Vector Memory & Knowledge Vault *(Upcoming)*
- **Manthan**: Deep Reasoning, Deliberation & Synthesis Engine *(Upcoming)*
- **Kriya**: Execution, Tool Calling & Action Orchestration *(Upcoming)*
- **Trinetra**: Multimodal Vision, Perception & Screen Understanding *(Upcoming)*
- **Vaani**: Real-time Voice & Audio Stream Intelligence *(Upcoming)*

---

## ⚡ Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS, Lucide Icons
- **Backend**: Python 3.9+, FastAPI, Pydantic v2, Uvicorn, SQLAlchemy
- **Database**: SQLite (`backend/narad.db`, isolated local storage)
- **AI Core**: Model Router with Google Gemini provider (`gemini-2.5-flash`)
- **SDK**: Official `google-genai` with asynchronous HTTPX REST fallback
- **Theme**: JARVIS Technical HUD (Deep navy void `#070b14`, cyan highlights `#00f0ff`, refined hairline borders, telemetry readouts)

---

## 📂 Project Structure

```
Narad/
├── .gitignore                   # Security & hygiene rules (secrets, venvs, dbs ignored)
├── README.md                    # Project documentation
├── backend/
│   ├── .env.example             # Safe environment configuration template
│   ├── requirements.txt         # FastAPI, Uvicorn, SQLAlchemy, Pydantic, google-genai
│   ├── config.py                # Configuration compatibility shim
│   └── app/
│       ├── main.py              # FastAPI application & CORS configuration
│       ├── core/
│       │   ├── config.py        # Centralized settings & explicit .env loader
│       │   ├── narad.py         # NARAD Core intelligence orchestration service
│       │   └── router.py        # Deterministic Model Router
│       ├── db/
│       │   ├── database.py      # SQLite connection & session maker
│       │   └── models.py        # ChatSession and ChatMessage SQLite models
│       ├── providers/
│       │   ├── base.py          # Abstract BaseLLMProvider interface
│       │   ├── gemini.py        # Google Gemini live provider implementation
│       │   └── manager.py       # Provider registry & reserved slots
│       └── api/
│           └── routes/
│               ├── health.py    # Health check & system telemetry
│               ├── chat.py      # Canonical POST /api/chat endpoint
│               ├── chats.py     # Conversation session management
│               └── messages.py  # Message dispatch & history
└── frontend/
    ├── index.html               # Technical HTML shell
    ├── package.json             # React, Vite, Tailwind dependencies
    ├── vite.config.js           # Vite server & backend API proxy
    ├── tailwind.config.js       # Custom JARVIS color tokens & HUD utilities
    ├── postcss.config.js
    └── src/
        ├── index.css            # Custom scanlines, glow limits, scrollbars
        ├── App.jsx              # Main 3-column JARVIS interface
        ├── components/
        │   ├── sidebar/         # Left sidebar (identity, chats, search)
        │   ├── chat/            # Center conversation (messages, status, composer)
        │   └── hud/             # Right sidebar (system status, model telemetry, tools)
        └── services/
            └── api.js           # Backend API communication layer
```

---

## 🚀 Quick Start Guide

### 1. Environment Configuration

Create `backend/.env` using `backend/.env.example` as a template:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add your Google Gemini API key:

```env
GEMINI_API_KEY=your_gemini_api_key_here
NARAD_DEFAULT_PROVIDER=gemini
NARAD_DEFAULT_MODEL=gemini-2.5-flash
```

> Obtain a free Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey). Valid keys begin with `AIzaSy...`.

### 2. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run FastAPI backend on port 8000
uvicorn app.main:app --reload --port 8000
```
- Backend API: `http://localhost:8000`
- Health & Telemetry: `http://localhost:8000/api/health`
- Interactive API Docs: `http://localhost:8000/docs`

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```
- Frontend Interface: `http://localhost:5173`
- All `/api/*` requests automatically proxy to the FastAPI backend on port `8000`.

---

## 🔒 Security & Secrets Management

- **Zero Secrets in Code**: API keys and credentials must **never** be committed to version control.
- Credentials reside exclusively in `backend/.env`, which is strictly excluded by `.gitignore`.
- Neither client-side code nor browser responses ever expose or receive raw API keys.
- If `GEMINI_API_KEY` is missing or invalid, NARAD returns an explicit, user-friendly diagnostic alert rather than crashing or inventing fake responses.

---

## 🛠️ Status & Milestones

- [x] **Milestone 1**: Foundations & Clean Skeleton (FastAPI backend foundation, React+Tailwind JARVIS interface).
- [x] **Milestone 2**: Single-User Local Architecture & SQLite Persistence (Private local vault, session management, dark HUD).
- [x] **Milestone 3**: Real AI Core & Model Router (Google Gemini 2.5 Flash integration, deterministic Model Router, dynamic key loading, zero mock fallback).
- [ ] **Milestone 4**: Smriti (Persistent local vector memory, document ingestion, semantic search).
- [ ] **Milestone 5**: Kriya (Local tool execution engine, file I/O, terminal actions).
- [ ] **Milestone 6**: Manthan (Deep multi-step deliberation and reasoning).
- [ ] **Milestone 7**: Trinetra (Vision) & Vaani (Voice).
