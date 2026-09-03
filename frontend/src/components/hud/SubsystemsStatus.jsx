import React from 'react';
import { Layers } from 'lucide-react';

export default function SubsystemsStatus() {
  const subsystems = [
    { name: 'NARAD', role: 'Interface & Router', status: 'ONLINE [V1]', active: true },
    { name: 'Smriti', role: 'Long-term Memory', status: 'STANDBY [V2]', active: false },
    { name: 'Manthan', role: 'Deep Reasoning', status: 'STANDBY [V2]', active: false },
    { name: 'Kriya', role: 'Agent Execution', status: 'STANDBY [V2]', active: false },
    { name: 'Vaani', role: 'Voice Synthesizer', status: 'STANDBY [V2]', active: false },
    { name: 'Trinetra', role: 'Multimodal Vision', status: 'STANDBY [V2]', active: false },
  ];

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <Layers size={12} className="text-narad-cyan" />
          Trimurti Subsystems
        </span>
        <span className="text-[9px] font-mono text-narad-textDim">
          FABRIC v0.1
        </span>
      </div>

      <div className="space-y-1 text-xs font-mono">
        {subsystems.map((sub, idx) => (
          <div 
            key={idx}
            className="flex items-center justify-between p-1.5 rounded bg-narad-card/30 border border-narad-border/20"
          >
            <div className="flex flex-col">
              <span className={sub.active ? 'text-narad-cyan font-semibold' : 'text-slate-400'}>
                {sub.name}
              </span>
              <span className="text-[9px] text-narad-textDim font-sans">
                {sub.role}
              </span>
            </div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
              sub.active 
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
                : 'bg-narad-card text-narad-textDim border-narad-border/40'
            }`}>
              {sub.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
