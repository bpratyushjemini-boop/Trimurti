# 🌐 NARAD (Neural Assistant for Rizz & Absolute Destruction)

> **V3.1 Intelligent Multi-Provider Router + Conversational Core of the TRIMURTI AI Ecosystem**

NARAD is a private, single-user personal AI assistant and desktop intelligence interaction gateway designed for retrieval, synthesis, execution, and communication across local and networked intelligence nodes. Built with a sleek, technical **JARVIS-inspired** visual language, NARAD combines a responsive 3-column HUD command interface with a model-agnostic FastAPI backend, local SQLite persistence, persistent Smṛti memory, Krīya tool execution, local Knowledge Base retrieval, Vāṇī voice interaction, and an Intelligent Multi-Provider Router.

---

## 🏛️ The TRIMURTI Architecture

NARAD serves as the central cognitive orchestration interface of TRIMURTI:
- **NARAD [V3.1]**: Conversational Core & Intelligent Multi-Provider Router *(Active)*
- **Smṛti**: Persistent Long-Term Memory & User Profile Knowledge Vault *(Active)*
- **Krīya**: Execution Engine & Real-World Tool Dispatcher *(Active)*
- **Knowledge Base [V2.2]**: Local Document Ingestion, Chunking & FTS5 Semantic Retrieval *(Active)*
- **Vāṇī [V3]**: Bidirectional Voice Agent (Web Speech STT & Speech Synthesis TTS) *(Active)*
- **Manthan**: Deep Reasoning, Deliberation & Thought Chains *(Integrated via Router)*
- **Trinetra**: Multimodal Vision & Perception *(Routing Ready)*

---

