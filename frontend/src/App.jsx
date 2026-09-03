import React, { useState, useEffect } from 'react';
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
      setMessages(chatDetails.messages || []);
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

  const handleSendMessage = async (content) => {
    let currentChatId = activeChatId;

    // If no chat selected, create one first
    if (!currentChatId) {
      try {
        const newChat = await api.createChat('New Briefing');
        setChats((prev) => [newChat, ...prev]);
        currentChatId = newChat.id;
        setActiveChatId(newChat.id);
      } catch (err) {
        console.error('Failed to auto-create chat:', err);
        return;
      }
    }

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
      const res = await api.sendMessage(currentChatId, content);
      
      // Update message stream with persisted messages
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== tempUserMsg.id),
        res.user_message,
        res.assistant_message
      ]);

      // Refresh chat list to update title and order
      loadChats();
    } catch (err) {
      console.error('Failed to transmit message:', err);
    } finally {
      setIsSending(false);
    }
  };

  const activeChat = chats.find((c) => c.id === activeChatId);

  return (
    <div className="flex h-screen w-screen bg-narad-bg overflow-hidden text-narad-text select-none">
      {/* 1. Left Sidebar */}
      <LeftSidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={setActiveChatId}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        isHealthy={healthData?.status === 'online'}
      />

      {/* 2. Center Conversation Interface */}
      <main className="flex-1 h-full flex flex-col min-w-0">
        <ChatContainer
          chat={activeChat}
          messages={messages}
          isSending={isSending}
          onSendMessage={handleSendMessage}
          activeProvider={healthData?.active_provider}
        />
      </main>

      {/* 3. Right Sidebar (HUD & Telemetry) */}
      <RightSidebar
        healthData={healthData}
        onRefreshHealth={loadHealth}
      />
    </div>
  );
}
