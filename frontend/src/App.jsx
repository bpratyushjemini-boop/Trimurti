import React, { useState, useEffect, useCallback } from 'react';
import LeftSidebar from './components/sidebar/LeftSidebar';
import ChatContainer from './components/chat/ChatContainer';
import RightSidebar from './components/hud/RightSidebar';
import { api } from './services/api';

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isSending, setIsSending] = useState(false);
  const [healthData, setHealthData] = useState(null);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);
  const [draftPrompt, setDraftPrompt] = useState('');
  const [lastTelemetry, setLastTelemetry] = useState(null);

  // Load initial health & chat list
  useEffect(() => {
    loadHealth();
    loadChats();
  }, []);

  // When active chat changes, load its messages
  useEffect(() => {
    if (activeChatId) {
      loadChatMessages(activeChatId);
    } else {
      setMessages([]);
    }
  }, [activeChatId]);

  const loadHealth = async () => {
    const data = await api.getHealth();
    setHealthData(data);
  };

  const loadChats = async () => {
    try {
      const data = await api.getChats();
      setChats(data);
      if (data.length > 0 && !activeChatId) {
        setActiveChatId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load chats:', err);
    }
  };

  const loadChatMessages = async (chatId) => {
    try {
      const chatDetails = await api.getChat(chatId);
      const loadedMessages = chatDetails.messages || [];
      setMessages(loadedMessages);

      // Extract telemetry from last assistant message if available
      const lastAssistant = [...loadedMessages].reverse().find((m) => m.role === 'assistant');
      if (lastAssistant && lastAssistant.metadata_json) {
        try {
          const meta = typeof lastAssistant.metadata_json === 'string'
            ? JSON.parse(lastAssistant.metadata_json)
            : lastAssistant.metadata_json;
          setLastTelemetry(meta);
        } catch {
          // ignore
        }
      }
    } catch (err) {
      console.error('Failed to load messages for chat:', chatId, err);
    }
  };

  const handleNewChat = async () => {
    try {
      const newChat = await api.createChat('New Briefing');
      setChats((prev) => [newChat, ...prev]);
      setActiveChatId(newChat.id);
      setMessages([]);
      setDraftPrompt('');
    } catch (err) {
      console.error('Failed to create new chat:', err);
    }
  };

  const handleDeleteChat = async (chatId) => {
    try {
      await api.deleteChat(chatId);
      const remaining = chats.filter((c) => c.id !== chatId);
      setChats(remaining);
      if (activeChatId === chatId) {
        setActiveChatId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch (err) {
      console.error('Failed to delete chat:', err);
    }
  };

  const handleSelectPrompt = (promptText) => {
    setDraftPrompt(promptText);
  };

  const handleClearDraftPrompt = useCallback(() => {
    setDraftPrompt('');
  }, []);

  const handleToggleRightPanel = () => {
    setIsRightPanelOpen((prev) => !prev);
  };

  const handleSendMessage = async (content) => {
    let currentChatId = activeChatId;

    // Optimistically append user message to UI
    const tempUserMsg = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsSending(true);

    try {
      // Dispatch via real /api/chat endpoint
      const res = await api.sendChat(content, currentChatId);

      // Auto-select session if newly created
      if (!currentChatId && res.chat_id) {
        currentChatId = res.chat_id;
        setActiveChatId(res.chat_id);
      }

      // Record actual telemetry
      const telemetryPayload = {
        provider: res.provider,
        model: res.model,
        latency_ms: res.latency_ms,
        status: res.status
      };
      setLastTelemetry(telemetryPayload);

      // Update message stream with persisted SQLite records
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempUserMsg.id),
        res.user_message || tempUserMsg,
        res.assistant_message || {
          id: `ast-${Date.now()}`,
          role: 'assistant',
          content: res.response,
          metadata_json: JSON.stringify(telemetryPayload),
          created_at: new Date().toISOString()
        }
      ]);

      // Refresh chat list to update title and order
      loadChats();
      loadHealth();
    } catch (err) {
      console.error('Failed to transmit directive:', err);
      // Friendly error handling
      const errorPayload = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ **NARAD Core Communication Failure:** ${err.message || 'Unable to connect to local server.'}`,
        created_at: new Date().toISOString(),
        metadata_json: JSON.stringify({
          provider: 'error',
          model: 'none',
          status: 'error',
          latency_ms: 0
        })
      };
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempUserMsg.id),
        tempUserMsg,
        errorPayload
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const activeChat = chats.find((c) => c.id === activeChatId);
  const activeModel = lastTelemetry?.model || healthData?.active_model || 'gemini-2.5-flash';
  const activeProvider = lastTelemetry?.provider || healthData?.active_provider || 'gemini';

  return (
    <div className="flex h-screen w-screen bg-narad-bg overflow-hidden text-narad-text select-none font-sans">
      {/* 1. Left Sidebar */}
      <LeftSidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={setActiveChatId}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        isHealthy={healthData?.status === 'online'}
      />

      {/* 2. Center Conversation Interface (Visually Dominant Workspace) */}
      <main className="flex-1 h-full flex flex-col min-w-0 relative">
        <ChatContainer
          chat={activeChat}
          messages={messages}
          isSending={isSending}
          onSendMessage={handleSendMessage}
          activeProvider={activeProvider}
          activeModel={activeModel}
          draftPrompt={draftPrompt}
          onSelectPrompt={handleSelectPrompt}
          onClearDraftPrompt={handleClearDraftPrompt}
          onToggleRightPanel={handleToggleRightPanel}
          isRightPanelOpen={isRightPanelOpen}
        />
      </main>

      {/* 3. Right Sidebar (HUD & Telemetry Information Panel) */}
      <RightSidebar
        healthData={healthData}
        onRefreshHealth={loadHealth}
        messages={messages}
        onSelectPrompt={handleSelectPrompt}
        isOpen={isRightPanelOpen}
        lastTelemetry={lastTelemetry}
      />
    </div>
  );
}
