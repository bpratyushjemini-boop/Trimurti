import React from 'react';
import { MessageSquare, Trash2 } from 'lucide-react';

export default function ConversationItem({
  chat,
  isActive,
  onSelect,
  onDelete
}) {
  const handleDelete = (e) => {
    e.stopPropagation();
    onDelete(chat.id);
  };

  const formattedDate = chat.created_at
    ? new Date(chat.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })
    : '';

  return (
    <div
      onClick={() => onSelect(chat.id)}
      className={`group relative flex items-center justify-between px-3 py-2.5 rounded-md text-xs cursor-pointer transition-all duration-150 ${
        isActive
          ? 'bg-narad-card border border-narad-cyan/40 text-white shadow-hud-subtle'
          : 'text-narad-textMuted hover:text-white hover:bg-narad-card/50 border border-transparent'
      }`}
    >
      {/* Active Cyan Left Indicator Bar */}
      {isActive && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 rounded-r bg-narad-cyan shadow-[0_0_8px_#00f0ff]" />
      )}

      <div className="flex items-center gap-2.5 overflow-hidden flex-1 min-w-0 pr-2">
        <MessageSquare
          size={14}
          className={`flex-shrink-0 transition-colors ${
            isActive ? 'text-narad-cyan' : 'text-narad-textDim group-hover:text-narad-cyan/80'
          }`}
        />
        <div className="flex flex-col min-w-0">
          <span className={`truncate font-sans text-xs ${isActive ? 'font-medium text-white' : 'text-slate-300'}`}>
            {chat.title || 'New Briefing'}
          </span>
          {formattedDate && (
            <span className="text-[10px] font-mono text-narad-textDim mt-0.5">
              {formattedDate}
            </span>
          )}
        </div>
      </div>

      {/* Action Button on Hover */}
      <button
        onClick={handleDelete}
        className="opacity-0 group-hover:opacity-100 p-1.5 rounded text-narad-textDim hover:text-rose-400 hover:bg-narad-surface/80 transition-all flex-shrink-0"
        title="Purge session"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}
