import React from 'react';
import { Zap, ShieldCheck, ListOrdered, FileText } from 'lucide-react';

export default function QuickTools({ onSelectPrompt }) {
  const tools = [
    {
      name: 'System Audit',
      icon: ShieldCheck,
      prompt: 'Execute a full diagnostic audit on NARAD core systems, active latency, and local persistence integrity.'
    },
    {
      name: 'Summarize Context',
      icon: FileText,
      prompt: 'Provide a concise structured summary of our current briefing session along with key takeaways.'
    },
    {
      name: 'Task Breakdown',
      icon: ListOrdered,
      prompt: 'Decompose the following objective into prioritized sequential execution steps: '
    },
    {
      name: 'Security Scan',
      icon: Zap,
      prompt: 'Verify environment sandboxing, SQLite local storage isolation, and zero-leakage security boundaries.'
    }
  ];

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <Zap size={12} className="text-narad-cyan" />
          Quick Directives
        </span>
        <span className="text-[9px] font-mono text-narad-cyan/80">READY</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {tools.map((t, idx) => {
          const Icon = t.icon;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectPrompt(t.prompt)}
              className="p-2 rounded-lg bg-narad-card/50 hover:bg-narad-card border border-narad-border/40 hover:border-narad-cyan/40 text-left transition-all duration-150 group cursor-pointer"
            >
              <div className="flex items-center gap-1.5 text-slate-300 group-hover:text-narad-cyan transition-colors text-xs font-medium mb-0.5">
                <Icon size={12} className="text-narad-cyan/80" />
                <span className="truncate">{t.name}</span>
              </div>
              <span className="text-[9px] font-mono text-narad-textDim block truncate">
                Click to load
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
