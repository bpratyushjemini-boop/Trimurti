import React from 'react';
import { Activity, Database, Server, Clock } from 'lucide-react';

export default function SystemStatus({ healthData, lastTelemetry }) {
  const isOnline = healthData?.status === 'online';
  const displayLatency = lastTelemetry?.latency_ms 
    ? `${lastTelemetry.latency_ms}ms` 
    : '< 2ms (Loopback)';

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <Activity size={12} className="text-narad-cyan" />
          Core Status
        </span>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border flex items-center gap-1.5 ${
          isOnline 
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
            : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]' : 'bg-rose-400'}`} />
          {isOnline ? 'OPERATIONAL' : 'DISCONNECTED'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1.5 border-t border-narad-border/40">
        <div className="bg-narad-bg/60 p-2 rounded border border-narad-border/40">
          <div className="flex items-center gap-1 text-[10px] text-narad-textDim mb-0.5">
            <Server size={10} />
            <span>Engine</span>
          </div>
          <span className="text-white font-medium">FastAPI v0.110</span>
        </div>

        <div className="bg-narad-bg/60 p-2 rounded border border-narad-border/40">
          <div className="flex items-center gap-1 text-[10px] text-narad-textDim mb-0.5">
            <Database size={10} />
            <span>Database</span>
          </div>
          <span className="text-narad-cyan font-medium truncate block">
            {healthData?.database === 'connected' ? 'SQLite (Active)' : 'SQLite'}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] font-mono text-narad-textDim px-0.5 pt-0.5">
        <span className="flex items-center gap-1" title="Model latency or loopback latency">
          <Clock size={11} />
          <span>Latency: {displayLatency}</span>
        </span>
        <span className="text-emerald-400/90">Single-User Standalone</span>
      </div>
    </div>
  );
}
