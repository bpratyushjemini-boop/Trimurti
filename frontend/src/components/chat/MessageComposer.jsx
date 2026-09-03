import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Mic, Sparkles } from 'lucide-react';

export default function MessageComposer({ onSendMessage, disabled }) {
  const [content, setContent] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [content]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!content.trim() || disabled) return;
    onSendMessage(content.trim());
    setContent('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
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
        <div className="hud-panel rounded-lg p-2 flex flex-col gap-2 relative group focus-within:hud-panel-active transition-all duration-200">
          {/* Main Input Textarea */}
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Instruct NARAD... (Enter to transmit, Shift+Enter for newline)"
            rows={1}
            className="w-full bg-transparent resize-none text-sm text-narad-text placeholder:text-narad-textDim focus:outline-none px-2.5 py-1 font-sans max-h-40 overflow-y-auto"
          />

          {/* Action Toolbar */}
          <div className="flex items-center justify-between pt-1 border-t border-narad-border/40 px-1">
            <div className="flex items-center gap-1.5">
              {/* Attachment Control Placeholder */}
              <button
                type="button"
                className="p-1.5 rounded text-narad-textDim hover:text-narad-cyan hover:bg-narad-card transition-colors"
                title="Attach Document or Image (Trinetra / Kriya)"
              >
                <Paperclip size={15} />
              </button>

              {/* Voice Button Placeholder */}
              <button
                type="button"
                className="p-1.5 rounded text-narad-textDim hover:text-narad-cyan hover:bg-narad-card transition-colors relative"
                title="Voice Input (Vaani Module Placeholder)"
              >
                <Mic size={15} />
              </button>

              <div className="h-3 w-[1px] bg-narad-border/60 mx-1" />

              <span className="text-[10px] font-mono text-narad-textDim flex items-center gap-1">
                <Sparkles size={11} className="text-narad-cyan/60" />
                AGNOSTIC CORE
              </span>
            </div>

            {/* Send Button */}
            <button
              type="submit"
              disabled={!content.trim() || disabled}
              className={`px-3 py-1.5 rounded text-xs font-mono flex items-center gap-1.5 transition-all duration-150 ${
                content.trim() && !disabled
                  ? 'bg-narad-cyan text-narad-bg font-semibold hover:bg-narad-blue shadow-[0_0_12px_rgba(0,240,255,0.4)] cursor-pointer'
                  : 'bg-narad-card text-narad-textDim border border-narad-border/40 cursor-not-allowed'
              }`}
            >
              <span>SEND</span>
              <Send size={12} />
            </button>
          </div>
        </div>

        {/* Minimal Footer Status */}
        <div className="flex justify-between items-center px-2 pt-2 text-[10px] font-mono text-narad-textDim">
          <span>NARAD PROTOCOL v0.1</span>
          <span>TRIMURTI AGENT FABRIC</span>
        </div>
      </form>
    </div>
  );
}
