import React, { useState, useEffect, useRef } from 'react';
import { 
  Zap, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  Pause, 
  Play, 
  SkipForward, 
  RotateCcw, 
  Ban, 
  ShieldCheck, 
  ShieldAlert, 
  Cpu, 
  Layers,
  ChevronDown,
  ChevronRight,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { naradApi } from '../../services/api';

const AUTONOMY_MODES = [
  { id: 'CHAT_ONLY', label: 'Chat Only (L0)', color: 'text-slate-400 bg-slate-800/40 border-slate-700' },
  { id: 'SUGGEST', label: 'Suggest Only (L1)', color: 'text-blue-400 bg-blue-900/30 border-blue-700' },
  { id: 'SUPERVISED', label: 'Supervised (L2 - Default)', color: 'text-amber-400 bg-amber-900/30 border-amber-700' },
  { id: 'TASK_AUTONOMY', label: 'Task Autonomy (L3)', color: 'text-cyan-400 bg-cyan-900/30 border-cyan-700' },
];

const PRESET_OBJECTIVES = [
  { title: 'Prepare Dev Environment', prompt: 'prepare my development environment' },
  { title: 'Diagnose Project Health', prompt: 'check my narad project and tell me what is wrong' },
  { title: 'Frontend Build Diagnostics', prompt: 'check why frontend build is failing' },
  { title: 'Production Build Prep', prompt: 'prepare the project for a production build' },
];

export default function TaskEnginePanel() {
  const [activeTask, setActiveTask] = useState(null);
  const [autonomyMode, setAutonomyMode] = useState('SUPERVISED');
  const [customObjective, setCustomObjective] = useState('');
  const [dryRun, setDryRun] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState(true);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  // Poll active task and autonomy mode
  useEffect(() => {
    let isMounted = true;

    const fetchStatus = async () => {
      try {
        const modeRes = await naradApi.getAutonomyMode();
        if (isMounted && modeRes?.mode) {
          setAutonomyMode(modeRes.mode);
        }

        const taskRes = await naradApi.getActiveAutonomousTask();
        if (isMounted) {
          if (taskRes?.active && taskRes?.task) {
            setActiveTask(taskRes.task);
          } else if (activeTask && (activeTask.status === 'EXECUTING' || activeTask.status === 'PLANNING')) {
            // Re-fetch latest status of task
            const details = await naradApi.getAutonomousTaskDetails(activeTask.task_id).catch(() => null);
            if (details) setActiveTask(details);
          }
        }
      } catch (err) {
        // Silent polling error
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeTask?.task_id]);

  const handleSetMode = async (mode) => {
    try {
      setLoading(true);
      const res = await naradApi.setAutonomyMode(mode);
      if (res?.mode) setAutonomyMode(res.mode);
    } catch (err) {
      alert(`Could not set autonomy mode: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleStartTask = async (objective) => {
    if (!objective.trim()) return;
    try {
      setLoading(true);
      const res = await naradApi.createAutonomousTask(objective, dryRun);
      setActiveTask(res);
      setCustomObjective('');
    } catch (err) {
      alert(`Task start failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    if (!activeTask) return;
    try {
      setLoading(true);
      await naradApi.pauseAutonomousTask(activeTask.task_id);
      const updated = await naradApi.getAutonomousTaskDetails(activeTask.task_id);
      setActiveTask(updated);
    } catch (err) {
      alert(`Pause failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async () => {
    if (!activeTask) return;
    try {
      setLoading(true);
      await naradApi.resumeAutonomousTask(activeTask.task_id);
      const updated = await naradApi.getAutonomousTaskDetails(activeTask.task_id);
      setActiveTask(updated);
    } catch (err) {
      alert(`Resume failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!activeTask) return;
    try {
      setLoading(true);
      await naradApi.cancelAutonomousTask(activeTask.task_id);
      const updated = await naradApi.getAutonomousTaskDetails(activeTask.task_id);
      setActiveTask(updated);
    } catch (err) {
      alert(`Cancel failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSkipStep = async (stepId = null) => {
    if (!activeTask) return;
    try {
      setLoading(true);
      await naradApi.skipAutonomousTaskStep(activeTask.task_id, stepId);
      const updated = await naradApi.getAutonomousTaskDetails(activeTask.task_id);
      setActiveTask(updated);
    } catch (err) {
      alert(`Skip failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRetryStep = async (stepId = null) => {
    if (!activeTask) return;
    try {
      setLoading(true);
      await naradApi.retryAutonomousTaskStep(activeTask.task_id, stepId);
      const updated = await naradApi.getAutonomousTaskDetails(activeTask.task_id);
      setActiveTask(updated);
    } catch (err) {
      alert(`Retry failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmDecision = async (decision) => {
    if (!activeTask?.pending_confirmation) return;
    try {
      setLoading(true);
      const confId = activeTask.pending_confirmation.confirmation_id;
      await naradApi.confirmAction(confId, decision, activeTask.task_id);
      const updated = await naradApi.getAutonomousTaskDetails(activeTask.task_id);
      setActiveTask(updated);
    } catch (err) {
      alert(`Confirmation failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadHistory = async () => {
    try {
      const list = await naradApi.listAutonomousTasks(10);
      setHistory(list || []);
      setShowHistory(!showHistory);
    } catch (err) {
      console.warn('History load error:', err);
    }
  };

  const totalSteps = activeTask?.steps?.length || 0;
  const completedSteps = activeTask?.steps?.filter(s => s.status === 'completed').length || 0;
  const progressPercent = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-3 shadow-hud-subtle border border-narad-border/40">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="hud-section-title flex items-center gap-1.5">
          <Zap size={13} className="text-narad-saffron animate-pulse" />
          Task Engine
        </span>
        <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-md border bg-narad-saffron/12 border-narad-saffron/35 text-narad-gold">
          V6
        </span>
      </div>

      {/* Autonomy Mode Selector */}
      <div className="space-y-1">
        <label className="text-[9px] font-mono text-narad-textDim uppercase tracking-wider flex items-center justify-between">
          <span>Autonomy Policy Mode</span>
          <span className="text-zinc-500">{autonomyMode}</span>
        </label>
        <select
          value={autonomyMode}
          onChange={(e) => handleSetMode(e.target.value)}
          disabled={loading}
          className="w-full text-[11px] font-mono bg-zinc-900/90 border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-zinc-200 focus:outline-none focus:border-cyan-500 cursor-pointer"
        >
          {AUTONOMY_MODES.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {/* Active Task Card */}
      {activeTask ? (
        <div className="space-y-2.5 pt-1">
          {/* Objective & Status Badge */}
          <div className="p-2.5 rounded-lg bg-zinc-950/70 border border-zinc-800 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="text-[11px] font-semibold text-zinc-100 leading-tight">
                {activeTask.objective}
              </div>
              <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border shrink-0 ${
                activeTask.status === 'COMPLETED'
                  ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-400'
                  : activeTask.status === 'VERIFY_FAILED'
                  ? 'bg-rose-950/60 border-rose-500/60 text-rose-300 font-bold'
                  : activeTask.status === 'PARTIALLY_COMPLETED'
                  ? 'bg-amber-950/40 border-amber-500/40 text-amber-400'
                  : activeTask.status === 'WAITING_FOR_PERMISSION'
                  ? 'bg-rose-950/50 border-rose-500/60 text-rose-300 animate-pulse'
                  : activeTask.status === 'PAUSED'
                  ? 'bg-amber-950/30 border-amber-500/30 text-amber-300'
                  : activeTask.status === 'FAILED'
                  ? 'bg-rose-950/40 border-rose-500/40 text-rose-400'
                  : 'bg-cyan-950/30 border-cyan-500/40 text-cyan-300 animate-pulse'
              }`}>
                {activeTask.status}
              </span>
            </div>

            {/* Progress Bar */}
            <div className="space-y-1">
              <div className="flex justify-between text-[9px] font-mono text-zinc-400">
                <span>Progress: {completedSteps} / {totalSteps} steps</span>
                <span>{progressPercent}%</span>
              </div>
              <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div 
                  className={`h-full transition-all duration-300 ${
                    activeTask.status === 'FAILED' || activeTask.status === 'VERIFY_FAILED' ? 'bg-rose-500' : 'bg-cyan-400'
                  }`}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Pending Confirmation Prompt (Batch Permissions) */}
            {activeTask.status === 'WAITING_FOR_PERMISSION' && activeTask.pending_confirmation && (
              <div className="p-2.5 rounded bg-rose-950/30 border border-rose-500/50 space-y-2 mt-1">
                <div className="flex items-center gap-1.5 text-rose-300 text-[10px] font-bold uppercase tracking-wider">
                  <AlertTriangle size={12} className="text-rose-400" />
                  Action Requires Authorization
                </div>
                <div className="text-[10px] text-zinc-200 font-mono">
                  {activeTask.pending_confirmation.action_summary}
                </div>
                <div className="grid grid-cols-3 gap-1.5 pt-1">
                  <button
                    onClick={() => handleConfirmDecision('allow')}
                    disabled={loading}
                    className="px-2 py-1 rounded text-[9px] font-mono font-bold bg-emerald-600/30 border border-emerald-500/50 text-emerald-300 hover:bg-emerald-600/50 cursor-pointer"
                  >
                    Allow Once
                  </button>
                  <button
                    onClick={() => handleConfirmDecision('allow_task')}
                    disabled={loading}
                    className="px-2 py-1 rounded text-[9px] font-mono font-bold bg-cyan-600/40 border border-cyan-400/60 text-cyan-200 hover:bg-cyan-600/60 cursor-pointer shadow-sm shadow-cyan-500/20"
                    title="Pre-authorizes safe repeated actions for the lifespan of this task only"
                  >
                    Allow for Task
                  </button>
                  <button
                    onClick={() => handleConfirmDecision('deny')}
                    disabled={loading}
                    className="px-2 py-1 rounded text-[9px] font-mono font-bold bg-rose-600/30 border border-rose-500/50 text-rose-300 hover:bg-rose-600/50 cursor-pointer"
                  >
                    Deny
                  </button>
                </div>
              </div>
            )}

            {/* Step Execution Timeline */}
            <div className="space-y-1.5 pt-1">
              <button
                onClick={() => setExpandedSteps(!expandedSteps)}
                className="flex items-center justify-between w-full text-[9px] font-mono text-zinc-400 hover:text-zinc-200 cursor-pointer"
              >
                <span>Steps Timeline ({totalSteps})</span>
                {expandedSteps ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              </button>

              {expandedSteps && (
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {activeTask.steps.map((step, idx) => (
                    <div 
                      key={step.step_id || idx}
                      className={`p-1.5 rounded border text-[10px] font-mono ${
                        step.status === 'completed'
                          ? 'bg-emerald-950/20 border-emerald-500/30 text-zinc-300'
                          : step.status === 'executing'
                          ? 'bg-cyan-950/30 border-cyan-500/40 text-cyan-200 animate-pulse'
                          : step.status === 'waiting_permission'
                          ? 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                          : step.status === 'failed'
                          ? 'bg-rose-950/30 border-rose-500/30 text-rose-300'
                          : step.status === 'skipped'
                          ? 'bg-zinc-900/40 border-zinc-800 text-zinc-500'
                          : 'bg-zinc-900/30 border-zinc-800/60 text-zinc-400'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1.5 font-medium truncate max-w-[180px]">
                          {step.status === 'completed' && <CheckCircle2 size={11} className="text-emerald-400 shrink-0" />}
                          {step.status === 'executing' && <Cpu size={11} className="text-cyan-400 shrink-0 animate-spin" />}
                          {step.status === 'waiting_permission' && <AlertTriangle size={11} className="text-rose-400 shrink-0" />}
                          {step.status === 'failed' && <XCircle size={11} className="text-rose-400 shrink-0" />}
                          {step.status === 'skipped' && <ArrowRight size={11} className="text-zinc-500 shrink-0" />}
                          {step.status === 'pending' && <span className="w-2.5 h-2.5 rounded-full bg-zinc-700 shrink-0 inline-block" />}
                          <span className="truncate">{step.title}</span>
                        </span>
                        <span className="text-[8px] uppercase tracking-wider text-zinc-500">
                          {step.status}
                        </span>
                      </div>

                      {/* Verification detail */}
                      {step.verification_result?.details && (
                        <div className="text-[8px] text-zinc-400 mt-1 pl-4 border-l border-zinc-700/60 truncate">
                          {step.verification_result.details}
                        </div>
                      )}

                      {/* Failure message */}
                      {step.error && (
                        <div className="text-[8px] text-rose-400 mt-1 pl-4 border-l border-rose-500/40">
                          {step.error}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Zero Fake Success Honest Report Summary */}
            {activeTask.honest_report && (
              <div className="p-2 rounded bg-zinc-900/80 border border-zinc-800 text-[9px] font-mono space-y-1">
                <div className="text-cyan-400 font-bold uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck size={11} />
                  Zero Fake Success Report
                </div>
                <div className="text-zinc-300">
                  {activeTask.honest_report.honest_summary}
                </div>
                <div className="text-zinc-500 text-[8px] flex justify-between">
                  <span>Actions: {activeTask.honest_report.total_actions}</span>
                  <span>Duration: {activeTask.honest_report.elapsed_seconds}s</span>
                </div>
              </div>
            )}

            {/* Task Controls */}
            <div className="flex items-center justify-between gap-1.5 pt-1 border-t border-zinc-800/80">
              {activeTask.status === 'PAUSED' ? (
                <button
                  onClick={handleResume}
                  disabled={loading}
                  className="flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-mono bg-emerald-600/30 border border-emerald-500/50 text-emerald-300 hover:bg-emerald-600/50 cursor-pointer"
                >
                  <Play size={10} /> Resume
                </button>
              ) : activeTask.status === 'EXECUTING' ? (
                <button
                  onClick={handlePause}
                  disabled={loading}
                  className="flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-mono bg-amber-600/30 border border-amber-500/50 text-amber-300 hover:bg-amber-600/50 cursor-pointer"
                >
                  <Pause size={10} /> Pause
                </button>
              ) : null}

              {(activeTask.status === 'EXECUTING' || activeTask.status === 'WAITING_FOR_PERMISSION') && (
                <button
                  onClick={() => handleSkipStep()}
                  disabled={loading}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-zinc-800 text-zinc-300 hover:bg-zinc-700 cursor-pointer"
                >
                  <SkipForward size={10} /> Skip
                </button>
              )}

              {activeTask.status === 'FAILED' && (
                <button
                  onClick={() => handleRetryStep()}
                  disabled={loading}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-cyan-600/30 border border-cyan-500/50 text-cyan-300 hover:bg-cyan-600/50 cursor-pointer"
                >
                  <RotateCcw size={10} /> Retry
                </button>
              )}

              {(activeTask.status === 'EXECUTING' || activeTask.status === 'PAUSED' || activeTask.status === 'WAITING_FOR_PERMISSION') && (
                <button
                  onClick={handleCancel}
                  disabled={loading}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-rose-950/40 border border-rose-500/40 text-rose-300 hover:bg-rose-900/50 cursor-pointer ml-auto"
                >
                  <Ban size={10} /> Cancel
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* Preset Objective Quick Launchers */
        <div className="space-y-2">
          <div className="text-[9px] font-mono text-narad-textDim uppercase tracking-wider">
            Autonomous Workflows
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            {PRESET_OBJECTIVES.map((item, idx) => (
              <button
                key={idx}
                onClick={() => handleStartTask(item.prompt)}
                disabled={loading}
                className="flex items-center justify-between p-2 rounded-lg bg-zinc-900/50 border border-zinc-800/80 hover:border-cyan-500/50 hover:bg-cyan-950/20 text-left transition-colors cursor-pointer group"
              >
                <div className="flex flex-col">
                  <span className="text-[11px] font-semibold text-zinc-200 group-hover:text-cyan-300">
                    {item.title}
                  </span>
                  <span className="text-[8px] font-mono text-zinc-500 truncate max-w-[200px]">
                    {item.prompt}
                  </span>
                </div>
                <ArrowRight size={12} className="text-zinc-600 group-hover:text-cyan-400 transition-transform group-hover:translate-x-0.5" />
              </button>
            ))}
          </div>

          {/* Custom Objective Input */}
          <div className="pt-2 border-t border-zinc-800/80 space-y-1.5">
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={customObjective}
                onChange={(e) => setCustomObjective(e.target.value)}
                placeholder="Custom objective (e.g. check status)..."
                disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleStartTask(customObjective);
                }}
                className="flex-1 text-[10px] font-mono bg-zinc-900/90 border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-cyan-500"
              />
              <button
                onClick={() => handleStartTask(customObjective)}
                disabled={loading || !customObjective.trim()}
                className="p-1.5 rounded-lg bg-cyan-600/30 border border-cyan-500/50 text-cyan-300 hover:bg-cyan-600/50 disabled:opacity-40 cursor-pointer"
                title="Start Autonomous Task"
              >
                <Play size={12} />
              </button>
            </div>

            <div className="flex items-center justify-between text-[9px] font-mono text-zinc-400">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="rounded border-zinc-700 text-cyan-500 focus:ring-0"
                />
                <span>Dry Run Mode</span>
              </label>
              <button
                onClick={handleLoadHistory}
                className="text-zinc-500 hover:text-zinc-300 underline cursor-pointer"
              >
                {showHistory ? 'Hide History' : 'Task History'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Task History List */}
      {showHistory && history.length > 0 && (
        <div className="pt-2 border-t border-zinc-800/80 space-y-1">
          <div className="text-[9px] font-mono text-zinc-400 uppercase tracking-wider">
            Recent Task Runs
          </div>
          <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
            {history.map((t) => (
              <div
                key={t.task_id}
                onClick={() => setActiveTask(t)}
                className="p-1.5 rounded border border-zinc-800/80 bg-zinc-900/40 text-[9px] font-mono flex items-center justify-between cursor-pointer hover:border-zinc-700"
              >
                <span className="text-zinc-300 truncate max-w-[150px]">{t.objective}</span>
                <span className={`px-1 rounded text-[8px] ${
                  t.status === 'COMPLETED' ? 'text-emerald-400' : 'text-zinc-400'
                }`}>
                  {t.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