## ⚡ Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS, Lucide Icons, Web Speech API (Vāṇī STT/TTS)
- **Backend**: Python 3.9+, FastAPI, Pydantic v2, Uvicorn, SQLAlchemy, SQLite (FTS5)
- **Primary AI Provider**: Groq LPU (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`)
- **Multi-Provider Connectors**:
  - **Groq LPU**: Ultra-fast low-latency inference with Krīya tool calling
  - **NVIDIA NIM**: Enterprise open-source models (`meta/llama-3.3-70b-instruct`, `deepseek-r1`)
  - **Google Gemini**: Large-context and multimodal reasoning (`gemini-2.5-flash`)
  - **OpenRouter**: Universal gateway (`meta-llama/llama-3.3-70b-instruct`, `anthropic/claude-3.5-sonnet`)
  - **NARAD Simulated Core**: Safe local deterministic failsafe
- **Theme**: JARVIS Technical HUD (Deep navy `#070b14`, cyan `#00f0ff`, amber `#f59e0b`, emerald `#10b981`, hairline borders, real-time telemetry readouts)

---

## 🧠 Core Systems in V3.1

### 1. Intelligent Model Router
Deterministic, heuristic task classifier matching user directives to optimal models across 8 specialized task categories:
- `FAST_CHAT`: Ultra-low-latency models for brief greetings and queries
- `GENERAL_CHAT`: Balanced conversational models
- `REASONING`: Deep mathematical and logical reasoning engines
- `CODING`: Syntax, debugging, and code generation specialists
- `TOOL_USE`: Multi-turn function and tool-calling models
- `LONG_CONTEXT`: Extended context window models (>4k tokens)
- `VISION`: Multimodal visual understanding models
- `VOICE`: High-speed models optimized for conversational voice turns

### 2. Conversational Context & Sliding Window
- **Recent Turn Window**: Maintains the last 12 conversational turns in active working memory.
- **Context Continuity**: Seamlessly resolves pronouns ("that", "it", "they") and follow-up directives ("continue that", "explain why").
- **Memory Separation**: Working dialogue history is strictly separated from persistent long-term Smṛti memories, preventing context bloat and hallucination.

### 3. Automated Failover Engine
- **Transient Failover**: Automatically fails over on HTTP 429 (rate limits), timeouts, connection resets, and 5xx server errors across configured providers (e.g. `GROQ → NVIDIA → GEMINI → OPENROUTER → MOCK-NARAD`).
- **400 Bug Preservation**: Never masks or fails over on HTTP 400 Bad Request or schema validation errors. Surfaces client errors directly to expose integration bugs immediately.
- **Health Matrix & Cooldowns**: Tracks provider latency, consecutive failures, and automatically sets cooldown periods for degraded providers.

### 4. Server-Sent Events (SSE) Streaming
- Real-time token streaming at `POST /api/chat/stream`.
- Progressively streams generated response chunks to the frontend while simultaneously persisting dialogue turns to SQLite.

### 5. Smṛti Persistent Memory & Krīya Tools
- **Persistent Memory**: Explicit user preferences and facts stored in SQLite (`save_memory`, `retrieve_memory`, `delete_memory`, `list_memories`).
- **Real Tools**:
  - `web_search`: Live multi-source web intelligence with verified title, snippet, URL, and domain citations.
  - `search_knowledge`: Local document passage retrieval using SQLite FTS5 full-text indexing.
  - `calculator`: Safe mathematical expression evaluation.
  - `get_current_time` & `get_current_date`: Timezone-aware date/time tools.

### 6. Vāṇī Voice Layer [V7 — Real Two-Way Local Voice Pipeline]
- **Two-Way Voice Pipeline**:
  `MIC → Local Whisper STT → Language Detection → NARAD Core / Tools / Router → Dynamic TTS Router (Chatterbox / IndicVoice) → SPEAKER`
- **Zero Cloud Voice Costs**: 100% private, on-device STT and TTS without any third-party paid voice APIs.
- **Local STT (faster-whisper)**: Whisper `tiny` on CPU with `int8` quantization (~0.5s - 1.2s transcription latency) supporting English, Hindi, and Hinglish.
- **Dynamic TTS Router**:
  - **English**: Chatterbox Multilingual on Apple Silicon `MPS` (~3.7s latency).
  - **Hindi (Devanagari)**: IndicVoice Kokoro-82M Indic G2P on `CPU` (~0.28s - 0.7s latency, ~7x faster than real-time).
  - **Hinglish**: Chatterbox first with IndicVoice fallback.
  - **Fallback**: Browser Web Speech API (only if local models are unavailable).
- **Persistent Model Lifetime**: STT and TTS models are loaded once into memory as singletons—never reloaded per request.
- **Instant Barge-In / Interruption**: Users can interrupt NARAD while speaking at any millisecond; audio buffer playback cancels instantly and clears memory buffers.
- **Real Hardware Telemetry**: Honest hardware reporting (`DEVICE: MPS` for Chatterbox, `DEVICE: CPU` for Whisper/IndicVoice). Real time measurements for `STT: Xs`, `LLM: Ys`, `TTS: Zs`, `TOTAL: Ws`. Zero fake telemetry.

### 7. Hugging Face Local AI Layer [V7.1 — On-Device Intelligence]
- **Additive Local Layer**: Does NOT replace Groq, NVIDIA, Gemini, or OpenRouter; adds on-device local execution for offline mode, privacy-first queries, and semantic embeddings.
- **Local Model Caching via Hugging Face Hub**: Models are downloaded once and cached locally in `~/.cache/huggingface/hub/`. Subsequent runs are zero-delay cache hits.
- **Lightweight On-Device LLM**: `HuggingFaceTB/SmolLM2-135M-Instruct` (~271MB on disk) generating responses in **~300ms** on CPU without requiring external API keys.
- **Local Knowledge Base Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors, ~91MB on disk) accelerated on Apple Silicon **MPS** with cosine similarity re-ranking.
- **Local Vision Provider Interface**: `LocalHuggingFaceVisionProvider` abstraction ready for lightweight multimodal vision models.
- **Capability-Aware Router**: `TASK_LOCAL = "LOCAL"` routes local/offline directives to Hugging Face with automatic cloud failover.
- **Real Hardware Telemetry**: Honest hardware reporting (`DEVICE: CPU` for SmolLM2, `DEVICE: MPS` for all-MiniLM embeddings). Zero fake success.

