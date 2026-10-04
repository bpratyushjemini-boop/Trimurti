import React, { useState, useEffect } from 'react';
import { Copy, Check, ThumbsUp, ThumbsDown, Sparkles, Terminal, AlertCircle, Volume2, Square, Radio } from 'lucide-react';
import NaradCoreIcon from '../common/NaradCoreIcon';
import { vaaniService } from '../../services/voice';

export default function ChatMessage({ message }) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const isUser = message.role === 'user';

  // Stop speaking on unmount
  useEffect(() => {
    return () => {
      if (isSpeaking) {
        vaaniService.stopSpeaking();
      }
    };
  }, [isSpeaking]);

  const handleToggleSpeak = () => {
    if (isSpeaking) {
      vaaniService.stopSpeaking();
      setIsSpeaking(false);
      return;
    }

    if (isError) return;

    vaaniService.speak(message.content, {
      onStart: () => setIsSpeaking(true),
      onEnd: () => setIsSpeaking(false),
      onError: () => setIsSpeaking(false)
    });
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatMessageTimestamp = (ts) => {
    if (!ts) return '';
    try {
      let iso = String(ts).trim();
      if (iso.includes(' ') && !iso.includes('T')) {
        iso = iso.replace(' ', 'T');
      }
      if (!iso.endsWith('Z') && !iso.includes('+') && !/-\d{2}:\d{2}$/.test(iso)) {
        iso += 'Z';
      }
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const formattedTime = formatMessageTimestamp(message.created_at);

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

  // Provider Truth & Anti-Hallucination: Hard execution mode enforcement
  const providerLower = (metadata?.provider || '').toLowerCase();
  const isCloudProvider = providerLower === 'groq' || providerLower === 'nvidia' || providerLower === 'gemini' || providerLower === 'openrouter';
  const isLocalProvider = providerLower === 'ollama' || providerLower === 'huggingface' || providerLower === 'task-engine' || providerLower === 'manthan' || providerLower === 'micro-tasks' || providerLower === 'deterministic-engine';

  let executionMode = 'CLOUD';
  if (isLocalProvider || metadata?.execution_mode === 'local' || metadata?.execution === 'local') {
    executionMode = isCloudProvider ? 'CLOUD' : 'LOCAL';
  } else if (metadata?.execution_mode === 'cloud' || metadata?.execution === 'cloud' || isCloudProvider) {
    executionMode = 'CLOUD';
  }

  const liveProviderName = metadata?.provider ? metadata.provider.toUpperCase() : 'NARAD';
  const providerTruthLabel = `${liveProviderName} // ${executionMode}`;
  const isMock = metadata?.provider === 'mock-narad';
  const isError = metadata?.status === 'api_error' || metadata?.status === 'network_error' || metadata?.status === 'error' || metadata?.status === 'offline_rejected';

  // Enhanced Markdown renderer with heading support
  const renderFormattedContent = (text) => {
    if (!text) return null;
    
    const lines = text.split('\n');
    return lines.map((line, idx) => {
      // Heading detection
      if (line.trim().startsWith('### ')) {
        return (
          <h4 key={idx} className="text-narad-cyan/85 font-display font-semibold text-xs tracking-wide mt-3 mb-1">
            {line.trim().slice(4)}
          </h4>
        );
      }
      if (line.trim().startsWith('## ')) {
        return (
          <h3 key={idx} className="text-narad-cyan font-display font-semibold text-sm tracking-wide mt-3 mb-1.5">
            {line.trim().slice(3)}
          </h3>
        );
      }

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
            <code key={pIdx} className="bg-narad-card/80 px-1.5 py-0.5 rounded text-narad-cyan font-mono text-xs border border-narad-border/40">
              {part.slice(1, -1)}
            </code>
          );
        }
        return part;
      });

      if (line.trim().startsWith('•') || line.trim().startsWith('-')) {
        return (
          <div key={idx} className="flex items-start gap-2 my-0.5 pl-1">
            <span className="text-narad-saffron text-xs mt-1 flex-shrink-0">•</span>
            <span className="flex-1">{formattedLine}</span>
          </div>
        );
      }

      if (line.trim() === '') {
        return <div key={idx} className="h-1.5" />;
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
          <div className="w-8 h-8 rounded-lg border border-narad-saffron/40 bg-narad-card flex items-center justify-center shadow-hud-saffron">
            <NaradCoreIcon size={20} animated={false} />
          </div>
        </div>
      )}

      {/* Message Bubble Container */}
      <div className={`max-w-[82%] sm:max-w-[76%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Author Label, Status, and Timestamp */}
        <div className="flex items-center gap-2 mb-1.5 px-1 select-none flex-wrap">
          <span className={`text-[10px] font-mono font-semibold tracking-wider ${
            isUser ? 'text-narad-textDim' : 'text-narad-saffron'
          }`}>
            {isUser ? 'YOU' : 'NARAD'}
          </span>

          {formattedTime && (
            <span className="text-[10px] font-mono text-narad-textDim">
              {formattedTime}
            </span>
          )}

          {!isUser && metadata?.model && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-narad-card border border-narad-border text-slate-300">
              {metadata.model}
            </span>
          )}

          {!isUser && (
            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-md border font-semibold ${
              executionMode === 'LOCAL'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}>
              {executionMode}
            </span>
          )}

          {!isUser && metadata?.latency_ms !== undefined && metadata.latency_ms > 0 && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-narad-card border border-narad-border text-narad-cyan/90">
              {metadata.latency_ms}ms
            </span>
          )}

          {!isUser && metadata?.status === 'unconfigured' && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/30">
              KEY REQUIRED
            </span>
          )}

          {!isUser && isError && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-rose-500/10 text-rose-400 border border-rose-500/30">
              {metadata?.status === 'offline_rejected' ? 'OFFLINE REJECTED' : 'API ERROR'}
            </span>
          )}
        </div>

        {/* Message Bubble */}
        <div
          className={`relative p-4 rounded-xl text-sm transition-all duration-200 ${
            isUser
              ? 'bg-gradient-to-br from-narad-card/95 to-narad-card/70 border border-narad-borderBright/60 text-slate-100 shadow-hud-subtle'
              : isError
              ? 'bg-rose-950/20 border border-rose-500/40 text-rose-100 shadow-hud-subtle'
              : 'hud-panel text-slate-200 border border-narad-border shadow-hud-subtle msg-assistant-accent'
          }`}
        >
          {/* Corner accents on assistant messages */}
          {!isUser && !isError && (
            <>
              <span className="absolute top-0 left-0 w-2.5 h-2.5 border-t border-l border-narad-saffron/50 rounded-tl-xl pointer-events-none" />
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 border-b border-r border-narad-cyan/50 rounded-br-xl pointer-events-none" />
            </>
          )}

          {/* Content */}
          <div className="font-sans text-sm selection:bg-narad-cyan/30 selection:text-white space-y-0.5 message-content">
            {renderFormattedContent(message.content)}
          </div>

          {/* Assistant Action Bar */}
          {!isUser && (
            <div className="mt-3 pt-2.5 border-t border-narad-border/20 flex items-center justify-between text-[11px] font-mono text-narad-textDim select-none">
              {/* Model Source Tag: Truthful Provider & Execution Mode Badge */}
              {isError ? (
                <span className="text-[10px] text-rose-400 flex items-center gap-1 font-semibold" title={metadata?.why_this_choice || ''}>
                  <AlertCircle size={11} />
                  <span>{metadata?.provider ? `${metadata.provider.toUpperCase()} FAILED` : 'REQUEST FAILED'}</span>
                </span>
              ) : metadata?.status === 'unconfigured' ? (
                <span className="text-[10px] text-amber-400/90 flex items-center gap-1 font-semibold">
                  <AlertCircle size={11} />
                  <span>KEY NOT CONFIGURED</span>
                </span>
              ) : isMock ? (
                <span className="text-[10px] text-narad-cyan/70 flex items-center gap-1">
                  <Sparkles size={11} />
                  <span>SIMULATED // LOCAL</span>
                </span>
              ) : executionMode === 'LOCAL' ? (
                <span 
                  className="text-[10px] text-amber-400 flex items-center gap-1.5 font-semibold tracking-wider" 
                  title={metadata?.why_this_choice || `${liveProviderName} on-device local inference via ${metadata?.endpoint || '127.0.0.1'}`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_6px_#fbbf24]" />
                  <Sparkles size={11} className="text-amber-400" />
                  <span>{providerTruthLabel}</span>
                </span>
              ) : (
                <span 
                  className="text-[10px] text-emerald-400 flex items-center gap-1.5 font-semibold tracking-wider" 
                  title={metadata?.why_this_choice || `${liveProviderName} remote cloud inference API`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]" />
                  <Sparkles size={11} className="text-emerald-400" />
                  <span>{providerTruthLabel}</span>
                </span>
              )}

              <div className="flex items-center gap-1">
                {/* Feedback */}
                <button
                  onClick={() => setFeedback(feedback === 'like' ? null : 'like')}
                  className={`p-1 rounded-md transition-colors ${
                    feedback === 'like'
                      ? 'text-emerald-400 bg-emerald-500/10'
                      : 'text-narad-textDim hover:text-white hover:bg-narad-card'
                  }`}
                  title="Accurate"
                >
                  <ThumbsUp size={11} />
                </button>

                <button
                  onClick={() => setFeedback(feedback === 'dislike' ? null : 'dislike')}
                  className={`p-1 rounded-md transition-colors ${
                    feedback === 'dislike'
                      ? 'text-rose-400 bg-rose-500/10'
                      : 'text-narad-textDim hover:text-white hover:bg-narad-card'
                  }`}
                  title="Inaccurate"
                >
                  <ThumbsDown size={11} />
                </button>

                {/* Speak Button */}
                {!isError && (
                  <button
                    onClick={handleToggleSpeak}
                    className={`flex items-center gap-1 transition-colors px-1.5 py-0.5 rounded-md cursor-pointer ${
                      isSpeaking
                        ? 'text-cyan-300 bg-cyan-500/20 border border-cyan-500/40 shadow-glow-cyan animate-pulse'
                        : 'text-narad-textDim hover:text-narad-cyan hover:bg-narad-card'
                    }`}
                    title={isSpeaking ? "Stop speaking" : "Speak via Vāṇī"}
                  >
                    {isSpeaking ? (
                      <>
                        <Square size={10} className="text-cyan-300 fill-current" />
                        <span className="text-[9px] font-mono font-semibold text-cyan-300">STOP</span>
                      </>
                    ) : (
                      <>
                        <Volume2 size={11} />
                      </>
                    )}
                  </button>
                )}

                <div className="h-3 w-[1px] bg-narad-border/30 mx-0.5" />

                {/* Copy */}
                <button
                  onClick={handleCopy}
                  className="hover:text-narad-cyan flex items-center gap-1 transition-colors px-1.5 py-0.5 rounded-md hover:bg-narad-card cursor-pointer"
                  title="Copy"
                >
                  {copied ? (
                    <Check size={11} className="text-emerald-400" />
                  ) : (
                    <Copy size={11} />
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Speaking indicator */}
          {isSpeaking && (
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-cyan-300 mt-1 px-1">
              <Radio size={11} className="animate-pulse text-cyan-400" />
              <span>VĀṆĪ // SPEAKING...</span>
            </div>
          )}
        </div>
      </div>

      {/* User Terminal Glyph */}
      {isUser && (
        <div 
          className="w-8 h-8 rounded-lg border border-narad-border bg-narad-card flex items-center justify-center text-narad-cyan flex-shrink-0 mt-1 shadow-hud-subtle"
          title="Owner Input"
        >
          <Terminal size={15} />
        </div>
      )}
    </div>
  );
}
