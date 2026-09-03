import React, { useState } from 'react';
import {
  Plus,
  Search,
  Database,
  Wrench,
  Settings
} from 'lucide-react';
import ConversationItem from './ConversationItem';
import SystemIdentity from './SystemIdentity';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function LeftSidebar({
  chats = [],
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  isHealthy = true
}) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredChats = chats.filter(chat =>
    (chat.title || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <aside className="w-72 h-full bg-narad-surface border-r border-narad-border flex flex-col select-none relative z-20 flex-shrink-0">
      {/* 1. NARAD Identity & Header */}
      <div className="p-4 border-b border-narad-border flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <NaradCoreIcon size={32} animated={true} />
            <div>
              <h1 className="font-display tracking-widest text-base font-bold text-white flex items-center gap-1.5">
                NARAD
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-narad-cyan/20 text-narad-cyan border border-narad-cyan/40">
                  V1
                </span>
              </h1>
              <p className="text-[10px] font-mono tracking-wider text-narad-textMuted uppercase">
                PERSONAL AI CORE
              </p>
            </div>
          </div>

          <div
            className="flex items-center gap-1 px-2 py-0.5 rounded border border-narad-border text-[10px] font-mono text-narad-textDim"
            title={isHealthy ? "Local loopback connection active" : "Local backend unreachable"}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isHealthy ? 'bg-narad-cyan animate-pulse shadow-[0_0_6px_#00f0ff]' : 'bg-rose-500'}`} />
            <span>{isHealthy ? 'LOCAL' : 'OFFLINE'}</span>
          </div>
        </div>

        {/* 2. New Briefing Action */}
        <button
          onClick={onNewChat}
          className="w-full py-2.5 px-3 rounded bg-narad-cyan/10 hover:bg-narad-cyan/20 border border-narad-cyan/35 hover:border-narad-cyan/70 text-narad-cyan font-mono text-xs font-semibold flex items-center justify-center gap-2 transition-all duration-150 active:scale-[0.99] group shadow-hud-subtle cursor-pointer"
        >
          <Plus size={15} className="group-hover:rotate-90 transition-transform duration-200" />
          <span>NEW BRIEFING</span>
        </button>
      </div>

      {/* 3. Search Briefings */}
      <div className="px-3 py-2.5 border-b border-narad-border/60">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-narad-textDim" />
          <input
            type="text"
            placeholder="Search briefings..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-narad-bg/80 border border-narad-border/40 focus:border-narad-cyan/60 rounded px-2.5 pl-8 py-1.5 text-xs text-narad-text placeholder:text-narad-textDim font-mono focus:outline-none transition-colors"
          />
        </div>
      </div>

      {/* 4. Conversation History List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <div className="px-2 py-1 text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center justify-between">
          <span>Briefing History</span>
          <span className="text-[9px]">{filteredChats.length}</span>
        </div>

        {filteredChats.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs font-mono text-narad-textDim">
            {searchTerm ? "No matching briefings found" : "No briefings recorded"}
          </div>
        ) : (
          filteredChats.map((chat) => (
            <ConversationItem
              key={chat.id}
              chat={chat}
              isActive={chat.id === activeChatId}
              onSelect={onSelectChat}
              onDelete={onDeleteChat}
            />
          ))
        )}
      </div>

      {/* 5. Subsystem Navigation (Knowledge Base, Tools, System Settings) */}
      <div className="p-2.5 border-t border-narad-border bg-narad-bg/40 flex flex-col gap-1">
        <div
          className="flex items-center gap-2.5 px-2.5 py-2 rounded text-xs font-mono text-narad-textDim opacity-80 cursor-not-allowed select-none"
          title="Smriti local vector memory integration arriving in Milestone 4"
        >
          <Database size={14} className="text-narad-textDim" />
          <span>Knowledge Base</span>
          <span className="ml-auto text-[9px] px-1 py-0.2 rounded bg-narad-card border border-narad-border/60 text-narad-textDim">
            COMING SOON
          </span>
        </div>

        <div
          className="flex items-center gap-2.5 px-2.5 py-2 rounded text-xs font-mono text-narad-textDim opacity-80 cursor-not-allowed select-none"
          title="Kriya local tool execution engine unlocks in upcoming milestone"
        >
          <Wrench size={14} className="text-narad-textDim" />
          <span>Agent Tools</span>
          <span className="ml-auto text-[9px] px-1 py-0.2 rounded bg-narad-card border border-narad-border/60 text-narad-textDim">
            STANDBY
          </span>
        </div>

        <div
          className="flex items-center gap-2.5 px-2.5 py-2 rounded text-xs font-mono text-narad-textDim opacity-80 cursor-not-allowed select-none"
          title="System preferences & local model routing options"
        >
          <Settings size={14} className="text-narad-textDim" />
          <span>System Settings</span>
          <span className="ml-auto text-[9px] px-1 py-0.2 rounded bg-narad-card border border-narad-border/60 text-narad-textDim">
            LOCAL
          </span>
        </div>
      </div>

      {/* 6. System Identity / Private Local Node (Replaces commercial User Profile) */}
      <SystemIdentity />
    </aside>
  );
}