### 8. Native Ollama Layer [V7.2 — Local-Fast Intelligence]
- **LOCAL_FAST Routing Tier**: High-frequency, lightweight tasks (intent classification, structured JSON/entity extraction, text formatting/normalization, and simple Q&A) route directly to Ollama.
- **Sub-Second On-Device Execution**: Runs locally via Ollama daemon (`http://localhost:11434`) using `qwen3.5:0.8b` with thinking-bypass mode (`think: false`), delivering responses in **~80ms - 300ms**.
- **Preserved Primary Reasoning**: General chat remains routed to Groq LPU (`openai/gpt-oss-120b`) for ultra-low latency conversational fluency, and complex coding/reasoning remains with NVIDIA NIM / Groq. Ollama is never the default for general conversation.
- **Health Detection & Graceful Fallback**:
  - Live daemon inspection via `GET /api/tags`.
  - If Ollama is offline or `qwen3.5:0.8b` is missing, provider status is set to `UNAVAILABLE` or `MODEL_MISSING`.
  - Model Router automatically fails over to Groq/cloud providers with zero server crashes and zero mock responses.
- **Real Latency & Telemetry**:
  - Measures true end-to-end generation latency, prompt token evaluation, and completion tokens.
  - Displayed live in `/api/health` telemetry, Provider Matrix, and the HUD.

---

## 📂 Project Structure

```
Narad/
├── .gitignore                   # Excludes .env, local DBs, venvs, artifacts
├── README.md                    # System architecture & voice documentation
├── backend/
│   ├── .env.example             # Multi-provider template (all secrets excluded)
│   ├── requirements.txt         # Dependencies (includes faster-whisper, indicvoice, chatterbox-tts)
│   ├── app/
│   │   ├── main.py              # FastAPI app & router registrations
│   │   ├── core/
│   │   │   ├── config.py        # Safe settings loader
│   │   │   ├── narad.py         # NARAD Core orchestrator & failover engine
│   │   │   ├── router.py        # Model capability registry & task classifier
│   │   │   ├── kriya.py         # Krīya tool dispatcher
│   │   │   └── prompts.py       # JARVIS system prompts
│   │   ├── providers/           # Model Provider Layer
│   │   │   ├── base.py          # BaseLLMProvider interface & health tracker
│   │   │   ├── groq.py          # Groq LPU Provider (Ultra-Fast)
│   │   │   ├── nvidia.py        # NVIDIA NIM Provider (High-Throughput)
│   │   │   ├── gemini.py        # Gemini Multimodal Provider
│   │   │   ├── openrouter.py    # OpenRouter Universal Gateway
│   │   │   ├── ollama.py        # Native Ollama Local Fast Provider (qwen3.5:0.8b)
│   │   │   ├── huggingface.py   # Hugging Face Local Model Provider (SmolLM2)
│   │   │   └── manager.py       # Central Provider Registry
│   │   ├── services/
│   │   │   ├── stt/             # Vāṇī Speech-to-Text
│   │   │   │   ├── base.py      # BaseSTTProvider interface
│   │   │   │   ├── whisper.py   # faster-whisper local CPU provider
│   │   │   │   └── manager.py   # STT Manager & format normalization
│   │   │   ├── tts/             # Vāṇī Text-to-Speech
│   │   │   │   ├── base.py      # BaseTTSProvider interface
│   │   │   │   ├── chatterbox.py# Chatterbox Multilingual provider (MPS)
│   │   │   │   ├── indicvoice.py# IndicVoice Kokoro-82M Indic G2P provider (CPU)
│   │   │   │   └── manager.py   # Dynamic Language Router & sample diagnostics
│   │   │   ├── smriti.py        # Smṛti persistent memory service
│   │   │   ├── kriya.py         # Krīya tool execution
│   │   │   ├── computer.py      # Native macOS application & screen adapter
│   │   │   └── knowledge.py     # Local Knowledge Base ingestion & FTS5 search
│   │   └── api/
│   │       └── routes/
│   │           ├── voice.py     # POST /api/voice/interact (end-to-end two-way voice)
│   │           ├── stt.py       # GET /api/stt/status, POST /api/stt/transcribe
│   │           ├── tts.py       # GET /api/tts/status, GET /api/tts/engines, POST /api/tts/synthesize, POST /api/tts/test
│   │           ├── health.py    # Multi-provider health matrix & router telemetry
│   │           ├── chat.py      # POST /api/chat & POST /api/chat/stream SSE
│   │           ├── chats.py     # Chat session management
│   │           └── messages.py  # Message dispatch & history
│   └── tests/
│       ├── test_v7_voice.py     # 12-test automated Vāṇī Voice System test suite
│       ├── test_tools.py        # Krīya tool dispatcher tests
│       ├── test_smriti.py       # Smṛti memory subsystem tests
│       └── test_live_e2e.py     # Live multi-turn dialogue, memory & streaming test
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js           # Proxies /api/* to localhost:8000
    ├── tailwind.config.js       # JARVIS color tokens
    └── src/
        ├── App.jsx              # Main JARVIS interface & two-way voice pipeline
        ├── components/
        │   ├── chat/
        │   │   ├── MessageComposer.jsx   # Voice HUD banner, push-to-talk & interrupt
        │   │   ├── VoiceSettingsModal.jsx# TTS/STT hardware cards & diagnostic tester
        │   │   └── ChatWorkspace.jsx     # Message stream with audio play buttons
        │   └── hud/
        │       └── SubsystemsStatus.jsx  # Real Vāṇī telemetry (MPS/CPU, STT/LLM/TTS latency)
        └── services/
            ├── api.js           # REST client (STT, TTS, Voice Interact)
            └── voice.js         # Audio recording, playback, and instant barge-in manager
```

