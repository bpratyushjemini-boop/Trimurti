import React from 'react';
import { 
  Activity, 
  Cpu, 
  Database, 
  Layers, 
  ShieldCheck, 
  Radio, 
  Zap,
  RefreshCw
} from 'lucide-react';

export default function RightSidebar({ 
  healthData, 
  onRefreshHealth 
}) {
  const isOnline = healthData?.status === 'online';

  return (
    <aside className="w-80 h-full bg-narad-surface border-l border-narad-border flex flex-col select-none overflow-y-auto flex-shrink-0">
      {/* HUD Header */}
      <div className="p-4 border-b border-narad-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-narad-cyan animate-pulse" />
          <h2 className="font-display font-semibold text-xs tracking-widest text-white uppercase">
            System Telemetry
          </h2>
        </div>

        <button 
          onClick={onRefreshHealth}
          className="p-1 rounded text-narad-textDim hover:text-narad-cyan hover:bg-narad-card transition-colors"
          title="Refresh Telemetry"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Core Status Card */}
        <div className="hud-panel rounded-lg p-3 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase">
              Core Status
            </span>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border flex items-center gap-1 ${
              isOnline 
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
                : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-400 animate-ping' : 'bg-rose-400'}`} />
              {isOnline ? 'OPERATIONAL' : 'OFFLINE'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1 border-t border-narad-border/30">
            <div>
              <span className="text-[10px] text-narad-textDim block">Engine</span>
              <span className="text-white">FastAPI v0.1</span>
            </div>
            <div>
              <span className="text-[10px] text-narad-textDim block">Database</span>
              <span className="text-narad-cyan truncate block">{healthData?.database || 'SQLite'}</span>
            </div>
          </div>
        </div>

        {/* AI Provider Telemetry */}
        <div className="hud-panel rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
              <Cpu size={12} className="text-narad-cyan" />
              Active Provider
            </span>
            <span className="text-[9px] font-mono px-1 rounded bg-narad-card border border-narad-border text-narad-textMuted">
              AGNOSTIC
            </span>
          </div>

          <div className="bg-narad-bg/70 p-2 rounded border border-narad-border/40">
            <div className="text-xs font-mono font-semibold text-white">
              {healthData?.active_provider ? healthData.active_provider.toUpperCase() : 'NARAD-MOCK'}
            </div>
            <div className="text-[10px] text-narad-textDim mt-0.5">
              Model abstraction layer loaded. Ready for external AI providers.
            </div>
          </div>

          {/* Provider Pipeline Slots */}
          <div className="pt-2 border-t border-narad-border/30">
            <div className="text-[10px] font-mono text-narad-textDim mb-1.5 uppercase">
              Configured Connectors
            </div>
            <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
              <div className="p-1.5 rounded bg-narad-card/40 border border-narad-border/30 flex items-center justify-between">
                <span className="text-narad-textMuted">Gemini</span>
                <span className="text-narad-textDim">SLOT 1</span>
              </div>
              <div className="p-1.5 rounded bg-narad-card/40 border border-narad-border/30 flex items-center justify-between">
                <span className="text-narad-textMuted">OpenRouter</span>
                <span className="text-narad-textDim">SLOT 2</span>
              </div>
              <div className="p-1.5 rounded bg-narad-card/40 border border-narad-border/30 flex items-center justify-between">
                <span className="text-narad-textMuted">Groq</span>
                <span className="text-narad-textDim">SLOT 3</span>
              </div>
              <div className="p-1.5 rounded bg-narad-card/40 border border-narad-border/30 flex items-center justify-between">
                <span className="text-narad-textMuted">Claude</span>
                <span className="text-narad-textDim">SLOT 4</span>
              </div>
            </div>
          </div>
        </div>

        {/* TRIMURTI Ecosystem Subsystems Status */}
        <div className="hud-panel rounded-lg p-3 space-y-2.5">
          <div className="flex items-center gap-1.5 text-[10px] font-mono tracking-wider text-narad-textDim uppercase">
            <Layers size={12} className="text-narad-cyan" />
            Trimurti Subsystems
          </div>

          <div className="space-y-1.5 text-xs font-mono">
            <div className="flex items-center justify-between p-1.5 rounded bg-narad-card/30">
              <span className="text-narad-cyan font-semibold">NARAD</span>
              <span className="text-[10px] text-emerald-400">ONLINE [V1]</span>
            </div>
            <div className="flex items-center justify-between p-1.5 rounded bg-narad-card/30">
              <span className="text-narad-textDim">Smriti (Memory)</span>
              <span className="text-[10px] text-narad-textDim">STANDBY</span>
            </div>
            <div className="flex items-center justify-between p-1.5 rounded bg-narad-card/30">
              <span className="text-narad-textDim">Manthan (Reasoning)</span>
              <span className="text-[10px] text-narad-textDim">STANDBY</span>
            </div>
            <div className="flex items-center justify-between p-1.5 rounded bg-narad-card/30">
              <span className="text-narad-textDim">Kriya (Execution)</span>
              <span className="text-[10px] text-narad-textDim">STANDBY</span>
            </div>
          </div>
        </div>

        {/* Security & Sandbox Audit Card */}
        <div className="hud-panel rounded-lg p-3 border-l-2 border-l-narad-cyan space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-white">
            <ShieldCheck size={14} className="text-narad-cyan" />
            <span>Vault Security: Isolated</span>
          </div>
          <p className="text-[10px] font-sans text-narad-textDim leading-normal">
            Zero credentials exposed. Local SQLite persistence. API keys confined to private environment variables.
          </p>
        </div>
      </div>
    </aside>
  );
}
