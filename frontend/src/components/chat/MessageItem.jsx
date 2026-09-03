import React, { useState } from 'react';
import { Terminal, User, Copy, Check } from 'lucide-react';

export default function MessageItem({ message }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formattedTime = message.created_at
    ? new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  return (
    <div className={`py-3 px-4 flex gap-3.5 group transition-colors ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded border border-narad-cyan bg-narad-cyan/10 flex items-center justify-center text-narad-cyan flex-shrink-0 mt-0.5 shadow-[0_0_10px_rgba(0,240,255,0.2)]">
          <Terminal size={16} />
        </div>
      )}

      <div className={`max-w-[78%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Author Label & Timestamp */}
        <div className="flex items-center gap-2 mb-1 px-1">
          <span className="text-[11px] font-mono font-semibold tracking-wider text-narad-textDim">
            {isUser ? 'OPERATOR' : 'NARAD // CORE'}
          </span>
          {formattedTime && (
            <span className="text-[10px] font-mono text-narad-textDim/80">
              {formattedTime}
            </span>
          )}
        </div>

        {/* Message Bubble */}
        <div
          className={`relative p-3.5 rounded-lg text-sm leading-relaxed transition-all ${
            isUser
              ? 'bg-narad-card border border-narad-border text-white'
              : 'hud-panel text-narad-text border border-narad-border/80'
          }`}
        >
          <div className="whitespace-pre-wrap font-sans text-sm selection:bg-narad-cyan selection:text-narad-bg">
            {message.content}
          </div>

          {/* Quick Copy Trigger for Assistant */}
          {!isUser && (
            <div className="mt-2.5 pt-2 border-t border-narad-border/30 flex items-center justify-between text-[11px] font-mono text-narad-textDim">
              <span className="text-[10px] text-narad-cyan/70">
                // TELEMETRY VERIFIED
              </span>
              <button
                onClick={handleCopy}
                className="hover:text-narad-cyan flex items-center gap-1 transition-colors px-1 py-0.5 rounded"
                title="Copy response"
              >
                {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                <span className="text-[10px]">{copied ? 'COPIED' : 'COPY'}</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded border border-narad-border bg-narad-card flex items-center justify-center text-narad-textMuted flex-shrink-0 mt-0.5">
          <User size={16} />
        </div>
      )}
    </div>
  );
}