---

## 🎙️ Vāṇī Voice System Architecture (NARAD V7)

```
[ User Speaks into Microphone ]
               │
               ▼
[ Frontend Web Audio / MediaRecorder (WAV) ]
               │  POST /api/voice/interact
               ▼
┌─────────────────────────────────────────────────────────────┐
│                       NARAD BACKEND                         │
│                                                             │
│  1. Speech-to-Text:                                         │
│     faster-whisper (tiny, CPU int8)                         │
│     Latency: ~0.5s - 1.2s                                   │
│                                                             │
│  2. Language Detection:                                     │
│     Auto-identifies 'en' (English), 'hi' (Hindi),           │
│     or 'hinglish' (Mixed Hindi-English)                     │
│                                                             │
│  3. NARAD Intelligence Core:                                │
│     Enters the SAME pipeline as typed input:                │
│     - Fast Path / LLM Router                                │
│     - Krīya Tool Dispatcher (e.g. open Apple Music)         │
│     - Action Policy & Confirmation Matrix                   │
│                                                             │
│  4. Dynamic TTS Language Router:                            │
│     ┌───────────────────┬────────────────────────────────┐  │
│     │ Language          │ TTS Engine                     │  │
│     ├───────────────────┼────────────────────────────────┤  │
│     │ English           │ Chatterbox Multilingual (MPS)  │  │
│     │ Hindi             │ IndicVoice Kokoro (CPU)        │  │
│     │ Hinglish          │ Chatterbox (Fallback: Indic)   │  │
│     │ Fallback          │ Browser Web Speech             │  │
│     └───────────────────┴────────────────────────────────┘  │
│                                                             │
│  5. Return Payload:                                         │
│     - transcription                                         │
│     - detected_language                                     │
│     - response text                                         │
│     - audio_base64 (WAV)                                    │
│     - real telemetry (stt_s, llm_s, tts_s, total_s, device) │
└─────────────────────────────────────────────────────────────┘
               │
               ▼
[ Frontend Web Audio Player ] ────► [ Speaker ]
               │
               └─► [ Instant Barge-In / Interrupt on User Stop ]
```

---

## 🚀 Quick Start & Installation

### 1. System Dependencies (macOS)
IndicVoice requires `espeak-ng` for Indic grapheme-to-phoneme conversion:

```bash
brew install espeak-ng
```

### 2. Environment Configuration
Create `backend/.env` using `backend/.env.example` as a template:

```bash
cp backend/.env.example backend/.env
```

Configure your API keys in `backend/.env`:

```env
# Primary LLM Provider
GROQ_API_KEY=gsk_your_groq_api_key_here
NARAD_DEFAULT_PROVIDER=groq
NARAD_DEFAULT_MODEL=openai/gpt-oss-120b

# Vāṇī Local Voice Configuration
TTS_PROVIDER=chatterbox
TTS_LOCAL=true
TTS_DEVICE=auto   # 'auto' selects 'mps' on Apple Silicon, 'cuda' on Nvidia, or 'cpu'
```

### 3. Backend Setup & Virtual Environment

```bash
cd backend

# Use Python 3.10+ (Python 3.12 recommended)
python3.12 -m venv .venv
source .venv/bin/activate

# Install core dependencies
pip install -r requirements.txt

# Install Voice & TTS dependencies
pip install faster-whisper indicvoice indicg2p chatterbox-tts soundfile
```

