import React, { useState } from 'react';
import { Copy, Check, ThumbsUp, ThumbsDown, Sparkles, Terminal, AlertCircle } from 'lucide-react';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function ChatMessage({ message }) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null); // 'like' | 'dislike' | null
  const isUser = message.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formattedTime = message.created_at
    ? new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  // Parse optional metadata_json or metadata
  let metadata = null;
  const rawMeta = message.metadata_json || message.metadata;
  if (rawMeta) {
    try {
      metadata = typeof rawMeta === 'string' 
        ? JSON.parse(rawMeta) 
        : rawMeta;
    } catch {
      metadata = null;
    }
  }

  const isGeminiLive = metadata?.provider === 'gemini' && metadata?.status === 'success';
  const isMock = metadata?.provider === 'mock-narad';
  const isError = metadata?.status === 'api_error' || metadata?.status === 'network_error' || metadata?.status === 'error';

  // Simple Markdown renderer helper for bold, bullet lists, and inline code
  const renderFormattedContent = (text) => {
    if (!text) return null;
    
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      const parts = line.split(/(\*\*.*?\*\*|`.*?`)/g);
      
      const formattedLine = parts.map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <strong key={pIdx} className="text-cyan-200 font-semibold">
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith('`') && part.endsWith('`')) {
          return (
            <code key={pIdx} className="bg-narad-card px-1.5 py-0.5 rounded text-narad-cyan font-mono text-xs border border-narad-border/60">
              {part.slice(1, -1)}
            </code>
          );
        }
        return part;
      });

      if (line.trim().startsWith('•') || line.trim().startsWith('-')) {
        return (
          <div key={idx} className="flex items-start gap-2 my-1 pl-1">
            <span className="text-narad-cyan text-xs mt-1">•</span>
            <span className="flex-1">{formattedLine}</span>
          </div>
        );
      }

      if (line.trim() === '') {
        return <div key={idx} className="h-2" />;
      }

      return <p key={idx} className="leading-relaxed">{formattedLine}</p>;
    });
  };

  return (
    <div 
      className={`group flex items-start gap-3 w-full py-1.5 animate-fadeIn ${
        isUser ? 'flex-row-reverse' : 'flex-row'
      }`}
    >
      {/* Avatar Icon */}
      {!isUser && (
        <div className="flex-shrink-0 mt-1 select-none">
          <div className="w-8 h-8 rounded-lg border border-narad-borderBright bg-narad-card flex items-center justify-center shadow-hud-subtle">
            <NaradCoreIcon size={20} animated={false} />
          </div>
        </div>
      )}

      {/* Message Bubble Container */}
      <div className={`max-w-[82%] sm:max-w-[76%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Author Label, Status, and Timestamp */}
        <div className="flex items-center gap-2 mb-1.5 px-1 select-none">
          <span className={`text-[10px] font-mono font-semibold tracking-wider ${
            isUser ? 'text-narad-textDim' : 'text-narad-cyan'
          }`}>
            {isUser ? 'YOU' : 'NARAD // PERSONAL CORE'}
          </span>

          {formattedTime && (
            <span className="text-[10px] font-mono text-narad-textDim">
              {formattedTime}
            </span>
          )}

          {!isUser && metadata?.model && (
            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-narad-card border border-narad-border text-slate-300">
              {metadata.model}
            </span>
          )}

          {!isUser && metadata?.latency_ms !== undefined && metadata.latency_ms > 0 && (
            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-narad-card border border-narad-border text-narad-cyan/90">
              {metadata.latency_ms}ms
            </span>
          )}

          {!isUser && metadata?.status === 'unconfigured' && (
            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
              KEY REQUIRED
            </span>
          )}

          {!isUser && isError && (
            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30">
              API ERROR
            </span>
          )}
        </div>

        {/* Message Bubble */}
        <div
          className={`relative p-4 rounded-xl text-sm transition-all duration-150 ${
            isUser
              ? 'bg-narad-card/90 border border-narad-borderBright text-slate-100 shadow-hud-subtle'
              : isError
              ? 'bg-rose-950/20 border border-rose-500/40 text-rose-100 shadow-hud-subtle'
              : 'hud-panel text-slate-200 border border-narad-border shadow-hud-subtle'
          }`}
        >
          {/* Subtle Corner HUD Accent on Assistant */}
          {!isUser && (
            <>
              <span className="absolute top-0 left-0 w-2 h-2 border-t border-l border-narad-cyan/60 rounded-tl-xl pointer-events-none" />
              <span className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-narad-cyan/60 rounded-br-xl pointer-events-none" />
            </>
          )}

          {/* Content */}
          <div className="font-sans text-sm selection:bg-narad-cyan selection:text-narad-bg space-y-1">
            {renderFormattedContent(message.content)}
          </div>

          {/* Assistant Action Bar (Copy & Feedback) */}
          {!isUser && (
            <div className="mt-3 pt-2.5 border-t border-narad-border/30 flex items-center justify-between text-[11px] font-mono text-narad-textDim select-none">
              {/* Truthful Model Source Tag */}
              {isGeminiLive ? (
                <span className="text-[10px] text-emerald-400 flex items-center gap-1.5 font-semibold tracking-wider">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]" />
                  <Sparkles size={11} className="text-emerald-400" />
                  <span>GEMINI // LIVE</span>
                </span>
              ) : isMock ? (
                <span className="text-[10px] text-narad-cyan/70 flex items-center gap-1">
                  <Sparkles size={11} />
                  <span>SIMULATED CORE</span>
                </span>
              ) : isError ? (
                <span className="text-[10px] text-rose-400 flex items-center gap-1 font-semibold">
                  <AlertCircle size={11} />
                  <span>GEMINI REQUEST FAILED</span>
                </span>
              ) : metadata?.status === 'unconfigured' ? (
                <span className="text-[10px] text-amber-400/90 flex items-center gap-1 font-semibold">
                  <AlertCircle size={11} />
                  <span>KEY NOT CONFIGURED</span>
                </span>
              ) : (
                <span className="text-[10px] text-narad-textDim flex items-center gap-1">
                  <Sparkles size={11} />
                  <span>{metadata?.provider ? metadata.provider.toUpperCase() : 'NARAD RESPONSE'}</span>
                </span>
              )}

              <div className="flex items-center gap-1.5">
                {/* Feedback Like */}
                <button
                  onClick={() => setFeedback(feedback === 'like' ? null : 'like')}
                  className={`p-1 rounded transition-colors ${
                    feedback === 'like'
                      ? 'text-emerald-400 bg-emerald-500/10'
                      : 'text-narad-textDim hover:text-white hover:bg-narad-card'
                  }`}
                  title="Accurate response"
                >
                  <ThumbsUp size={12} />
                </button>

                {/* Feedback Dislike */}
                <button
                  onClick={() => setFeedback(feedback === 'dislike' ? null : 'dislike')}
                  className={`p-1 rounded transition-colors ${
                    feedback === 'dislike'
                      ? 'text-rose-400 bg-rose-500/10'
                      : 'text-narad-textDim hover:text-white hover:bg-narad-card'
                  }`}
                  title="Inaccurate response"
                >
                  <ThumbsDown size={12} />
                </button>

                <div className="h-3 w-[1px] bg-narad-border/40 mx-0.5" />

                {/* Copy Button */}
                <button
                  onClick={handleCopy}
                  className="hover:text-narad-cyan flex items-center gap-1 transition-colors px-1.5 py-0.5 rounded hover:bg-narad-card cursor-pointer"
                  title="Copy to clipboard"
                >
                  {copied ? (
                    <>
                      <Check size={12} className="text-emerald-400" />
                      <span className="text-[10px] text-emerald-400">COPIED</span>
                    </>
                  ) : (
                    <>
                      <Copy size={12} />
                      <span className="text-[10px]">COPY</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* User Terminal Glyph (Replaces generic SaaS user avatar) */}
      {isUser && (
        <div 
          className="w-8 h-8 rounded-lg border border-narad-border bg-narad-card flex items-center justify-center text-narad-cyan flex-shrink-0 mt-1 shadow-hud-subtle"
          title="Direct Owner Input"
        >
          <Terminal size={15} />
        </div>
      )}
    </div>
  );
}
