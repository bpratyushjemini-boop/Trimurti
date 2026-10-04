import React, { useState } from 'react';
import { Eye, ChevronDown, ChevronUp, Monitor, CheckCircle, XCircle, RefreshCw, AlertCircle, Shield } from 'lucide-react';
import { api } from '../../services/api';

export default function VisualDebugPanel({ agentTelemetry = {} }) {
  const [isOpen, setIsOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [imgKey, setImgKey] = useState(Date.now());
  const [isRefreshing, setIsRefreshing] = useState(false);

  const observationCount = agentTelemetry?.observation_count || 0;
  const activeApp = agentTelemetry?.last_active_app || 'None detected';
  const visionStatus = agentTelemetry?.vision_status || 'IDLE';
  const lastVisionResult = agentTelemetry?.last_vision_result;
  const lastVerification = agentTelemetry?.last_verification_result;

  const handleRefresh = () => {
    setIsRefreshing(true);
    setImgError(false);
    setImgKey(Date.now());
    setTimeout(() => setIsRefreshing(false), 600);
  };

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle border border-narad-border/60 bg-narad-surface/80">
      {/* Header with Collapsible Toggle */}
      <div 
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <Eye size={12} className="text-cyan-400 animate-pulse" />
          Trinetra Vision [V5]
        </span>
        <div className="flex items-center gap-2">
          <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded border font-bold ${
            visionStatus === 'OBSERVING'
              ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse'
              : 'bg-narad-card text-cyan-400 border-cyan-500/30'
          }`}>
            {visionStatus}
          </span>
          <button
            type="button"
            className="text-narad-textDim hover:text-cyan-400 transition-colors"
            title={isOpen ? "Collapse Trinetra Panel" : "Expand Trinetra Panel"}
          >
            {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Mini quick-status bar even when collapsed */}
      <div className="flex items-center justify-between text-[9px] font-mono text-narad-textDim pt-1">
        <span className="flex items-center gap-1">
          <Monitor size={10} className="text-amber-400" />
          App: <strong className="text-zinc-200">{activeApp}</strong>
        </span>
        <span>
          Obs: <strong className="text-cyan-300">{observationCount}/5</strong>
        </span>
      </div>

      {/* Expanded Content */}
      {isOpen && (
        <div className="pt-2 border-t border-narad-border/40 space-y-2.5 font-mono text-[10px]">
          {/* Latest Screenshot Thumbnail */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[9px] text-narad-textDim">
              <span>Latest Screen Observation</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleRefresh();
                }}
                className="hover:text-cyan-400 flex items-center gap-1 cursor-pointer transition-colors"
                title="Reload screenshot preview"
              >
                <RefreshCw size={10} className={isRefreshing ? "animate-spin" : ""} />
                Refresh
              </button>
            </div>
            <div className="relative w-full h-32 rounded-lg overflow-hidden border border-narad-border bg-black/70 flex items-center justify-center">
              {!imgError ? (
                <img
                  key={imgKey}
                  src={`${api.getLatestScreenshotUrl()}&k=${imgKey}`}
                  alt="Trinetra Screen Capture"
                  className="w-full h-full object-contain"
                  onError={() => setImgError(true)}
                />
              ) : (
                <div className="text-center p-2 text-narad-textDim space-y-1">
                  <Monitor size={20} className="mx-auto opacity-30 text-cyan-400" />
                  <p className="text-[9px]">No recent screenshot available</p>
                </div>
              )}
            </div>
          </div>

          {/* Verification Badge */}
          <div className="p-2 rounded bg-zinc-900/60 border border-zinc-800 space-y-1">
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-zinc-500">Action Verification:</span>
              {lastVerification === true ? (
                <span className="flex items-center gap-1 text-emerald-400 font-bold">
                  <CheckCircle size={10} /> PASS
                </span>
              ) : lastVerification === false ? (
                <span className="flex items-center gap-1 text-rose-400 font-bold">
                  <XCircle size={10} /> FAIL
                </span>
              ) : (
                <span className="text-zinc-400">NONE</span>
              )}
            </div>

            {/* Vision Inference Summary */}
            <div className="text-[9px] pt-1 border-t border-zinc-800/80">
              <span className="text-zinc-500">Vision Analysis:</span>
              <p className="text-zinc-300 font-sans text-[10px] mt-0.5 max-h-16 overflow-y-auto leading-relaxed whitespace-pre-wrap">
                {lastVisionResult || 'No visual model inference executed yet.'}
              </p>
            </div>
          </div>

          {/* Safety Notice */}
          <div className="text-[8px] text-zinc-500 flex items-center gap-1">
            <Shield size={9} className="text-emerald-500" />
            <span>Privacy: Local capture, auto-pruned, 5-observation safety limit.</span>
          </div>
        </div>
      )}
    </div>
  );
}
