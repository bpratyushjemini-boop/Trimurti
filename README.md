# 🌐 NARAD (Networked Agent for Retrieval, Analysis & Dissemination)

> **V1 Core Interface & Agentic Orchestrator of the TRIMURTI AI Ecosystem**

NARAD is the primary desktop intelligent interaction gateway designed for retrieval, synthesis, execution, and communication across local and networked intelligence nodes. Built with a sleek, technical **JARVIS-inspired** visual language, NARAD combines a responsive 3-column HUD command interface with a robust, model-agnostic FastAPI backend.

---

## 🏛️ The TRIMURTI Vision

NARAD is the initial V1 component of the broader TRIMURTI ecosystem:
- **NARAD**: Networked Agent for Retrieval, Analysis & Dissemination *(Current)*
- **Smriti**: Persistent Context, Vector Memory & Knowledge Graph *(Upcoming)*
- **Manthan**: Deep Reasoning, Deliberation & Synthesis Engine *(Upcoming)*
- **Kriya**: Execution, Tool Calling & Action Orchestration *(Upcoming)*
- **Trinetra**: Multimodal Vision, Perception & Screen Understanding *(Upcoming)*
- **Vaani**: Real-time Voice & Audio Stream Intelligence *(Upcoming)*

---

## ⚡ Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS, Lucide Icons
- **Backend**: Python 3.9+, FastAPI, Pydantic v2, Uvicorn
- **Database**: SQLite (SQLAlchemy ORM)
- **Architecture**: Modular provider abstraction (model-agnostic)
- **Theme**: JARVIS Technical HUD (Deep navy void `#070b14`, cyan highlights `#00f0ff`, refined hairline borders, telemetry readouts)

---

## 📂 Project Structure

```
Narad/
├── .gitignore                   # Security & hygiene rules (secrets, venvs, dbs ignored)
├── README.md                    # Project documentation
├── backend/
│   ├── .env.example             # Safe environment variable configuration template
│   ├── requirements.txt         # FastAPI, Uvicorn, SQLAlchemy, Pydantic
│   └── app/
│       ├── main.py              # FastAPI application & CORS configuration
│       ├── core/
│       │   └── config.py        # Centralized settings & environment loader
│       ├── db/
│       │   ├── database.py      # SQLite connection & session maker
│       │   └── models.py        # ChatSession and ChatMessage SQLite models
│       ├── providers/
│       │   ├── base.py          # Abstract BaseLLMProvider interface
│       │   └── manager.py       # Model-agnostic provider registry
│       └── api/
│           └── routes/
│               ├── health.py    # Health check & system telemetry
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
        │   ├── sidebar/         # Left sidebar (branding, chats, search, nav)
        │   ├── chat/            # Center conversation (messages, status, composer)
        │   └── hud/             # Right sidebar (system status, model telemetry, tools)
        └── services/
            └── api.js           # Backend API communication layer
```

---

## 🚀 Quick Start Guide

### 1. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run FastAPI backend
uvicorn app.main:app --reload --port 8000
```
Backend API will be live at: `http://localhost:8000`  
Interactive API docs: `http://localhost:8000/docs`

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```
Frontend interface will be live at: `http://localhost:5173`

---

## 🔒 Security & Secrets Management

- **Zero Secrets in Code**: API keys and secrets must **never** be committed to version control.
- All credentials reside exclusively in `.env` files which are strictly excluded by `.gitignore`.
- Always use `.env.example` as a template for new configuration variables.

---

## 🛠️ Roadmap & Milestones

- [x] **Milestone 1**: Foundations & Clean Skeleton (Git, .gitignore, README, FastAPI backend foundation, React+Tailwind JARVIS 3-column interface).
- [ ] **Milestone 2**: Database persistence & full chat session management.
- [ ] **Milestone 3**: Model-agnostic AI provider implementations (Gemini, Groq, OpenRouter, Claude, OpenAI).
- [ ] **Milestone 4**: Attachment processing, voice hooks & tool execution primitives.
