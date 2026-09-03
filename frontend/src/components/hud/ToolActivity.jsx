import React from 'react';
import { Terminal, CheckCircle2, Clock } from 'lucide-react';

export default function ToolActivity() {
  const simulatedLogs = [
    {
      action: 'Session Persistence Synced',
      status: 'OK',
      source: 'SQLite // DB'
    },
    {
      action: 'Model Abstraction Verified',
      status: 'OK',
      source: 'FastAPI // Core'
    },
    {
      action: 'Kriya Tool Dispatcher',
      status: 'STANDBY',
      source: 'Kriya Engine'
    }
  ];

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <Terminal size={12} className="text-narad-cyan" />
          Tool Telemetry
        </span>
        <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-narad-card border border-narad-border text-narad-textDim">
          STANDBY
        </span>
      </div>

      <div className="space-y-1.5">
        {simulatedLogs.map((log, idx) => (
          <div 
            key={idx} 
            className="flex items-center justify-between p-1.5 rounded bg-narad-card/35 border border-narad-border/30 text-[10px] font-mono"
          >
            <div className="flex items-center gap-1.5 truncate mr-2">
              {log.status === 'OK' ? (
                <CheckCircle2 size={11} className="text-emerald-400 flex-shrink-0" />
              ) : (
                <Clock size={11} className="text-narad-textDim flex-shrink-0" />
              )}
              <span className="text-slate-300 truncate">{log.action}</span>
            </div>
            <span className={log.status === 'OK' ? 'text-emerald-400' : 'text-narad-textDim'}>
              {log.status}
            </span>
          </div>
        ))}
      </div>

      <div className="text-[10px] font-sans text-narad-textDim pt-1 border-t border-narad-border/30">
        Autonomous agent execution unlocks in Kriya integration phase.
      </div>
    </div>
  );
}
