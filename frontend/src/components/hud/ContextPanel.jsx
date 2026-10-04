import React from 'react';
import { BookOpen, HardDrive, Hash } from 'lucide-react';

export default function ContextPanel({ messages = [] }) {
  const totalCharacters = messages.reduce((acc, m) => acc + (m.content ? m.content.length : 0), 0);
  const estimatedTokens = Math.round(totalCharacters / 3.8);
  const maxContextWindow = 8192;
  const contextPercentage = Math.min(Math.round((estimatedTokens / maxContextWindow) * 100), 100);

  const barColor = contextPercentage > 80 
    ? 'from-rose-500 to-rose-400' 
    : contextPercentage > 50 
    ? 'from-narad-saffron to-amber-400' 
    : 'from-narad-cyan to-cyan-400';

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="hud-section-title flex items-center gap-1.5">
          <BookOpen size={12} className="text-narad-saffron" />
          Working Memory
        </span>
        <span className="text-[10px] font-mono text-narad-textDim">
          {estimatedTokens.toLocaleString()} / {maxContextWindow.toLocaleString()}
        </span>
      </div>

      {/* Progress Bar with dynamic color */}
      <div className="w-full bg-narad-bg/80 rounded-full h-1.5 overflow-hidden border border-narad-border/30">
        <div 
          className={`bg-gradient-to-r ${barColor} h-full rounded-full transition-all duration-500 shadow-[0_0_8px_rgba(0,240,255,0.3)]`}
          style={{ width: `${Math.max(contextPercentage, 3)}%` }}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono pt-0.5">
        <div className="flex items-center justify-between p-1.5 rounded-md bg-narad-card/30 border border-narad-border/25">
          <span className="text-narad-textDim flex items-center gap-1">
            <Hash size={9} />
            Msgs:
          </span>
          <span className="text-white font-medium">{messages.length}</span>
        </div>

        <div className="flex items-center justify-between p-1.5 rounded-md bg-narad-card/30 border border-narad-border/25">
          <span className="text-narad-textDim flex items-center gap-1">
            <HardDrive size={9} className="text-emerald-400" />
            Smriti:
          </span>
          <span className="text-emerald-400 text-[10px] font-semibold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_4px_#34d399]" />
            ON
          </span>
        </div>
      </div>
    </div>
  );
}
