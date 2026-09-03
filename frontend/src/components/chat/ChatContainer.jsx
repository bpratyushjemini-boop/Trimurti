import React, { useEffect, useRef } from 'react';
import ChatHeader from './ChatHeader';
import ChatMessage from './ChatMessage';
import WelcomeHero from './WelcomeHero';
import MessageComposer from './MessageComposer';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function ChatContainer({
  chat,
  messages = [],
  isSending = false,
  onSendMessage,
  activeProvider = 'gemini',
  activeModel = 'gemini-2.5-flash',
  draftPrompt = '',
  onSelectPrompt,
  onClearDraftPrompt,
  onToggleRightPanel,
  isRightPanelOpen = true
}) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom on new messages or thinking state
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isSending]);

  return (
    <div className="flex-1 h-full flex flex-col bg-narad-bg bg-tech-grid relative overflow-hidden">
      {/* Top Header */}
      <ChatHeader
        title={chat ? chat.title : 'NARAD Core Standby'}
        activeProvider={activeProvider}
        activeModel={activeModel}
        onToggleRightPanel={onToggleRightPanel}
        isRightPanelOpen={isRightPanelOpen}
      />

      {/* Main Conversation Scroll Stream */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-6 space-y-3 flex flex-col"
      >
        {messages.length === 0 ? (
          <WelcomeHero onSelectPrompt={onSelectPrompt} />
        ) : (
          messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))
        )}

        {/* Thinking / Transmitting Loading State Indicator */}
        {isSending && (
          <div className="py-2 px-4 flex items-center gap-3 animate-fadeIn">
            <div className="w-8 h-8 rounded-lg border border-narad-cyan/70 bg-narad-card flex items-center justify-center shadow-[0_0_14px_rgba(0,240,255,0.3)]">
              <NaradCoreIcon size={20} animated={true} />
            </div>
            <div className="flex items-center gap-2 font-mono text-xs text-narad-cyan">
              <span className="inline-block w-2 h-2 rounded-full bg-narad-cyan animate-ping" />
              <span className="tracking-wide font-semibold">NARAD // THINKING...</span>
            </div>
          </div>
        )}
      </div>

      {/* Message Composer Area */}
      <MessageComposer
        onSendMessage={onSendMessage}
        disabled={isSending}
        draftPrompt={draftPrompt}
        onClearDraftPrompt={onClearDraftPrompt}
      />
    </div>
  );
}
