import React, { useState, useEffect } from 'react';
import { ShieldAlert, CheckCircle2, XCircle, AlertTriangle, Layers } from 'lucide-react';

export default function AgentPermissionModal({ confirmation, onDecision }) {
  if (!confirmation) return null;

  const {
    confirmation_id,
    task_id,
    level = 2,
    description = 'Operation requested',
    action_summary,
    reason,
    tool_name
  } = confirmation;

  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setIsSubmitting(false);
  }, [confirmation_id]);

  const displaySummary = action_summary || description;
  const isHighRisk = level >= 3;

  const handleDecision = (decision) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    onDecision(confirmation_id, decision, task_id);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-lg bg-zinc-950 border border-amber-500/40 rounded-xl shadow-2xl overflow-hidden shadow-amber-500/10">
        {/* Top Header Banner */}
        <div className={`px-5 py-4 border-b flex items-center gap-3 ${
          isHighRisk ? 'bg-red-950/40 border-red-500/30' : 'bg-amber-950/40 border-amber-500/30'
        }`}>
          <div className={`p-2 rounded-lg ${isHighRisk ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
            {isHighRisk ? <ShieldAlert className="w-6 h-6 animate-pulse" /> : <AlertTriangle className="w-6 h-6" />}
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-wider uppercase text-zinc-100 font-mono">
              Action Permission Required
            </h3>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold uppercase tracking-wider ${
              isHighRisk ? 'bg-red-500/20 text-red-300 border border-red-500/40' : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
            }`}>
              Level {level} — {isHighRisk ? 'High Risk Operation' : 'Confirmation Required'}
            </span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4 font-mono text-xs">
          <div className="bg-zinc-900/90 border border-zinc-800 rounded-lg p-4 space-y-2">
            <div className="text-[11px] text-zinc-400 uppercase tracking-wide">Directive</div>
            <div className="text-sm font-semibold text-zinc-100 break-words">
              {displaySummary}
            </div>
            {tool_name && (
              <div className="text-[10px] text-zinc-500">
                Kriya Tool: <span className="text-zinc-300">{tool_name}</span>
              </div>
            )}
            {task_id && (
              <div className="text-[10px] text-zinc-500">
                Task Scope: <span className="text-cyan-400">{task_id}</span>
              </div>
            )}
          </div>

          {reason && (
            <div className="text-zinc-400 text-[11px] bg-zinc-900/40 p-3 rounded border border-zinc-800/60">
              <span className="text-zinc-300 font-semibold">Policy Rationale: </span>
              {reason}
            </div>
          )}

          <p className="text-[11px] text-zinc-400 leading-relaxed">
            NARAD will not perform this action without your explicit authorization. Choose to allow once, pre-authorize for this task, or deny execution.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="px-6 py-4 bg-zinc-900/60 border-t border-zinc-800 flex items-center justify-end gap-2.5 flex-wrap">
          <button
            onClick={() => handleDecision('deny')}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-mono font-medium text-red-300 bg-red-950/40 hover:bg-red-900/60 border border-red-500/40 rounded-lg transition-colors disabled:opacity-50"
          >
            <XCircle className="w-4 h-4" />
            DENY
          </button>
          {task_id && (
            <button
              onClick={() => handleDecision('allow_task')}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-mono font-semibold text-sky-200 bg-sky-950/60 hover:bg-sky-900/60 border border-sky-500/40 rounded-lg transition-colors disabled:opacity-50"
            >
              <Layers className="w-4 h-4 text-sky-400" />
              ALLOW FOR THIS TASK
            </button>
          )}
          <button
            onClick={() => handleDecision('allow')}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-mono font-bold text-emerald-950 bg-emerald-400 hover:bg-emerald-300 rounded-lg shadow-lg shadow-emerald-500/20 transition-colors disabled:opacity-50"
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-950" />
            ALLOW ONCE
          </button>
        </div>
      </div>
    </div>
  );
}
