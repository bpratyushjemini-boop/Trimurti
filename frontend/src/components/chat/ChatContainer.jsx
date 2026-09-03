import React, { useEffect, useRef } from 'react';
import MessageItem from './MessageItem';
import MessageComposer from './MessageComposer';
import { Cpu, Activity, Shield, Sparkles, Terminal } from 'lucide-react';

export default function ChatContainer({
  chat,
  messages,
  isSending,
  onSendMessage,
  activeProvider
}) {
  const scrollRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isSending]);

  return (
    <div className="flex-1 h-full flex flex-col bg-narad-bg bg-tech-grid relative overflow-hidden">
      {/* Top Header Bar */}
      <header className="h-14 border-b border-narad-border bg-narad-surface/80 backdrop-blur-md px-6 flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <h2 className="font-display font-semibold text-sm tracking-wide text-white truncate max-w-md">
            {chat ? chat.title : 'NARAD Core Standby'}
          </h2>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-narad-card border border-narad-border text-narad-textMuted flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-narad-cyan animate-pulse" />
            LIVE LINK
          </span>
        </div>

        {/* Model Indicator & Protocol */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-narad-card border border-narad-border text-xs font-mono text-narad-cyan">
            <Cpu size={13} />
            <span>{activeProvider || 'AGNOSTIC ROUTER'}</span>
          </div>

          <div className="hidden md:flex items-center gap-1 text-[11px] font-mono text-narad-textDim px-2 py-1 rounded border border-narad-border/30">
            <Activity size={12} className="text-emerald-400" />
            <span>TELEMETRY: OK</span>
          </div>
        </div>
      </header>

      {/* Message History Feed */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 max-w-xl mx-auto">
            <div className="w-16 h-16 rounded-xl border border-narad-cyan bg-narad-cyan/10 flex items-center justify-center text-narad-cyan mb-4 shadow-[0_0_24px_rgba(0,240,255,0.2)]">
              <Terminal size={32} />
            </div>

            <h3 className="font-display text-xl font-bold tracking-wider text-white mb-2">
              NARAD INTELLIGENT CORE ONLINE
            </h3>
            <p className="text-xs font-mono text-narad-textMuted leading-relaxed max-w-md mb-6">
              Networked Agent for Retrieval, Analysis & Dissemination. 
              V1 Core Interface for the TRIMURTI AI Ecosystem.
            </p>

            {/* Feature Pills */}
            <div className="grid grid-cols-2 gap-3 w-full text-left">
              <div className="p-3 rounded bg-narad-card/60 border border-narad-border/60 hover:border-narad-cyan/40 transition-colors">
                <div className="text-narad-cyan text-xs font-mono font-semibold flex items-center gap-1.5 mb-1">
                  <Cpu size={13} />
                  <span>Model Agnostic</span>
                </div>
                <p className="text-[11px] text-narad-textDim font-sans">
                  Dynamic provider switching ready for Gemini, Groq, OpenRouter, Claude & OpenAI.
                </p>
              </div>

              <div className="p-3 rounded bg-narad-card/60 border border-narad-border/60 hover:border-narad-cyan/40 transition-colors">
                <div className="text-narad-cyan text-xs font-mono font-semibold flex items-center gap-1.5 mb-1">
                  <Shield size={13} />
                  <span>Isolated & Secure</span>
                </div>
                <p className="text-[11px] text-narad-textDim font-sans">
                  Local SQLite persistence with zero credential leakage and safe environment sandboxing.
                </p>
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageItem key={msg.id} message={msg} />
          ))
        )}

        {/* Thinking / Transmitting State Indicator */}
        {isSending && (
          <div className="py-2 px-4 flex items-center gap-3">
            <div className="w-8 h-8 rounded border border-narad-cyan bg-narad-cyan/10 flex items-center justify-center text-narad-cyan flex-shrink-0 animate-pulse">
              <Sparkles size={16} />
            </div>
            <div className="flex items-center gap-2 font-mono text-xs text-narad-cyan">
              <span className="inline-block w-2 h-2 rounded-full bg-narad-cyan animate-ping" />
              <span>SYNTHESIZING TELEMETRY IN NARAD CORE...</span>
            </div>
          </div>
        )}
      </div>

      {/* Message Composer Area */}
      <MessageComposer onSendMessage={onSendMessage} disabled={isSending} />
    </div>
  );
}
