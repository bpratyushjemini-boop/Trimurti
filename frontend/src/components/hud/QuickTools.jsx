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
        <span className="hud-section-title flex items-center gap-1.5">
          <Zap size={12} className="text-narad-saffron" />
          Quick Directives
        </span>
        <span className="text-[9px] font-mono text-narad-gold/70">READY</span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {tools.map((t, idx) => {
          const Icon = t.icon;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectPrompt(t.prompt)}
              className="p-2 rounded-lg bg-narad-card/40 hover:bg-narad-card/70 border border-narad-border/30 hover:border-narad-saffron/40 text-left transition-all duration-200 group cursor-pointer"
            >
              <div className="flex items-center gap-1.5 text-slate-300 group-hover:text-narad-gold transition-colors text-[11px] font-medium">
                <Icon size={11} className="text-narad-saffron/70 group-hover:text-narad-saffron flex-shrink-0" />
                <span className="truncate">{t.name}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
