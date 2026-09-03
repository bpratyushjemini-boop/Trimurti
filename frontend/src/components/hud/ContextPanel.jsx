import React from 'react';
import { BookOpen, HardDrive, Hash } from 'lucide-react';

export default function ContextPanel({ messages = [] }) {
  // Rough token estimation: words / 0.75 or characters / 4
  const totalCharacters = messages.reduce((acc, m) => acc + (m.content ? m.content.length : 0), 0);
  const estimatedTokens = Math.round(totalCharacters / 3.8);
  const maxContextWindow = 8192; // simulated baseline
  const contextPercentage = Math.min(Math.round((estimatedTokens / maxContextWindow) * 100), 100);

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <BookOpen size={12} className="text-narad-cyan" />
          Working Memory
        </span>
        <span className="text-[10px] font-mono text-narad-textDim">
          {estimatedTokens} / {maxContextWindow} TOKENS
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-narad-bg/80 rounded-full h-1.5 overflow-hidden border border-narad-border/40">
        <div 
          className="bg-narad-cyan h-full rounded-full transition-all duration-300 shadow-[0_0_8px_#00f0ff]"
          style={{ width: `${Math.max(contextPercentage, 3)}%` }}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono pt-1">
        <div className="flex items-center justify-between p-1.5 rounded bg-narad-card/40 border border-narad-border/30">
          <span className="text-narad-textDim flex items-center gap-1">
            <Hash size={10} />
            Messages:
          </span>
          <span className="text-white font-medium">{messages.length}</span>
        </div>

        <div className="flex items-center justify-between p-1.5 rounded bg-narad-card/40 border border-narad-border/30">
          <span className="text-narad-textDim flex items-center gap-1">
            <HardDrive size={10} />
            Smriti:
          </span>
          <span className="text-narad-textDim text-[10px]">STANDBY</span>
        </div>
      </div>
    </div>
  );
}
