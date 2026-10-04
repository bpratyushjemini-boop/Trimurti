import React from 'react';
import { Activity, Database, Server, Clock } from 'lucide-react';

export default function SystemStatus({ healthData, runtimeTruth = null, lastTelemetry }) {
  const isOnline = (runtimeTruth?.system?.backend === 'ONLINE') || (healthData?.status === 'online');
  const displayLatency = lastTelemetry?.latency_ms 
    ? `${lastTelemetry.latency_ms}ms` 
    : (runtimeTruth?.query_latency_ms ? `${runtimeTruth.query_latency_ms}ms` : '< 2ms (Loopback)');

  const osInfo = runtimeTruth?.identity 
    ? `${runtimeTruth.identity.platform} (${runtimeTruth.identity.architecture})`
    : 'Darwin (arm64)';

  const activeApp = runtimeTruth?.identity?.active_application && runtimeTruth.identity.active_application !== 'UNKNOWN'
    ? runtimeTruth.identity.active_application
    : null;

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle hud-corner-tl hud-corner-br">
      <div className="flex items-center justify-between">
        <span className="hud-section-title flex items-center gap-1.5">
          <Activity size={12} className="text-narad-saffron" />
          Core Status
        </span>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md border flex items-center gap-1.5 ${
          isOnline 
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
            : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]' : 'bg-rose-400'}`} />
          {isOnline ? 'OPERATIONAL' : 'DISCONNECTED'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1.5 border-t border-narad-border/30">
        <div className="bg-narad-bg/60 p-2 rounded-lg border border-narad-border/30">
          <div className="flex items-center gap-1 text-[10px] text-narad-textDim mb-0.5">
            <Server size={10} className="text-narad-cyan" />
            <span>Host / OS</span>
          </div>
          <span className="text-white font-medium text-[10.5px] truncate block" title={osInfo}>
            {osInfo}
          </span>
        </div>

        <div className="bg-narad-bg/60 p-2 rounded-lg border border-narad-border/30">
          <div className="flex items-center gap-1 text-[10px] text-narad-textDim mb-0.5">
            <Database size={10} className="text-narad-saffron" />
            <span>Database</span>
          </div>
          <span className="text-narad-cyan font-medium text-[10.5px] truncate block">
            {runtimeTruth?.system?.database === 'ONLINE' || healthData?.database === 'connected' ? 'SQLite ✓' : 'SQLite'}
          </span>
        </div>
      </div>

      {activeApp && (
        <div className="flex items-center justify-between text-[9.5px] font-mono bg-narad-bg/40 px-2 py-1 rounded border border-narad-border/20">
          <span className="text-narad-textDim">ACTIVE APP:</span>
          <span className="text-narad-gold font-semibold truncate max-w-[150px]">{activeApp}</span>
        </div>
      )}

      <div className="flex items-center justify-between text-[10px] font-mono text-narad-textDim px-0.5 pt-0.5">
        <span className="flex items-center gap-1" title="Latency">
          <Clock size={10} className="text-narad-cyan/60" />
          <span>{displayLatency}</span>
        </span>
        <span className="text-emerald-400/80 text-[9px]">Single-User Core</span>
      </div>
    </div>
  );
}
