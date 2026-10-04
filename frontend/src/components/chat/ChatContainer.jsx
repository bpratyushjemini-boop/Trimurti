import React, { useEffect, useRef } from 'react';
import ChatHeader from './ChatHeader';
import ChatMessage from './ChatMessage';
import WelcomeHero from './WelcomeHero';
import MessageComposer from './MessageComposer';
import NaradCoreIcon from '../common/NaradCoreIcon';
import { Wrench, Volume2, Sparkles, Loader2 } from 'lucide-react';

export default function ChatContainer({
  chat,
  messages = [],
  isSending = false,
  onSendMessage,
  activeProvider = 'groq',
  activeModel = 'openai/gpt-oss-120b',
  draftPrompt = '',
  onSelectPrompt,
  onClearDraftPrompt,
  onToggleRightPanel,
  isRightPanelOpen = true,
  isVoiceMode = false,
  onToggleVoiceMode,
  interactionState = 'IDLE',
  currentTool = null,
  onCancel = null,
  onOpenVoiceSettings = null,
  isDryRun = false,
  onToggleDryRun = null,
  onEmergencyStop = null,
  agentState = 'IDLE',
  onVoiceInteraction = null,
  onOpenKnowledgeBase = null
}) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom on new messages or busy state
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isSending, interactionState]);

  return (
    <div className="flex-1 h-full flex flex-col bg-narad-bg bg-tech-grid relative overflow-hidden">
      {/* Subtle scanline overlay */}
      <div className="scanline-overlay" />
      
      {/* Top Header */}
      <ChatHeader
        title={chat ? chat.title : 'NARAD Core Standby'}
        activeProvider={activeProvider}
        activeModel={activeModel}
        onToggleRightPanel={onToggleRightPanel}
        isRightPanelOpen={isRightPanelOpen}
        isVoiceMode={isVoiceMode}
        onToggleVoiceMode={onToggleVoiceMode}
      />

      {/* Main Conversation Scroll Stream */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-6 space-y-3 flex flex-col relative z-[2]"
      >
        {messages.length === 0 ? (
          <WelcomeHero onSelectPrompt={onSelectPrompt} />
        ) : (
          messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))
        )}

        {/* Dynamic Turn-Taking State Indicators */}
        {isSending && (
          <div className="py-2 px-4 flex items-center gap-3 animate-fadeIn">
            <div className="w-8 h-8 rounded-lg border border-narad-saffron/50 bg-narad-card flex items-center justify-center shadow-hud-saffron">
              <NaradCoreIcon size={20} animated={true} />
            </div>
            
            {interactionState === 'TOOL_EXECUTION' ? (
              <div className="flex items-center gap-2 font-mono text-xs text-narad-cyan">
                <Wrench size={14} className="text-narad-cyan animate-pulse" />
                <span className="tracking-wide font-semibold">KRĪYA // EXECUTING{currentTool ? `: ${currentTool}` : ''}...</span>
              </div>
            ) : interactionState === 'GENERATING' ? (
              <div className="flex items-center gap-2 font-mono text-xs text-cyan-300">
                <Sparkles size={14} className="text-cyan-400 animate-spin" />
                <span className="tracking-wide font-semibold">NARAD // GENERATING...</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 font-mono text-xs text-narad-saffron">
                <Loader2 size={14} className="text-narad-saffron animate-spin" />
                <span className="tracking-wide font-semibold">NARAD // THINKING & ROUTING...</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Message Composer Area */}
      <MessageComposer
        onSendMessage={onSendMessage}
        disabled={isSending}
        draftPrompt={draftPrompt}
        onClearDraftPrompt={onClearDraftPrompt}
        isVoiceMode={isVoiceMode}
        onToggleVoiceMode={onToggleVoiceMode}
        interactionState={interactionState}
        currentTool={currentTool}
        onCancel={onCancel}
        onOpenVoiceSettings={onOpenVoiceSettings}
        isDryRun={isDryRun}
        onToggleDryRun={onToggleDryRun}
        onEmergencyStop={onEmergencyStop}
        agentState={agentState}
        onVoiceInteraction={onVoiceInteraction}
        onOpenKnowledgeBase={onOpenKnowledgeBase}
      />
    </div>
  );
}