### 4. Voice Models & Caches
- **faster-whisper**: Automatically downloads `tiny` model to `~/.cache/huggingface/hub/` on first use.
- **IndicVoice**:
  - Model weights: `backend/indic-voice/indicvoice-v1_0.pth` (Kokoro-82M).
  - Voice profiles: `backend/indic-voice/voices/hf_alpha.pt` (female), `hm_omega.pt` (male).
- **Chatterbox Multilingual**:
  - Loaded locally from snapshot in `~/.cache/huggingface/hub/models--ResembleAI--chatterbox/`.

### 5. Running NARAD

```bash
# Terminal 1: Backend Server
cd backend
source .venv/bin/activate
uvicorn app.main:app --port 8000 --host 127.0.0.1 --reload

# Terminal 2: Frontend Client
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## 🎙️ Enabling & Using Vāṇī Voice

1. **Activate Voice Mode**:
   - In the chat interface, click the **VĀṆĪ VOICE** toggle button in the bottom composer bar.
   - The HUD will display:
     `VĀṆĪ INPUT | LOCAL WHISPER | MIC: READY | STATUS: READY`
2. **Push to Speak**:
   - Click and hold **HOLD TO SPEAK** (or click to toggle recording).
   - Speak your query (e.g. `"Narad, what is the capital of India?"` or `"Narad, Apple Music chalao."`).
   - Release the button.
3. **Instant Barge-In (Interrupt)**:
   - While NARAD is speaking, an active **INTERRUPT (STOP)** button appears in the composer bar.
   - Click the button or say `"Stop"` to immediately halt playback and return to listening.
4. **Voice Diagnostics Modal**:
   - Click the **VĀṆĪ Config** button (waveform icon) to view active engine cards (`CHATTERBOX` on MPS, `INDICVOICE` on CPU, `LOCAL WHISPER`) and test sample synthesis prompts.

---

## 🔧 Troubleshooting & Platform Notes

### 1. Microphone Permissions on macOS
- Browser mic access: When prompted by the browser (`localhost:5173`), click **Allow**.
- System mic access: Check **macOS System Settings → Privacy & Security → Microphone** to verify your browser (Safari, Chrome, Arc, etc.) has permission.

### 2. Apple Silicon (MPS vs CPU) Detection
- **Chatterbox**: Employs PyTorch Metal Performance Shaders (`mps`) when available on Apple Silicon (`torch.backends.mps.is_available()`). Synthesis takes ~3.7s.
- **IndicVoice**: Kokoro-82M Indic G2P runs natively on Apple Silicon CPU in ~0.28s - 0.7s (extremely lightweight and ~7x faster than real-time).
- **faster-whisper**: Whisper `tiny` runs with `compute_type="int8"` on CPU for lowest latency (~0.5s - 1.2s).
- **Honest Telemetry**: The HUD displays exact runtime hardware (`DEVICE: MPS` or `DEVICE: CPU`).

---

## 🧪 Testing Vāṇī

Run the dedicated 12-test automated Vāṇī integration test suite:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v tests/test_v7_voice.py
```

### Verified Test Prompts:
1. **English Q&A**:
   - Prompt: `"What is the capital of India?"`
   - STT: Local Whisper → LLM: Groq → TTS: Chatterbox (`MPS`) → `"New Delhi is the capital of India."`
2. **Hindi Q&A**:
   - Prompt: `"नमस्ते, मैं नारद हूँ। मैं आपकी कैसे सहायता कर सकता हूँ?"`
   - STT: Local Whisper → TTS: IndicVoice (`CPU`) in ~0.3s.
3. **Voice Tool Command**:
   - Prompt: `"Narad, Apple Music chalao."`
   - STT: Local Whisper → Krīya: `open_application(Music)` → TTS: IndicVoice/Chatterbox → Apple Music opens and plays.
4. **Voice App Command**:
   - Prompt: `"Narad, Chrome kholo."`
   - STT: Local Whisper → Krīya: `open_application(Google Chrome)` → TTS confirms action.

