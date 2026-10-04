const BASE_URL = '/api';

export const api = {
  async getHealth() {
    try {
      const res = await fetch(`${BASE_URL}/health`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('Backend offline or unreachable:', err);
      return {
        status: 'offline',
        system: 'NARAD',
        version: '0.1.0',
        database: 'disconnected',
        active_provider: 'groq',
        active_model: 'openai/gpt-oss-120b',
        is_configured: false
      };
    }
  },

  async getChats() {
    const res = await fetch(`${BASE_URL}/chats`);
    if (!res.ok) throw new Error('Failed to fetch chat sessions');
    return await res.json();
  },

  async createChat(title = 'New Briefing') {
    const res = await fetch(`${BASE_URL}/chats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error('Failed to create chat');
    return await res.json();
  },

  async getChat(chatId) {
    const res = await fetch(`${BASE_URL}/chats/${chatId}`);
    if (!res.ok) throw new Error('Failed to fetch chat details');
    return await res.json();
  },

  async deleteChat(chatId) {
    const res = await fetch(`${BASE_URL}/chats/${chatId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete chat');
    return true;
  },

  /**
   * Primary chat transmission via POST /api/chat
   * Automatically persists to SQLite and returns real model metadata & latency.
   * Accepts optional abortSignal to immediately cancel in-flight requests.
   */
  async sendChat(message, chatId = null, provider = null, model = null, isVoice = false, abortSignal = null) {
    const res = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: abortSignal,
      body: JSON.stringify({
        message,
        chat_id: chatId,
        provider,
        model,
        is_voice: isVoice
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server error (HTTP ${res.status})`);
    }
    return await res.json();
  },

  /**
   * Real-time SSE token and turn-taking streaming via POST /api/chat/stream
   * Yields thinking, tool_execution, token, done, cancelled, error events.
   */
  async streamChat(message, chatId = null, provider = null, model = null, isVoice = false, onEvent, abortSignal = null) {
    const res = await fetch(`${BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: abortSignal,
      body: JSON.stringify({
        message,
        chat_id: chatId,
        provider,
        model,
        is_voice: isVoice
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server error (HTTP ${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop(); // keep remainder

      for (const block of lines) {
        const trimmed = block.trim();
        if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (onEvent) onEvent(data);
          } catch (e) {
            console.warn('[SSE] Parse warning:', e);
          }
        }
      }
    }
  },

  async sendMessage(chatId, content, providerId = null, model = null) {
    return this.sendChat(content, chatId, providerId, model);
  },

  // =========================================================================
  // Knowledge Base Subsystem (V2.2)
  // =========================================================================

  async getKnowledgeDocuments() {
    const res = await fetch(`${BASE_URL}/knowledge/documents`);
    if (!res.ok) throw new Error('Failed to fetch knowledge documents');
    return await res.json();
  },

  async uploadKnowledgeDocument(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/knowledge/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Upload failed with status ${res.status}`);
    }
    return await res.json();
  },

  async deleteKnowledgeDocument(docId) {
    const res = await fetch(`${BASE_URL}/knowledge/documents/${docId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Delete failed with status ${res.status}`);
    }
    return await res.json();
  },

  async searchKnowledge(query, maxResults = 4) {
    const res = await fetch(`${BASE_URL}/knowledge/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, max_results: maxResults }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Search failed with status ${res.status}`);
    }
    return await res.json();
  },

  // =========================================================================
  // NARAD V4 Computer Agent APIs
  // =========================================================================

  async getAgentState() {
    try {
      const res = await fetch(`${BASE_URL}/agent/state`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return await res.json();
    } catch (err) {
      return {
        state: 'IDLE',
        active_task_id: null,
        active_task_prompt: null,
        current_action: null,
        pending_confirmation: null,
        dry_run: false,
        is_cancelled: false
      };
    }
  },

  async getAgentTools() {
    try {
      const res = await fetch(`${BASE_URL}/agent/tools`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('Failed to fetch agent tools:', err);
      return { tools: [], total: 0 };
    }
  },

  async executeAgentTask(prompt, dryRun = false, confirmationId = null) {
    const res = await fetch(`${BASE_URL}/agent/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        dry_run: dryRun,
        confirmation_id: confirmationId
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Agent task execution failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  async confirmAction(confirmationId, decision, taskId = null) {
    const res = await fetch(`${BASE_URL}/agent/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        confirmation_id: confirmationId,
        decision,
        task_id: taskId
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Confirmation submission failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  async stopAgent() {
    const res = await fetch(`${BASE_URL}/agent/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) throw new Error('Emergency stop failed');
    return await res.json();
  },

  async resetAgent() {
    const res = await fetch(`${BASE_URL}/agent/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) throw new Error('Agent reset failed');
    return await res.json();
  },

  async getAgentHistory(limit = 20) {
    const res = await fetch(`${BASE_URL}/agent/history?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch agent history');
    return await res.json();
  },

  async getPendingConfirmations() {
    const res = await fetch(`${BASE_URL}/agent/confirmations`);
    if (!res.ok) throw new Error('Failed to fetch pending confirmations');
    return await res.json();
  },

  getLatestScreenshotUrl() {
    return `${BASE_URL}/agent/screenshot/latest?t=${Date.now()}`;
  },

  async queryVision(question, imageRef = null) {
    const res = await fetch(`${BASE_URL}/agent/vision/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, image_ref: imageRef })
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Vision query failed (HTTP ${res.status})`);
    }
    return await res.json();
  },

  // =========================================================================
  // NARAD V6 — Autonomous Task Engine Subsystem
  // =========================================================================

  async getAutonomyMode() {
    const res = await fetch(`${BASE_URL}/agent/autonomy/mode`);
    if (!res.ok) throw new Error('Failed to fetch autonomy mode');
    return await res.json();
  },

  async setAutonomyMode(mode) {
    const res = await fetch(`${BASE_URL}/agent/autonomy/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to set autonomy mode (HTTP ${res.status})`);
    }
    return await res.json();
  },

  async createAutonomousTask(objective, dryRun = false, autonomyMode = null) {
    const res = await fetch(`${BASE_URL}/agent/task/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        objective,
        dry_run: dryRun,
        autonomy_mode: autonomyMode,
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Failed to create autonomous task (HTTP ${res.status})`);
    }
    return await res.json();
  },

  async getActiveAutonomousTask() {
    const res = await fetch(`${BASE_URL}/agent/task/active`);
    if (!res.ok) throw new Error('Failed to fetch active task');
    return await res.json();
  },

  async listAutonomousTasks(limit = 10) {
    const res = await fetch(`${BASE_URL}/agent/task/list?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to list autonomous tasks');
    return await res.json();
  },

  async getAutonomousTaskDetails(taskId) {
    const res = await fetch(`${BASE_URL}/agent/task/${taskId}`);
    if (!res.ok) throw new Error(`Failed to fetch task ${taskId}`);
    return await res.json();
  },

  async pauseAutonomousTask(taskId) {
    const res = await fetch(`${BASE_URL}/agent/task/${taskId}/pause`, { method: 'POST' });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to pause task');
    }
    return await res.json();
  },

  async resumeAutonomousTask(taskId) {
    const res = await fetch(`${BASE_URL}/agent/task/${taskId}/resume`, { method: 'POST' });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to resume task');
    }
    return await res.json();
  },

  async cancelAutonomousTask(taskId) {
    const res = await fetch(`${BASE_URL}/agent/task/${taskId}/cancel`, { method: 'POST' });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to cancel task');
    }
    return await res.json();
  },

  async skipAutonomousTaskStep(taskId, stepId = null) {
    const res = await fetch(`${BASE_URL}/agent/task/${taskId}/skip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step_id: stepId }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to skip step');
    }
    return await res.json();
  },

  async retryAutonomousTaskStep(taskId, stepId = null) {
    const res = await fetch(`${BASE_URL}/agent/task/${taskId}/retry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step_id: stepId }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Failed to retry step');
    }
    return await res.json();
  },

  // =========================================================================
  // Vāṇī Local STT & Two-Way Voice Pipeline Endpoints
  // =========================================================================

  async getSTTStatus() {
    try {
      const res = await fetch(`${BASE_URL}/stt/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('[Vāṇī API] STT status fetch failed:', err);
      return {
        engine: 'local_whisper',
        installed: false,
        model_loaded: false,
        ready: false,
        device: 'cpu',
        supported_languages: ['en', 'hi', 'hinglish', 'auto'],
        error: 'Backend STT unreachable',
        active_fallback: true
      };
    }
  },

  async transcribeAudio(audioBlob, language = 'auto') {
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.wav');
    formData.append('language', language);

    const res = await fetch(`${BASE_URL}/stt/transcribe`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail?.message || errJson.detail || `STT HTTP ${res.status}`);
    }
    return await res.json();
  },

  async voiceInteract(audioBlob, chatId = null, provider = null, model = null, abortSignal = null) {
    const formData = new FormData();
    formData.append('audio_file', audioBlob, 'recording.wav');
    if (chatId) formData.append('chat_id', chatId);
    if (provider) formData.append('provider', provider);
    if (model) formData.append('model', model);

    const res = await fetch(`${BASE_URL}/voice/interact`, {
      method: 'POST',
      signal: abortSignal,
      body: formData,
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail?.message || errJson.detail || `Voice Interact HTTP ${res.status}`);
    }
    return await res.json();
  },

  // =========================================================================
  // Vāṇī Local TTS (Chatterbox Multilingual & IndicVoice) Endpoints
  // =========================================================================

  async getTTSStatus() {
    try {
      const res = await fetch(`${BASE_URL}/tts/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('[Vāṇī API] TTS status fetch failed, using browser fallback:', err);
      return {
        provider: 'chatterbox',
        installed: false,
        model_loaded: false,
        ready: false,
        mode: 'local',
        device: 'cpu',
        supported_languages: ['en', 'hi', 'hinglish'],
        error: 'Backend TTS status unreachable',
        active_fallback: true,
        fallback_provider: 'browser_speech_synthesis'
      };
    }
  },

  async getTTSEngines() {
    try {
      const res = await fetch(`${BASE_URL}/tts/engines`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('[Vāṇī API] Failed to fetch individual TTS engines:', err);
      return {};
    }
  },

  async synthesizeTTS(text, language = 'auto') {
    const res = await fetch(`${BASE_URL}/tts/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language }),
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      const reason = errJson.detail?.reason || errJson.detail?.message || `HTTP ${res.status}`;
      throw new Error(reason);
    }
    return await res.blob();
  },

  async testTTS(sampleKey = 'english') {
    const res = await fetch(`${BASE_URL}/tts/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sample_key: sampleKey }),
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail?.message || errJson.detail || `HTTP ${res.status}`);
    }
    return await res.blob();
  },

  async getTTSSamples() {
    const res = await fetch(`${BASE_URL}/tts/samples`);
    if (!res.ok) return {};
    return await res.json();
  },

  // =========================================================================
  // Hugging Face Local AI Subsystem (V7.1)
  // =========================================================================

  async getLocalAIStatus() {
    try {
      const res = await fetch(`${BASE_URL}/local-ai/status`);
      if (!res.ok) return null;
      return await res.json();
    } catch (err) {
      console.warn('[Local AI API] Failed to fetch status:', err);
      return null;
    }
  },

  async generateLocalAI(prompt, maxTokens = 128) {
    const res = await fetch(`${BASE_URL}/local-ai/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, max_tokens: maxTokens }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Local AI generation error: ${res.status}`);
    }
    return await res.json();
  },

  async preloadLocalAI() {
    const res = await fetch(`${BASE_URL}/local-ai/load`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Preload failed with status ${res.status}`);
    }
    return await res.json();
  },

  async getRuntimeTruth(sessionId = null) {
    try {
      const url = sessionId ? `${BASE_URL}/runtime/truth?session_id=${sessionId}` : `${BASE_URL}/runtime/truth`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('[RuntimeTruth API] Failed to fetch runtime truth:', err);
      return null;
    }
  },

  async getRuntimeReport(sessionId = null) {
    try {
      const url = sessionId ? `${BASE_URL}/runtime/report?session_id=${sessionId}` : `${BASE_URL}/runtime/report`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return await res.text();
    } catch (err) {
      console.warn('[RuntimeTruth API] Failed to fetch runtime report:', err);
      return null;
    }
  },

  // =========================================================================
  // Smṛti 3.0 Memory APIs
  // =========================================================================

  async getMemories({ category = null, search = null, status = 'ACTIVE', limit = 50 } = {}) {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (search) params.append('search', search);
    if (status) params.append('status', status);
    if (limit) params.append('limit', limit);
    const res = await fetch(`${BASE_URL}/memory?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch memories');
    return await res.json();
  },

  async getMemoryStatus() {
    try {
      const res = await fetch(`${BASE_URL}/memory/status`);
      if (!res.ok) throw new Error('Failed to fetch memory status');
      return await res.json();
    } catch (err) {
      console.warn('[Smriti API] Status fetch notice:', err);
      return {
        enabled: true,
        backend: 'sqlite',
        persistent: true,
        total_memories: 0,
        active_memories: 0,
        categories: {},
        subsystem_status: 'ONLINE'
      };
    }
  },

  async searchMemories(query, limit = 5) {
    const params = new URLSearchParams({ query, limit });
    const res = await fetch(`${BASE_URL}/memory/search?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to search memories');
    return await res.json();
  },

  async getMemory(id) {
    const res = await fetch(`${BASE_URL}/memory/${id}`);
    if (!res.ok) throw new Error('Failed to fetch memory record');
    return await res.json();
  },

  async saveMemory({ key, value, category = 'FACTS', importance = 0.5, confidence = 1.0 }) {
    const res = await fetch(`${BASE_URL}/memory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value, category, importance, confidence })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to save memory');
    }
    return await res.json();
  },

  async updateMemory(id, { value, category, importance, status }) {
    const res = await fetch(`${BASE_URL}/memory/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value, category, importance, status })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update memory');
    }
    return await res.json();
  },

  async deleteMemory(id) {
    const res = await fetch(`${BASE_URL}/memory/${id}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete memory');
    return await res.json();
  },

  async forgetMemory(key) {
    const res = await fetch(`${BASE_URL}/memory/forget`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to forget memory');
    }
    return await res.json();
  },

  async explainMemory(query) {
    const res = await fetch(`${BASE_URL}/memory/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    if (!res.ok) throw new Error('Failed to explain memory');
    return await res.json();
  },
};

export const naradApi = api;

