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
        active_provider: 'gemini',
        active_model: 'gemini-2.5-flash',
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
   */
  async sendChat(message, chatId = null, provider = null, model = null) {
    const res = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        chat_id: chatId,
        provider,
        model
      }),
    });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server error (HTTP ${res.status})`);
    }
    return await res.json();
  },

  async sendMessage(chatId, content, providerId = null, model = null) {
    return this.sendChat(content, chatId, providerId, model);
  }
};
