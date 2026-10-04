import React from 'react';
import { Terminal, CheckCircle2, Clock, Zap, Cpu } from 'lucide-react';

export default function ToolActivity({ lastTelemetry = null, isSending = false, messages = [] }) {
  let executedTools = lastTelemetry?.tools_executed || [];
  if ((!executedTools || executedTools.length === 0) && messages.length > 0) {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role === 'assistant' && msg.metadata_json) {
        try {
          const meta = typeof msg.metadata_json === 'string' ? JSON.parse(msg.metadata_json) : msg.metadata_json;
          if (meta?.tools_executed && meta.tools_executed.length > 0) {
            executedTools = meta.tools_executed;
            break;
          }
        } catch {
          // ignore
        }
      }
    }
  }

  const logs = [];

  if (isSending) {
    logs.push({ action: 'Knowledge Search', status: 'EXECUTING', source: 'Knowledge Base' });
    logs.push({ action: 'Krīya Dispatcher', status: 'BUSY', source: 'Krīya Engine' });
  }

  if (executedTools && executedTools.length > 0) {
    executedTools.forEach((t) => {
      let label = t.name;
      let subStatus = null;
      let resultCount = null;

      if (t.name === 'search_knowledge') {
        const detail = t.arguments?.query ? `"${t.arguments.query.slice(0, 14)}..."` : '';
        label = detail ? `KB // ${detail}` : 'Knowledge Search';
        const res = t.result || {};
        const count = res.results_found ?? res.count ?? (Array.isArray(res.results) ? res.results.length : 0);
        resultCount = count;
        subStatus = `${count} results`;
      } else if (t.name === 'web_search') {
        const detail = t.arguments?.query ? `"${t.arguments.query.slice(0, 16)}..."` : '';
        label = detail ? `Web // ${detail}` : 'Web Search';
        const res = t.result || {};
        const count = res.results_found ?? res.count ?? (Array.isArray(res.results) ? res.results.length : 0);
        resultCount = count;
        subStatus = `${count} results`;
      } else if (t.name === 'calculator') {
        label = `calc(${t.arguments?.expression || ''})`;
      } else if (t.name === 'get_current_time' || t.name === 'get_current_date') {
        label = `${t.name.replace('get_current_', '')}(${t.arguments?.location || 'UTC'})`;
      } else if (t.name === 'save_memory') {
        label = `Smṛti.save(${t.arguments?.key || 'fact'})`;
      } else if (t.name === 'delete_memory') {
        label = `Smṛti.del(${t.arguments?.key || 'fact'})`;
      } else if (t.name === 'retrieve_memory') {
        label = `Smṛti.get(${t.arguments?.key || 'fact'})`;
      } else if (t.name === 'list_memories') {
        label = 'Smṛti.list()';
      }

      const isFailed = t.result?.error || t.result?.status === 'error';
      logs.push({ action: label, status: isFailed ? 'FAILED' : 'OK', subStatus, resultCount, source: 'Krīya' });
    });
  }

  if (!isSending) {
    logs.push({ action: 'Krīya Dispatcher', status: 'ACTIVE', source: 'Krīya' });
  }
  logs.push({ action: 'Smṛti Vault', status: 'ONLINE', source: 'SQLite' });

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="hud-section-title flex items-center gap-1.5">
          <Terminal size={12} className="text-narad-saffron" />
          Tool Activity
        </span>
        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-md border transition-colors flex items-center gap-1 ${
          isSending
            ? 'bg-narad-saffron/12 text-narad-saffron border-narad-saffron/30 animate-pulse'
            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
        }`}>
          {isSending ? (
            <><Zap size={9} className="animate-spin" /> EXEC</>
          ) : (
            <><Cpu size={9} /> READY</>
          )}
        </span>
      </div>

      <div className="space-y-1">
        {logs.slice(0, 4).map((log, idx) => (
          <div 
            key={idx} 
            className="flex items-center justify-between p-1.5 rounded-md bg-narad-card/25 border border-narad-border/20 text-[10px] font-mono"
          >
            <div className="flex items-center gap-1.5 truncate mr-2">
              {log.status === 'OK' || log.status === 'ACTIVE' || log.status === 'ONLINE' ? (
                <CheckCircle2 size={10} className="text-emerald-400 flex-shrink-0" />
              ) : log.status === 'BUSY' || log.status === 'EXECUTING' ? (
                <Zap size={10} className="text-narad-saffron flex-shrink-0 animate-pulse" />
              ) : log.status === 'FAILED' ? (
                <span className="w-2 h-2 rounded-full bg-rose-400 flex-shrink-0" />
              ) : (
                <Clock size={10} className="text-narad-textDim flex-shrink-0" />
              )}
              <span className="text-slate-300 truncate">{log.action}</span>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              {log.subStatus && (
                <span className={`text-[8px] px-1 py-0.5 rounded border ${
                  log.resultCount > 0 
                    ? 'bg-cyan-500/10 text-cyan-300 border-cyan-500/25' 
                    : 'bg-slate-800/40 text-slate-400 border-slate-700/40'
                }`}>
                  {log.subStatus}
                </span>
              )}
              <span className={
                log.status === 'OK' || log.status === 'ACTIVE' || log.status === 'ONLINE' 
                  ? 'text-emerald-400 font-semibold' 
                  : log.status === 'BUSY' || log.status === 'EXECUTING'
                  ? 'text-narad-saffron' 
                  : log.status === 'FAILED'
                  ? 'text-rose-400 font-semibold'
                  : 'text-narad-textDim'
              }>
                {log.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
