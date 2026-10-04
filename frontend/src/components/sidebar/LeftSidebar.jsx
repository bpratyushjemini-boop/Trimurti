import React, { useState } from 'react';
import {
  Plus,
  Search,
  Database,
  Brain,
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
  isHealthy = true,
  onOpenKnowledgeBase,
  knowledgeDocCount = 0,
  onOpenSmritiMemory,
  memoryCount = 0,
  onOpenAgentTools,
  onOpenSystemSettings
}) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredChats = chats.filter(chat =>
    (chat.title || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <aside className="w-72 h-full bg-narad-surface border-r border-narad-border flex flex-col select-none relative z-20 flex-shrink-0 saffron-accent-top">
      {/* 1. NARAD Identity & Header */}
      <div className="p-4 border-b border-narad-border flex flex-col gap-3 bg-gradient-panel">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <NaradCoreIcon size={34} animated={true} />
            <div>
              <h1 className="font-display tracking-widest text-base font-bold text-white flex items-center gap-2">
                <span>NARAD // नारद</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gradient-to-r from-narad-saffron/20 to-narad-cyan/20 text-narad-gold border border-narad-saffron/40">
                  V7
                </span>
              </h1>
              <p className="text-[10px] font-mono tracking-wider text-narad-textMuted uppercase flex items-center gap-1.5" title="NARAD — Neural Assistant for Rizz & Absolute Destruction">
                <span className="text-narad-saffron">PERSONAL AI CORE</span>
                <span className="text-narad-textDim">•</span>
                <span>STANDALONE</span>
              </p>
            </div>
          </div>

          <div
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-narad-border text-[10px] font-mono text-narad-textDim bg-narad-card/50"
            title={isHealthy ? "Local loopback connection active" : "Local backend unreachable"}
          >
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]' : 'bg-rose-500 shadow-[0_0_6px_#f43f5e]'}`} />
            <span className="font-semibold">{isHealthy ? 'LIVE' : 'OFFLINE'}</span>
          </div>
        </div>

        {/* 2. New Briefing Action — Premium gradient button */}
        <button
          onClick={onNewChat}
          className="w-full py-2.5 px-3 rounded-lg bg-gradient-to-r from-narad-saffron/15 via-narad-cyan/10 to-narad-saffron/15 hover:from-narad-saffron/25 hover:via-narad-cyan/20 hover:to-narad-saffron/25 border border-narad-saffron/40 hover:border-narad-saffron/70 text-narad-gold font-mono text-xs font-semibold flex items-center justify-center gap-2 transition-all duration-200 active:scale-[0.98] group shadow-hud-saffron cursor-pointer"
        >
          <Plus size={15} className="group-hover:rotate-90 transition-transform duration-300 text-narad-saffron" />
          <span>NEW BRIEFING</span>
        </button>
      </div>

      {/* 3. Search Briefings */}
      <div className="px-3 py-2.5 border-b border-narad-border/50">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-narad-textDim" />
          <input
            type="text"
            placeholder="Search briefings..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-narad-bg/80 border border-narad-border/40 focus:border-narad-cyan/60 rounded-lg px-2.5 pl-8 py-1.5 text-xs text-narad-text placeholder:text-narad-textDim font-mono focus:outline-none transition-all duration-200 focus:shadow-[0_0_12px_rgba(0,240,255,0.1)]"
          />
        </div>
      </div>

      {/* 4. Conversation History List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        <div className="px-2 py-1.5 text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-narad-saffron/60" />
            Briefing History
          </span>
          <span className="text-[9px] bg-narad-card/50 px-1.5 py-0.5 rounded border border-narad-border/30">{filteredChats.length}</span>
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

      {/* 5. Subsystem Navigation */}
      <div className="p-2.5 border-t border-narad-border bg-narad-bg/40 flex flex-col gap-1">
        <button
          onClick={onOpenSmritiMemory}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-mono text-white hover:text-narad-gold bg-narad-card/30 hover:bg-narad-card/60 border border-narad-border/60 hover:border-narad-saffron/40 transition-all duration-200 cursor-pointer group text-left w-full shadow-sm"
          title="Open Smṛti Personal Memory Vault (V3.0)"
        >
          <Brain size={14} className="text-narad-saffron group-hover:scale-110 transition-transform flex-shrink-0 animate-pulse" />
          <span className="font-medium">Smṛti Memory</span>
          <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-narad-saffron/15 border border-narad-saffron/35 text-narad-gold font-mono">
            {memoryCount > 0 ? `${memoryCount} FACTS` : 'V3.0'}
          </span>
        </button>

        <button
          onClick={onOpenKnowledgeBase}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-mono text-white hover:text-narad-cyan bg-narad-card/30 hover:bg-narad-card/60 border border-narad-border/60 hover:border-narad-cyan/40 transition-all duration-200 cursor-pointer group text-left w-full shadow-sm"
          title="Open Local Knowledge Base Vault (V2.2)"
        >
          <Database size={14} className="text-narad-cyan group-hover:scale-110 transition-transform flex-shrink-0" />
          <span className="font-medium">Knowledge Base</span>
          <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-narad-cyan/15 border border-narad-cyan/35 text-narad-cyan font-mono">
            {knowledgeDocCount > 0 ? `${knowledgeDocCount} DOCS` : 'V2.2'}
          </span>
        </button>

        <button
          onClick={onOpenAgentTools}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-mono text-white hover:text-narad-gold bg-narad-card/30 hover:bg-narad-card/60 border border-narad-border/60 hover:border-narad-saffron/40 transition-all duration-200 cursor-pointer group text-left w-full shadow-sm"
          title="Inspect 36 registered Krīya tools and security permission policies"
        >
          <Wrench size={14} className="text-narad-saffron group-hover:rotate-45 transition-transform flex-shrink-0" />
          <span className="font-medium">Agent Tools</span>
          <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-narad-saffron/15 border border-narad-saffron/35 text-narad-gold font-mono">
            36 TOOLS
          </span>
        </button>

        <button
          onClick={onOpenSystemSettings}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-mono text-white hover:text-narad-cyan bg-narad-card/30 hover:bg-narad-card/60 border border-narad-border/60 hover:border-narad-cyan/40 transition-all duration-200 cursor-pointer group text-left w-full shadow-sm"
          title="Open system voice, audio diagnostic & engine settings"
        >
          <Settings size={14} className="text-narad-cyan group-hover:rotate-90 transition-transform flex-shrink-0" />
          <span className="font-medium">System Settings</span>
          <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-narad-card border border-narad-border/60 text-narad-cyan font-mono">
            CONFIG
          </span>
        </button>
      </div>

      {/* 6. System Identity */}
      <SystemIdentity />
    </aside>
  );
}