### Testing Hugging Face Local AI (V7.1)
Run the dedicated 12-test automated Hugging Face Local AI test suite:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v tests/test_v71_local_ai.py
```

---

## 🔒 Security & Privacy

- **Local-First Voice**: Voice input and neural synthesis occur entirely on your local machine.
- **No Cloud Voice APIs**: No speech data is ever sent to third-party TTS/STT cloud endpoints.
- **Ephemeral Audio**: Generated audio bytes are streamed directly or stored in temporary system directories and immediately discarded.

---

## 🚀 Phase 2 Master Upgrade (Trimurti AI)

NARAD Phase 2 transforms the assistant into a resilient, production-oriented personal AI operating layer with zero fake success, rate-limit cooldown handling, deterministic micro-tasks, and offline capability.

### 1. Closed-Loop Execution Flow
```
USER 
  ↓
NARAD CORE (FastAPI + Sliding Window)
  ↓
INTENT CLASSIFICATION & TOKEN EFFICIENCY
  ↓
TASK ROUTER (CHAT, FAST, REASONING, CODING, VISION, TOOL, MEMORY, KNOWLEDGE)
  ↓
MODEL ROUTER
  ├── GROQ LPU (Primary low-latency conversational brain)
  ├── NVIDIA NIM (Deep reasoning & coding)
  ├── GOOGLE GEMINI (Multimodal vision & long context)
  ├── OPENROUTER (Universal fallback)
  └── OLLAMA (Local fast fallback / acceleration)
  ↓
TOOLS / COMPUTER AGENT / KNOWLEDGE / MEMORY
  ↓
OBSERVE (Trinetra screen capture / tool output verification)
  ↓
VERIFY (Zero Fake Success verification gate)
  ↓
RESPOND (SSE text stream, audio playback, HUD telemetry)
```

### 2. Centralized Capability Routing Policy
- **FAST_LOCAL**: Ollama (`qwen3.5:0.8b`) for simple greetings, lightweight formatting, text transformation.
- **GENERAL**: Groq → NVIDIA → Gemini → OpenRouter → Ollama fallback.
- **REASONING**: NVIDIA → Groq → OpenRouter (never routes deep reasoning to tiny local models).
- **CODING**: NVIDIA → Groq → OpenRouter.
- **VISION**: Gemini → OpenRouter → Local HuggingFace Vision slot.
- **LOCAL/PRIVATE**: Ollama → Local HuggingFace.

### 3. Provider Health & Cooldown Tracking
- **Rate Limit (429)**: Respects `Retry-After` header when provided; latches provider into rate-limited cooldown; automatically routes to next eligible provider.
- **Timeouts & 5xx**: Retries safely within task limits, then fails over.
- **Auth Errors (401/403)**: Latches permanently for process lifetime without infinite retry loops.

### 4. Local-First Deterministic Micro-Tasks
Zero LLM tokens and <5ms response time for deterministic queries:
- Current local & world time: `what time is it`, `current time in Tokyo`
- Date queries: `today's date`
- Safe math / calculator: `what is 45 * 20`
- Git status inspection: `git status`, `current branch`
- Installed local models listing: `list ollama models`
- Service ports & process checks: `port status`

### 5. Self-Diagnostics & Project Intelligence
- **NARAD HEALTH**: Diagnoses all 16 core subsystems (FastAPI, SQLite, Frontend, Ollama, Local Model, Groq, NVIDIA, Gemini, OpenRouter, Voice, Trinetra, Kriya, Manthan, Smṛti, Knowledge, Task Engine) returning **GREEN / YELLOW / RED** with exact reasons.
- **PROJECT STATUS**: Concise status overview of backend, frontend build, test results, Ollama daemon, and Git working tree.

### 6. Autonomy Levels & Safety Boundaries
- **Level 0 (Read-Only)**: System queries, time, calculator, screen observation. Always permitted.
- **Level 1 (Safe Interaction)**: Launching apps, opening URLs, focusing windows.
- **Level 2 (Supervised Mutations)**: Creating/editing sandboxed files, staging code. Requires user approval in Supervised mode.
- **Level 3 (High-Impact Actions)**: File deletion, development command execution. Always requires confirmation.
- **Level 4 (Dangerous / Destructive)**: Sudo, arbitrary shell commands, raw root modification. **Permanently blocked**.

### 7. Running Phase 2 Tests
```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -v tests/test_phase2_master_upgrade.py
```
*All 17 Phase 2 unit & integration tests pass with 100% verification.*


