import React, { useState } from 'react';
import { 
  Plus, 
  Search, 
  MessageSquare, 
  Trash2, 
  Database, 
  Wrench, 
  Settings, 
  ShieldCheck,
  Terminal
} from 'lucide-react';

export default function LeftSidebar({
  chats,
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  isHealthy
}) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredChats = chats.filter(chat => 
    chat.title.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <aside className="w-72 h-full bg-narad-surface border-r border-narad-border flex flex-col select-none relative z-10 flex-shrink-0">
      {/* NARAD Branding & Trimurti Badge */}
      <div className="p-4 border-b border-narad-border flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded border border-narad-cyan bg-narad-cyan/10 flex items-center justify-center text-narad-cyan shadow-[0_0_12px_rgba(0,240,255,0.25)]">
              <Terminal size={18} />
            </div>
            <div>
              <h1 className="font-display tracking-widest text-base font-bold text-white flex items-center gap-1.5">
                NARAD
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-narad-cyan/20 text-narad-cyan border border-narad-cyan/40">
                  V1
                </span>
              </h1>
              <p className="text-[10px] font-mono tracking-wider text-narad-textMuted uppercase">
                TRIMURTI ECOSYSTEM
              </p>
            </div>
          </div>

          <div className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-narad-cyan shadow-[0_0_8px_#00f0ff]' : 'bg-amber-500'}`} title={isHealthy ? "Core Online" : "Connecting..."} />
        </div>

        {/* New Chat Action */}
        <button
          onClick={onNewChat}
          className="mt-2 w-full py-2 px-3 rounded bg-narad-cyan/10 hover:bg-narad-cyan/20 border border-narad-cyan/30 hover:border-narad-cyan/60 text-narad-cyan font-mono text-xs flex items-center justify-center gap-2 transition-all duration-150 active:scale-[0.99] group shadow-[0_0_10px_rgba(0,240,255,0.05)]"
        >
          <Plus size={14} className="group-hover:rotate-90 transition-transform duration-200" />
          <span>NEW BRIEFING</span>
        </button>
      </div>

      {/* Search Input */}
      <div className="px-3 py-2 border-b border-narad-border/60">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-narad-textDim" />
          <input
            type="text"
            placeholder="Search briefings..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-narad-bg/70 border border-narad-border/40 focus:border-narad-cyan/60 rounded px-2.5 pl-8 py-1.5 text-xs text-narad-text placeholder:text-narad-textDim font-mono focus:outline-none transition-colors"
          />
        </div>
      </div>

      {/* Chat History List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <div className="px-2 py-1 text-[10px] font-mono tracking-wider text-narad-textDim uppercase">
          Transmission Logs
        </div>

        {filteredChats.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs font-mono text-narad-textDim">
            {searchTerm ? "No matching briefings" : "No transmission logs"}
          </div>
        ) : (
          filteredChats.map((chat) => {
            const isActive = chat.id === activeChatId;
            return (
              <div
                key={chat.id}
                onClick={() => onSelectChat(chat.id)}
                className={`group flex items-center justify-between px-2.5 py-2 rounded text-xs cursor-pointer transition-all duration-150 ${
                  isActive
                    ? 'bg-narad-cyan/15 text-white border border-narad-cyan/40 shadow-[0_0_10px_rgba(0,240,255,0.07)]'
                    : 'text-narad-textMuted hover:text-white hover:bg-narad-card border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2 overflow-hidden flex-1 mr-2">
                  <MessageSquare size={13} className={isActive ? 'text-narad-cyan' : 'text-narad-textDim group-hover:text-narad-textMuted'} />
                  <span className="truncate font-sans text-xs">{chat.title}</span>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteChat(chat.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-narad-textDim hover:text-rose-400 rounded transition-opacity"
                  title="Purge session"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Lower Navigation (Knowledge Base, Tools, Settings) */}
      <div className="p-3 border-t border-narad-border bg-narad-bg/40 flex flex-col gap-1">
        <button className="flex items-center gap-2.5 px-2.5 py-2 rounded text-xs font-mono text-narad-textMuted hover:text-narad-cyan hover:bg-narad-card transition-colors">
          <Database size={14} className="text-narad-cyan/70" />
          <span>Knowledge Base</span>
          <span className="ml-auto text-[9px] px-1 rounded bg-narad-card border border-narad-border text-narad-textDim">V2</span>
        </button>

        <button className="flex items-center gap-2.5 px-2.5 py-2 rounded text-xs font-mono text-narad-textMuted hover:text-narad-cyan hover:bg-narad-card transition-colors">
          <Wrench size={14} className="text-narad-cyan/70" />
          <span>Agent Tools</span>
          <span className="ml-auto text-[9px] px-1 rounded bg-narad-card border border-narad-border text-narad-textDim">READY</span>
        </button>

        <button className="flex items-center gap-2.5 px-2.5 py-2 rounded text-xs font-mono text-narad-textMuted hover:text-narad-cyan hover:bg-narad-card transition-colors">
          <Settings size={14} className="text-narad-cyan/70" />
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
}
