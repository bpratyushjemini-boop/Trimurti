import React, { useState, useEffect, useCallback, useRef } from 'react';
import LeftSidebar from './components/sidebar/LeftSidebar';
import ChatContainer from './components/chat/ChatContainer';
import RightSidebar from './components/hud/RightSidebar';
import KnowledgeBaseModal from './components/knowledge/KnowledgeBaseModal';
import SmritiMemoryModal from './components/knowledge/SmritiMemoryModal';
import VoiceSettingsModal from './components/chat/VoiceSettingsModal';
import AgentPermissionModal from './components/agent/AgentPermissionModal';
import AgentToolsModal from './components/agent/AgentToolsModal';
import { api } from './services/api';
import { vaaniService } from './services/voice';

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isSending, setIsSending] = useState(false);
  const [healthData, setHealthData] = useState(null);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(true);
  const [draftPrompt, setDraftPrompt] = useState('');
  const [lastTelemetry, setLastTelemetry] = useState(null);
  const [runtimeTruth, setRuntimeTruth] = useState(null);
  const [isKnowledgeModalOpen, setIsKnowledgeModalOpen] = useState(false);
  const [knowledgeDocCount, setKnowledgeDocCount] = useState(0);
  const [isMemoryModalOpen, setIsMemoryModalOpen] = useState(false);
  const [memoryCount, setMemoryCount] = useState(0);
  const [isAgentToolsModalOpen, setIsAgentToolsModalOpen] = useState(false);
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [voiceState, setVoiceState] = useState('IDLE');
  
  // V4 Computer Agent & Dry Run State
  const [isDryRun, setIsDryRun] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const [agentTelemetry, setAgentTelemetry] = useState({
    state: 'IDLE',
    current_action: null,
    pending_confirmation: null,
    dry_run: false
  });

  // V3.2 Turn-Taking & Cancellation State
  // 'IDLE' | 'LISTENING' | 'THINKING' | 'TOOL_EXECUTION' | 'GENERATING' | 'SPEAKING' | 'ERROR' | 'CANCELLED'
  const [interactionState, setInteractionState] = useState('IDLE');
  const [currentTool, setCurrentTool] = useState(null);
  const [isVoiceSettingsOpen, setIsVoiceSettingsOpen] = useState(false);
  const abortControllerRef = useRef(null);

  // Subscribe to Vāṇī Voice State
  useEffect(() => {
    const unsub = vaaniService.onStateChange((st) => {
      setVoiceState(st);
      if (st === 'LISTENING') {
        setInteractionState('LISTENING');
      } else if (st === 'SPEAKING') {
        setInteractionState('SPEAKING');
      } else if (st === 'IDLE' && !isSending) {
        setInteractionState('IDLE');
      }
    });
    return () => unsub();
  }, [isSending]);

  // Load initial health & chat list
  useEffect(() => {
    loadHealth();
    loadChats();
    loadKnowledgeCount();
    loadMemoryCount();
    
    // Check initial saved voice settings
    const settings = vaaniService.getSettings();
    if (settings?.voiceMode) {
      setIsVoiceMode(true);
    }
  }, []);

  // Poll Computer Agent State for live telemetry and confirmation requests
  useEffect(() => {
    let isMounted = true;
    const pollAgent = async () => {
      try {
        const st = await api.getAgentState();
        if (!isMounted) return;
        setAgentTelemetry(st);
        if (st.pending_confirmation) {
          setPendingConfirmation(st.pending_confirmation);
        } else {
          setPendingConfirmation(null);
        }
      } catch {
        // ignore network hiccups
      }
    };

    pollAgent();
    const interval = setInterval(pollAgent, 2000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleEmergencyStop = async () => {
    try {
      await api.stopAgent();
      handleCancelOperation();
      const st = await api.getAgentState();
      setAgentTelemetry(st);
    } catch (err) {
      console.error('Failed to emergency stop agent:', err);
    }
  };

  const handleConfirmDecision = async (confirmationId, decision, taskId = null) => {
    // Clear pending confirmation immediately to close modal and prevent double-clicks
    setPendingConfirmation(null);
    try {
      await api.confirmAction(confirmationId, decision, taskId);
      const st = await api.getAgentState();
      setAgentTelemetry(st);
    } catch (err) {
      console.error('Failed to submit confirmation decision:', err);
    }
  };

  // When active chat changes, load its messages
  useEffect(() => {
    if (activeChatId) {
      loadChatMessages(activeChatId);
    } else {
      setMessages([]);
    }
  }, [activeChatId]);

  const loadHealth = async () => {
    try {
      const [data, rTruth] = await Promise.all([
        api.getHealth(),
        api.getRuntimeTruth(activeChatId),
      ]);
      setHealthData(data);
      if (rTruth) {
        setRuntimeTruth(rTruth);
      } else if (data?.runtime_truth) {
        setRuntimeTruth(data.runtime_truth);
      }
    } catch (err) {
      console.warn('Failed to load health or runtime truth:', err);
    }
  };

  const loadKnowledgeCount = async () => {
    try {
      const data = await api.getKnowledgeDocuments();
      setKnowledgeDocCount(data.count || data.documents?.length || 0);
    } catch (err) {
      console.warn('Failed to load knowledge count:', err);
    }
  };

  const loadMemoryCount = async () => {
    try {
      const data = await api.getMemoryStatus();
      setMemoryCount(data.total_memories || 0);
    } catch (err) {
      console.warn('Failed to load memory count:', err);
    }
  };

  const loadChats = async () => {
    try {
      const data = await api.getChats();
      setChats(data);
      const savedChatId = localStorage.getItem('narad_active_chat_id');
      if (savedChatId && data.some((c) => c.id === savedChatId)) {
        setActiveChatId(savedChatId);
      } else if (data.length > 0 && !activeChatId) {
        setActiveChatId(data[0].id);
        localStorage.setItem('narad_active_chat_id', data[0].id);
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

  const handleSelectChat = (chatId) => {
    setActiveChatId(chatId);
    if (chatId) {
      localStorage.setItem('narad_active_chat_id', chatId);
    } else {
      localStorage.removeItem('narad_active_chat_id');
    }
  };

  const handleNewChat = async () => {
    try {
      const newChat = await api.createChat('New Briefing');
      setChats((prev) => [newChat, ...prev]);
      setActiveChatId(newChat.id);
      localStorage.setItem('narad_active_chat_id', newChat.id);
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
        const nextId = remaining.length > 0 ? remaining[0].id : null;
        setActiveChatId(nextId);
        if (nextId) {
          localStorage.setItem('narad_active_chat_id', nextId);
        } else {
          localStorage.removeItem('narad_active_chat_id');
        }
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

  const handleToggleVoiceMode = () => {
    setIsVoiceMode((prev) => {
      const next = !prev;
      vaaniService.saveSettings({ voiceMode: next });
      if (!next) {
        vaaniService.stopSpeaking();
        vaaniService.stopListening();
        setInteractionState('IDLE');
      }
      return next;
    });
  };

  // Immediate interruption and cancellation of any ongoing operation
  const handleCancelOperation = useCallback(() => {
    // 1. Abort in-flight network request
    if (abortControllerRef.current) {
      try {
        abortControllerRef.current.abort();
      } catch (e) {
        // ignore
      }
      abortControllerRef.current = null;
    }

    // 2. Halt any speech synthesis or recognition immediately
    vaaniService.halt();

    // 3. Update turn-taking state to CANCELLED, then revert to IDLE
    setIsSending(false);
    setCurrentTool(null);
    setInteractionState('CANCELLED');

    setTimeout(() => {
      setInteractionState('IDLE');
    }, 1200);
  }, []);

  const handleSendMessage = async (content) => {
    // Stop any ongoing speech playback before initiating next turn
    vaaniService.stopSpeaking();

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
    setInteractionState('THINKING');
    setCurrentTool(null);

    // Setup fresh AbortController
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      // Dispatch via real /api/chat endpoint with abortSignal support
      const res = await api.sendChat(
        content,
        currentChatId,
        null,
        null,
        isVoiceMode,
        controller.signal
      );

      // Auto-select session if newly created
      if (!currentChatId && res.chat_id) {
        currentChatId = res.chat_id;
        setActiveChatId(res.chat_id);
        localStorage.setItem('narad_active_chat_id', res.chat_id);
      }

      // Check for tools executed
      const executedTools = res.tools_executed || [];
      if (executedTools.length > 0) {
        setCurrentTool(executedTools[0].tool_name || executedTools[0].name || 'kriya');
      }

      // Record actual telemetry
      const telemetryPayload = {
        provider: res.provider,
        model: res.model,
        latency_ms: res.latency_ms,
        status: res.status,
        fallback: res.fallback,
        fallback_path: res.fallback_path,
        fallback_reason: res.fallback_reason,
        route_reason: res.route_reason,
        tools_executed: res.tools_executed
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

      // VĀṆĪ Voice Output: Auto-speak response if Voice Mode is active OR autoSpeak is enabled
      const voiceSettings = vaaniService.getSettings();
      const shouldSpeak = (isVoiceMode || voiceSettings.autoSpeak) && res.response && res.status !== 'error' && res.status !== 'service_unavailable';

      if (shouldSpeak) {
        setInteractionState('SPEAKING');
        vaaniService.speak(res.response, {
          onStart: () => setInteractionState('SPEAKING'),
          onEnd: () => setInteractionState('IDLE'),
          onError: () => setInteractionState('IDLE')
        });
      } else {
        setInteractionState('IDLE');
      }

      // Refresh chat list to update title and order
      loadChats();
      loadHealth();
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('[NARAD] Request cancelled by user.');
        handleCancelOperation();
        return;
      }

      console.error('Failed to transmit directive:', err);
      vaaniService.stopSpeaking();
      setInteractionState('ERROR');

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

      setTimeout(() => {
        setInteractionState('IDLE');
      }, 3000);
    } finally {
      setIsSending(false);
      abortControllerRef.current = null;
    }
  };

  const handleVoiceInteraction = async (audioBlob) => {
    vaaniService.stopSpeaking();

    let currentChatId = activeChatId;
    setIsSending(true);
    setInteractionState('PROCESSING');
    setCurrentTool(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await api.voiceInteract(
        audioBlob,
        currentChatId,
        null,
        null,
        controller.signal
      );

      if (!currentChatId && res.chat_id) {
        currentChatId = res.chat_id;
        setActiveChatId(res.chat_id);
        localStorage.setItem('narad_active_chat_id', res.chat_id);
      }

      const executedTools = res.tools_executed || [];
      if (executedTools.length > 0) {
        setCurrentTool(executedTools[0].tool_name || executedTools[0].name || executedTools[0].tool || 'kriya');
      }

      const telemetryPayload = {
        provider: res.provider,
        model: res.model,
        latency_ms: Math.round((res.telemetry?.total_latency || 0) * 1000),
        status: 'success',
        tools_executed: res.tools_executed,
        stt_engine: res.telemetry?.stt_engine,
        stt_latency: res.telemetry?.stt_latency,
        llm_engine: res.telemetry?.llm_engine,
        llm_latency: res.telemetry?.llm_latency,
        tts_engine: res.telemetry?.tts_engine,
        tts_device: res.telemetry?.tts_device,
        tts_latency: res.telemetry?.tts_latency,
        total_latency: res.telemetry?.total_latency,
        detected_language: res.detected_language,
        device: res.telemetry?.device
      };
      setLastTelemetry(telemetryPayload);

      setMessages((prev) => [
        ...prev,
        res.user_message || {
          id: `usr-${Date.now()}`,
          role: 'user',
          content: res.transcription,
          created_at: new Date().toISOString()
        },
        res.assistant_message || {
          id: `ast-${Date.now()}`,
          role: 'assistant',
          content: res.response,
          metadata_json: JSON.stringify(telemetryPayload),
          created_at: new Date().toISOString()
        }
      ]);

      if (res.audio_base64) {
        setInteractionState('SPEAKING');
        await vaaniService.playBase64Audio(res.audio_base64, res.audio_format || 'wav');
      } else {
        setInteractionState('IDLE');
      }

      loadChats();
      loadHealth();
    } catch (err) {
      if (err.name === 'AbortError') {
        handleCancelOperation();
        return;
      }
      console.error('Voice interaction failed:', err);
      vaaniService.stopSpeaking();
      setInteractionState('ERROR');
      setTimeout(() => setInteractionState('IDLE'), 3000);
    } finally {
      setIsSending(false);
      abortControllerRef.current = null;
    }
  };

  const activeChat = chats.find((c) => c.id === activeChatId);
  const activeModel = lastTelemetry?.model || healthData?.active_model || 'openai/gpt-oss-120b';
  const activeProvider = lastTelemetry?.provider || healthData?.active_provider || 'groq';

  return (
    <div className="flex h-screen w-screen bg-narad-bg overflow-hidden text-narad-text select-none font-sans">
      {/* 1. Left Sidebar */}
      <LeftSidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        isHealthy={healthData?.status === 'online'}
        onOpenKnowledgeBase={() => setIsKnowledgeModalOpen(true)}
        knowledgeDocCount={knowledgeDocCount}
        onOpenSmritiMemory={() => setIsMemoryModalOpen(true)}
        memoryCount={memoryCount}
        onOpenAgentTools={() => setIsAgentToolsModalOpen(true)}
        onOpenSystemSettings={() => setIsVoiceSettingsOpen(true)}
      />

      {/* 2. Center Conversation Interface */}
      <main className="flex-1 h-full flex flex-col min-w-0 relative">
        <ChatContainer
          chat={activeChat}
          messages={messages}
          isSending={isSending}
          onSendMessage={handleSendMessage}
          onVoiceInteraction={handleVoiceInteraction}
          activeProvider={activeProvider}
          activeModel={activeModel}
          draftPrompt={draftPrompt}
          onSelectPrompt={handleSelectPrompt}
          onClearDraftPrompt={handleClearDraftPrompt}
          onToggleRightPanel={handleToggleRightPanel}
          isRightPanelOpen={isRightPanelOpen}
          isVoiceMode={isVoiceMode}
          onToggleVoiceMode={handleToggleVoiceMode}
          interactionState={interactionState}
          currentTool={currentTool}
          onCancel={handleCancelOperation}
          onOpenVoiceSettings={() => setIsVoiceSettingsOpen(true)}
          isDryRun={isDryRun}
          onToggleDryRun={() => setIsDryRun(!isDryRun)}
          onEmergencyStop={handleEmergencyStop}
          agentState={agentTelemetry?.state || 'IDLE'}
          onOpenKnowledgeBase={() => setIsKnowledgeModalOpen(true)}
        />
      </main>

      {/* 3. Right Sidebar (HUD & Telemetry Information Panel) */}
      <RightSidebar
        healthData={healthData}
        runtimeTruth={runtimeTruth}
        onRefreshHealth={loadHealth}
        messages={messages}
        onSelectPrompt={handleSelectPrompt}
        isOpen={isRightPanelOpen}
        lastTelemetry={lastTelemetry}
        isSending={isSending}
        isVoiceMode={isVoiceMode}
        voiceState={voiceState}
        agentTelemetry={agentTelemetry}
      />

      {/* 4. Local Knowledge Base Vault Modal (V2.2) */}
      <KnowledgeBaseModal
        isOpen={isKnowledgeModalOpen}
        onClose={() => setIsKnowledgeModalOpen(false)}
        onDocumentChange={(docs) => setKnowledgeDocCount(docs.length)}
      />

      {/* 4b. Smṛti 3.0 Personal Memory Vault Modal */}
      <SmritiMemoryModal
        isOpen={isMemoryModalOpen}
        onClose={() => setIsMemoryModalOpen(false)}
        onMemoryChange={(count) => setMemoryCount(count)}
      />

      {/* 5. Vāṇī Voice Settings Modal (V3.2) */}
      <VoiceSettingsModal
        isOpen={isVoiceSettingsOpen}
        onClose={() => setIsVoiceSettingsOpen(false)}
      />

      {/* 6. V4 Action Permission Confirmation Modal */}
      <AgentPermissionModal
        confirmation={pendingConfirmation}
        onDecision={handleConfirmDecision}
      />

      {/* 7. Krīya Agent Tools Registry Modal */}
      <AgentToolsModal
        isOpen={isAgentToolsModalOpen}
        onClose={() => setIsAgentToolsModalOpen(false)}
        onSelectPrompt={handleSelectPrompt}
      />
    </div>
  );
}
