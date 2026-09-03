import React from 'react';
import { Shield, Cpu, HardDrive, ArrowRight, Lock } from 'lucide-react';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function WelcomeHero({ onSelectPrompt }) {
  const starterPrompts = [
    {
      title: "System Diagnostic Briefing",
      desc: "Check local engine status, loopback latency, and session tracking.",
      prompt: "Provide a comprehensive system diagnostic briefing of the active NARAD core."
    },
    {
      title: "Single-User Architecture",
      desc: "Review private standalone design, storage boundaries, and vault security.",
      prompt: "Explain the private, single-user architecture of NARAD and its zero-cloud local persistence model."
    },
    {
      title: "Local Persistence Audit",
      desc: "Inspect active SQLite database tables and local briefing storage.",
      prompt: "Confirm current local persistence capabilities and isolation boundaries in Milestone 2."
    },
    {
      title: "Milestone Roadmap",
      desc: "Understand what is active in V1 and what unlocks in Milestone 3.",
      prompt: "What capabilities are currently active in NARAD V1, and what AI providers will connect in Milestone 3?"
    }
  ];

  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-6 max-w-3xl mx-auto select-none my-auto">
      {/* Central ARC Reactor Core */}
      <div className="relative mb-6">
        <NaradCoreIcon size={72} animated={true} />
        <div className="absolute inset-0 bg-narad-cyan/15 blur-2xl rounded-full -z-10" />
      </div>

      {/* Hero Headings */}
      <h3 className="font-display text-2xl font-bold tracking-widest text-white mb-2 flex items-center justify-center gap-2">
        <span>NARAD PERSONAL AI ASSISTANT</span>
      </h3>
      <p className="text-xs font-mono text-narad-textMuted leading-relaxed max-w-lg mb-8">
        Private, single-user intelligence system. Operating strictly on your local machine with isolated SQLite storage and zero external data exposure.
      </p>

      {/* Starter Directives Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full text-left">
        {starterPrompts.map((item, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => onSelectPrompt(item.prompt)}
            className="hud-panel p-3.5 rounded-lg border border-narad-border hover:border-narad-cyan/50 hover:bg-narad-card/70 transition-all duration-200 group text-left cursor-pointer flex flex-col justify-between shadow-hud-subtle"
          >
            <div>
              <div className="text-white text-xs font-medium flex items-center justify-between mb-1">
                <span className="group-hover:text-narad-cyan transition-colors">{item.title}</span>
                <ArrowRight size={13} className="text-narad-textDim group-hover:text-narad-cyan group-hover:translate-x-0.5 transition-all" />
              </div>
              <p className="text-[11px] text-narad-textDim font-sans leading-relaxed">
                {item.desc}
              </p>
            </div>
            <div className="mt-2.5 pt-2 border-t border-narad-border/30 flex items-center justify-between text-[10px] font-mono text-narad-textDim">
              <span className="text-narad-cyan/70">DIRECTIVE // 0{idx + 1}</span>
              <span className="group-hover:text-white transition-colors">CLICK TO LOAD</span>
            </div>
          </button>
        ))}
      </div>

      {/* Trust & Architecture Badges */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-4 text-[10px] font-mono text-narad-textDim">
        <span className="flex items-center gap-1.5">
          <Lock size={12} className="text-emerald-400" />
          <span>PRIVATE SINGLE-USER SYSTEM</span>
        </span>
        <span>•</span>
        <span className="flex items-center gap-1.5">
          <HardDrive size={12} className="text-narad-cyan" />
          <span>LOCAL SQLITE PERSISTENCE</span>
        </span>
        <span>•</span>
        <span className="flex items-center gap-1.5">
          <Cpu size={12} className="text-narad-blue" />
          <span>MODEL-AGNOSTIC ROUTER (V1)</span>
        </span>
      </div>
    </div>
  );
}
