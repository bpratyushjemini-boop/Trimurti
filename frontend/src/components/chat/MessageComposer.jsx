import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Mic, Sparkles } from 'lucide-react';

export default function MessageComposer({
  onSendMessage,
  disabled,
  draftPrompt = '',
  onClearDraftPrompt
}) {
  const [content, setContent] = useState('');
  const textareaRef = useRef(null);

  // When an external starter prompt is provided, populate textarea and focus
  useEffect(() => {
    if (draftPrompt) {
      setContent(draftPrompt);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
      if (onClearDraftPrompt) {
        onClearDraftPrompt();
      }
    }
  }, [draftPrompt, onClearDraftPrompt]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [content]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!content.trim() || disabled) return;
    onSendMessage(content.trim());
    setContent('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="p-4 border-t border-narad-border bg-narad-surface/90 backdrop-blur-md relative z-10">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        <div className="hud-panel rounded-xl p-3 flex flex-col gap-2.5 relative group focus-within:hud-panel-active transition-all duration-200 shadow-hud-subtle">
          {/* Main Input Textarea */}
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Instruct NARAD, request analysis, or assign a directive... (Enter to transmit, Shift+Enter for newline)"
            rows={2}
            className="w-full bg-transparent resize-none text-sm text-narad-text placeholder:text-narad-textDim focus:outline-none px-2 py-1 font-sans max-h-48 overflow-y-auto leading-relaxed"
          />

          {/* Action Toolbar */}
          <div className="flex items-center justify-between pt-2 border-t border-narad-border/40 px-1 select-none">
            <div className="flex items-center gap-1.5">
              {/* Attachment Control (Disabled/Marked) */}
              <button
                type="button"
                className="p-1.5 rounded text-narad-textDim hover:text-narad-textMuted transition-colors cursor-not-allowed relative group/btn"
                title="File & document ingestion unlocks in future multimodal milestone"
              >
                <Paperclip size={15} />
                <span className="sr-only">Attach file</span>
              </button>

              {/* Voice Button (Disabled/Marked) */}
              <button
                type="button"
                className="p-1.5 rounded text-narad-textDim hover:text-narad-textMuted transition-colors cursor-not-allowed relative group/btn"
                title="Vaani voice interface is in development (V2)"
              >
                <Mic size={15} />
                <span className="sr-only">Voice input</span>
              </button>

              <div className="h-3 w-[1px] bg-narad-border/60 mx-1" />

              <span className="text-[10px] font-mono text-narad-textDim flex items-center gap-1.5">
                <Sparkles size={11} className="text-narad-cyan" />
                <span className="hidden sm:inline">LOCAL VAULT PERSISTENCE</span>
              </span>
            </div>

            {/* Right Action: Shortcuts & Send */}
            <div className="flex items-center gap-2">
              <span className="hidden sm:inline text-[10px] font-mono text-narad-textDim">
                ↵ SEND • ⇧↵ NEWLINE
              </span>

              {/* Send Button */}
              <button
                type="submit"
                disabled={!content.trim() || disabled}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center gap-2 transition-all duration-150 ${
                  content.trim() && !disabled
                    ? 'bg-narad-cyan text-narad-bg hover:bg-narad-blue shadow-[0_0_14px_rgba(0,240,255,0.45)] cursor-pointer active:scale-95'
                    : 'bg-narad-card text-narad-textDim border border-narad-border/50 cursor-not-allowed'
                }`}
              >
                <span>TRANSMIT</span>
                <Send size={12} className={content.trim() && !disabled ? 'translate-x-0.5' : ''} />
              </button>
            </div>
          </div>
        </div>

        {/* Minimal Footer Status Bar */}
        <div className="flex justify-between items-center px-2 pt-2 text-[10px] font-mono text-narad-textDim select-none">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>NARAD V1 // LOCAL STANDALONE INSTANCE</span>
          </span>
          <span>PRIVATE PERSONAL AI</span>
        </div>
      </form>
    </div>
  );
}
