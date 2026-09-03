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
        active_provider: 'none'
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

  async sendMessage(chatId, content, providerId = null, model = null) {
    const res = await fetch(`${BASE_URL}/chats/${chatId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, provider_id: providerId, model }),
    });
    if (!res.ok) throw new Error('Failed to send message');
    return await res.json();
  },
};
