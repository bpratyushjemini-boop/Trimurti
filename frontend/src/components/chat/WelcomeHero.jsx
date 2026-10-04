import React from 'react';
import { Shield, Cpu, HardDrive, ArrowRight, Lock, Sparkles } from 'lucide-react';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function WelcomeHero({ onSelectPrompt }) {
  const starterPrompts = [
    {
      title: "System Diagnostic",
      desc: "Check engine status, loopback latency, and session tracking.",
      prompt: "Provide a comprehensive system diagnostic briefing of the active NARAD core.",
      icon: "⚡"
    },
    {
      title: "Architecture Review",
      desc: "Private standalone design, storage boundaries, and vault security.",
      prompt: "Explain the private, single-user architecture of NARAD and its zero-cloud local persistence model.",
      icon: "🛡️"
    },
    {
      title: "Persistence Audit",
      desc: "Inspect active SQLite tables and local briefing storage.",
      prompt: "Confirm current local persistence capabilities and isolation boundaries in Milestone 2.",
      icon: "💾"
    },
    {
      title: "Milestone Roadmap",
      desc: "Active capabilities in V7 and what unlocks next.",
      prompt: "What capabilities are currently active in NARAD V7, and what AI providers will connect in Milestone 3?",
      icon: "🚀"
    }
  ];

  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-6 max-w-3xl mx-auto select-none my-auto relative">
      {/* Atmospheric Background Glow */}
      <div className="absolute inset-0 bg-gradient-hero pointer-events-none" />
      <div className="narad-glow-ring w-64 h-64 -top-8 left-1/2 -translate-x-1/2" />
      
      {/* Central Core Icon — Large, atmospheric */}
      <div className="relative mb-8 animate-float">
        <NaradCoreIcon size={88} animated={true} />
        <div className="absolute inset-0 bg-narad-cyan/10 blur-3xl rounded-full -z-10 scale-150" />
        <div className="absolute inset-0 bg-narad-saffron/5 blur-2xl rounded-full -z-10 scale-125" />
      </div>

      {/* Hero Headings */}
      <h3 className="font-display text-2xl font-bold tracking-[0.2em] text-white mb-1 flex items-center justify-center gap-3 relative z-10">
        <span>NARAD // नारद</span>
      </h3>
      <p className="font-display text-xs tracking-[0.15em] text-narad-saffron/80 mb-1">
        दिव्य दूत
      </p>
      <p className="text-[11px] font-mono text-narad-gold/80 tracking-wider uppercase mb-3" title="NARAD — Neural Assistant for Rizz & Absolute Destruction">
        Neural Assistant for Rizz & Absolute Destruction
      </p>
      <p className="text-xs font-mono text-narad-textMuted leading-relaxed max-w-md mb-8 relative z-10">
        Private, single-user intelligence system operating on your local machine.
        <br />
        <span className="text-narad-textDim">Isolated storage • Zero external exposure • Model-agnostic router</span>
      </p>

      {/* Starter Directives Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full text-left relative z-10">
        {starterPrompts.map((item, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => onSelectPrompt(item.prompt)}
            className="hud-panel p-4 rounded-xl border border-narad-border hover:border-narad-saffron/40 hover:bg-narad-card/50 transition-all duration-250 group text-left cursor-pointer flex flex-col justify-between shadow-hud-subtle hover:shadow-hud-saffron animate-slideUp"
            style={{ animationDelay: `${idx * 80}ms` }}
          >
            <div>
              <div className="text-white text-xs font-semibold flex items-center justify-between mb-1.5">
                <span className="flex items-center gap-2 group-hover:text-narad-gold transition-colors">
                  <span className="text-sm">{item.icon}</span>
                  {item.title}
                </span>
                <ArrowRight size={13} className="text-narad-textDim group-hover:text-narad-saffron group-hover:translate-x-1 transition-all duration-200" />
              </div>
              <p className="text-[11px] text-narad-textDim font-sans leading-relaxed">
                {item.desc}
              </p>
            </div>
            <div className="mt-3 pt-2 border-t border-narad-border/20 flex items-center justify-between text-[10px] font-mono text-narad-textDim">
              <span className="text-narad-saffron/60">DIRECTIVE // 0{idx + 1}</span>
              <span className="group-hover:text-narad-gold transition-colors">LOAD →</span>
            </div>
          </button>
        ))}
      </div>

      {/* Trust & Architecture Badges */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-4 text-[10px] font-mono text-narad-textDim relative z-10">
        <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-narad-card/30 border border-narad-border/30">
          <Lock size={11} className="text-emerald-400" />
          <span>PRIVATE SYSTEM</span>
        </span>
        <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-narad-card/30 border border-narad-border/30">
          <HardDrive size={11} className="text-narad-cyan" />
          <span>LOCAL SQLITE</span>
        </span>
        <span className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-narad-card/30 border border-narad-border/30">
          <Cpu size={11} className="text-narad-saffron" />
          <span>MODEL-AGNOSTIC</span>
        </span>
      </div>
    </div>
  );
}
