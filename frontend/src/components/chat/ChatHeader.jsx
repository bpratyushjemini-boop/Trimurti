import React from 'react';
import { Cpu, PanelRight, Volume2 } from 'lucide-react';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function ChatHeader({
  title = 'Active Briefing',
  activeProvider = 'groq',
  activeModel = 'openai/gpt-oss-120b',
  onToggleRightPanel,
  isRightPanelOpen = true,
  isVoiceMode = false,
  onToggleVoiceMode
}) {
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <header className="h-14 border-b border-narad-border bg-narad-surface/90 backdrop-blur-xl px-6 flex items-center justify-between z-10 select-none relative overflow-hidden">
      {/* Subtle top saffron accent */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-narad-saffron/40 to-transparent" />

      {/* Title & Status */}
      <div className="flex items-center gap-3 min-w-0">
        <NaradCoreIcon size={24} animated={true} className="flex-shrink-0" />
        <div className="flex items-center gap-2 min-w-0">
          <h2 className="font-display font-semibold text-sm tracking-wide text-white truncate max-w-md">
            {title}
          </h2>
          <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-narad-card border border-narad-border text-[10px] font-mono text-narad-cyan flex-shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]" />
            <span>127.0.0.1</span>
          </span>
        </div>
      </div>

      {/* Model Indicator, Voice Mode & Panel Toggle */}
      <div className="flex items-center gap-2.5">
        {/* Live Clock */}
        <span className="hidden lg:inline text-[10px] font-mono text-narad-textDim px-2 py-0.5 rounded bg-narad-card/30 border border-narad-border/30">
          {timeStr}
        </span>

        {/* VĀṆĪ Voice Mode Toggle */}
        {onToggleVoiceMode && (
          <button
            onClick={onToggleVoiceMode}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono transition-all duration-200 cursor-pointer ${
              isVoiceMode
                ? 'bg-cyan-500/20 text-narad-cyan border-cyan-500/50 shadow-glow-cyan font-semibold'
                : 'bg-narad-card text-narad-textDim border-narad-border hover:text-white hover:bg-narad-card/80 hover:border-narad-border/80'
            }`}
            title={isVoiceMode ? 'Voice Mode is ON' : 'Enable Voice Mode'}
          >
            <Volume2 size={13} className={isVoiceMode ? 'text-narad-cyan animate-pulse' : ''} />
            <span className="hidden sm:inline">VOICE:</span>
            <span>{isVoiceMode ? 'ON' : 'OFF'}</span>
          </button>
        )}

        {/* Model Badge */}
        <div 
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-narad-card border border-narad-border text-xs font-mono shadow-hud-subtle"
          title={`Active Route: ${activeProvider} -> ${activeModel}`}
        >
          <Cpu size={13} className="text-narad-saffron" />
          <span className="hidden md:inline text-narad-textDim">MODEL:</span>
          <span className="font-semibold text-white tracking-wide max-w-[140px] truncate">{activeModel.toUpperCase()}</span>
        </div>

        {/* Right Telemetry Toggle */}
        {onToggleRightPanel && (
          <button
            onClick={onToggleRightPanel}
            className={`p-1.5 rounded-lg border transition-all duration-200 cursor-pointer ${
              isRightPanelOpen 
                ? 'bg-narad-cyan/15 text-narad-cyan border-narad-cyan/40 shadow-[0_0_10px_rgba(0,240,255,0.15)]' 
                : 'text-narad-textDim hover:text-white border-narad-border/60 hover:bg-narad-card'
            }`}
            title={isRightPanelOpen ? "Collapse Telemetry" : "Expand Telemetry"}
          >
            <PanelRight size={15} />
          </button>
        )}
      </div>
    </header>
  );
}
