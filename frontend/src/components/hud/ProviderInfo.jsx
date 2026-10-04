import React from 'react';
import { Cpu, Lock, Zap, Shield, Database, Wrench, Globe, HardDrive } from 'lucide-react';

export default function ProviderInfo({ 
  activeProvider = 'groq', 
  activeModel = 'openai/gpt-oss-120b',
  isConfigured = false,
  healthData = null,
  runtimeTruth = null,
  lastTelemetry = null
}) {
  // Ground-truth provider and model resolution
  const currentProvider = (
    runtimeTruth?.inference?.provider ||
    lastTelemetry?.provider ||
    activeProvider ||
    'groq'
  ).toLowerCase();

  const effectiveModel = (
    runtimeTruth?.inference?.model ||
    lastTelemetry?.model ||
    activeModel ||
    'openai/gpt-oss-120b'
  );

  const isKeyInvalid = lastTelemetry?.status === 'api_error' || lastTelemetry?.status === 'client_error';
  const fallbackOccurred = Boolean(lastTelemetry?.fallback);
  const fallbackPath = lastTelemetry?.fallback_path;
  const fallbackReason = lastTelemetry?.fallback_reason;
  const routeReason = lastTelemetry?.route_reason || runtimeTruth?.router?.task_category || healthData?.task_category || 'GENERAL_CHAT';
  const isFallbackReady = runtimeTruth?.router?.failover_enabled ?? (healthData?.fallback_ready ?? false);

  // Execution Locality Truth
  const executionMode = (
    runtimeTruth?.inference?.execution_mode ||
    (lastTelemetry?.execution_mode ? lastTelemetry.execution_mode.toUpperCase() : null) ||
    (['ollama', 'huggingface', 'task-engine', 'manthan', 'deterministic-engine'].includes(currentProvider) ? 'LOCAL' : 'CLOUD')
  );
  const isLocal = executionMode === 'LOCAL';

  // Network Required Truth
  const networkRequired = runtimeTruth?.inference?.network_required ?? (
    lastTelemetry?.network_required ?? (!isLocal)
  );

  // Autonomy Truth
  const autonomyLevel = runtimeTruth?.autonomy?.level ?? 2;
  const autonomyMode = runtimeTruth?.autonomy?.mode || 'SUPERVISED';
  const mutationsAllowed = runtimeTruth?.autonomy?.computer_mutations_allowed ?? false;

  // Memory Truth
  const storedMemories = runtimeTruth?.memory?.stored_memory_count ?? 0;
  const memoryStatus = runtimeTruth?.memory?.status || 'ONLINE';

  // Tools Truth
  const toolsCount = runtimeTruth?.tools?.length ?? 0;

  // Provider Matrix Truth (distinguishing CONFIGURED != AVAILABLE != ACTIVE)
  const matrix = runtimeTruth?.router?.provider_matrix || healthData?.provider_matrix || {};
  const getProviderInfo = (pid) => {
    if (matrix[pid]) {
      return {
        configured: Boolean(matrix[pid].configured ?? matrix[pid].is_configured),
        available: Boolean(matrix[pid].available ?? (matrix[pid].status === 'ONLINE' || matrix[pid].health_state === 'AVAILABLE')),
        active: Boolean(matrix[pid].active ?? (currentProvider === pid)),
        status: matrix[pid].status || (matrix[pid].configured ? 'ONLINE' : 'NOT CONFIGURED')
      };
    }
    const found = healthData?.available_providers?.find((p) => p.id === pid);
    if (!found || !found.is_configured) {
      return { configured: false, available: false, active: currentProvider === pid, status: 'NOT CONFIGURED' };
    }
    return {
      configured: true,
      available: found.health?.status !== 'OFFLINE',
      active: currentProvider === pid,
      status: found.health?.status || 'ONLINE'
    };
  };

  const isRateLimited = lastTelemetry?.status === 'rate_limited' || (fallbackReason && fallbackReason.includes('rate_limit'));
  const providerState = isRateLimited ? 'RATE LIMITED' : executionMode;

  const providers = [
    { id: 'groq', name: 'GROQ LPU', label: 'GROQ' },
    { id: 'nvidia', name: 'NVIDIA NIM', label: 'NVIDIA' },
    { id: 'gemini', name: 'GEMINI', label: 'GEMINI' },
    { id: 'openrouter', name: 'OPENROUTER', label: 'OPENROUTER' },
    { id: 'ollama', name: 'OLLAMA', label: 'OLLAMA' },
    { id: 'huggingface', name: 'HUGGING FACE', label: 'HF LOCAL' },
  ];

  const currentProviderLabel = `${currentProvider.toUpperCase()} // ${providerState}`;

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle border border-narad-border/40 font-mono">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="hud-section-title flex items-center gap-1.5 font-display">
          <Cpu size={12} className="text-narad-saffron" />
          Runtime Truth & Router
        </span>
        <div className="flex items-center gap-1.5">
          <span className={`text-[9px] px-1.5 py-0.5 rounded-md border ${
            isFallbackReady
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
              : 'bg-slate-500/10 text-slate-400 border-slate-500/30'
          }`}>
            {isFallbackReady ? 'FAILOVER ✓' : 'STANDALONE'}
          </span>
        </div>
      </div>

      {/* Active Model & Telemetry Card */}
      <div className="bg-narad-bg/70 p-2.5 rounded-lg border border-narad-border/40 space-y-2">
        <div className="flex items-center justify-between text-[10px] text-narad-textDim uppercase">
          <span className="tracking-wider">ACTIVE INFERENCE</span>
          {lastTelemetry?.latency_ms !== undefined && (
            <span className="text-narad-cyan font-bold">
              {lastTelemetry.latency_ms}ms
            </span>
          )}
        </div>

        {/* Active Provider & Model */}
        <div className="flex items-center justify-between text-xs font-semibold text-white">
          <span className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${isKeyInvalid ? 'bg-rose-400' : (isLocal ? 'bg-amber-400' : 'bg-emerald-400')} animate-pulse`} />
            <span className="text-narad-gold font-bold">{currentProviderLabel}</span>
          </span>
          <span className="text-[10px] text-slate-300 truncate max-w-[120px]" title={effectiveModel}>
            {effectiveModel}
          </span>
        </div>

        {/* Locality & Network Truth Badges */}
        <div className="grid grid-cols-2 gap-1.5 pt-0.5 text-[8.5px]">
          <div className="flex items-center justify-between p-1 rounded bg-narad-card/60 border border-narad-border/20">
            <span className="text-narad-textDim flex items-center gap-1">
              <HardDrive size={9} className="text-narad-cyan" />
              MODE
            </span>
            <span className={`font-bold px-1 rounded ${isLocal ? 'text-amber-400 bg-amber-500/10' : 'text-emerald-400 bg-emerald-500/10'}`}>
              {executionMode}
            </span>
          </div>

          <div className="flex items-center justify-between p-1 rounded bg-narad-card/60 border border-narad-border/20">
            <span className="text-narad-textDim flex items-center gap-1">
              <Globe size={9} className="text-narad-saffron" />
              NETWORK
            </span>
            <span className={`font-bold px-1 rounded ${networkRequired ? 'text-sky-300 bg-sky-500/10' : 'text-emerald-400 bg-emerald-500/10'}`}>
              {networkRequired ? 'REQUIRED' : 'NONE (OFFLINE)'}
            </span>
          </div>
        </div>

        {/* Autonomy Truth */}
        <div className="flex items-center justify-between pt-0.5 text-[9px]">
          <span className="text-narad-textDim flex items-center gap-1">
            <Shield size={10} className="text-purple-400" />
            AUTONOMY:
          </span>
          <span className="px-1.5 py-0.5 rounded-md bg-purple-500/10 border border-purple-500/30 text-purple-300 font-semibold text-[8px]">
            L{autonomyLevel} — {autonomyMode} {mutationsAllowed ? '(MUTATIONS ON)' : '(SUPERVISED)'}
          </span>
        </div>

        {/* Memory & Tools Telemetry */}
        <div className="grid grid-cols-2 gap-1.5 pt-0.5 text-[8.5px]">
          <div className="flex items-center justify-between p-1 rounded bg-narad-card/60 border border-narad-border/20">
            <span className="text-narad-textDim flex items-center gap-1">
              <Database size={9} className="text-emerald-400" />
              SMṚTI
            </span>
            <span className="text-emerald-300 font-semibold">
              {storedMemories} items
            </span>
          </div>

          <div className="flex items-center justify-between p-1 rounded bg-narad-card/60 border border-narad-border/20">
            <span className="text-narad-textDim flex items-center gap-1">
              <Wrench size={9} className="text-amber-400" />
              TOOLS
            </span>
            <span className="text-amber-300 font-semibold">
              {toolsCount} active
            </span>
          </div>
        </div>

        {/* Route reason */}
        <div className="flex items-center justify-between pt-0.5 text-[9px]">
          <span className="text-narad-textDim">ROUTE REASON:</span>
          <span className="px-1.5 py-0.5 rounded-md bg-narad-card border border-narad-saffron/25 text-narad-saffron font-semibold text-[8px]">
            {routeReason}
          </span>
        </div>

        {lastTelemetry?.why_this_choice && (
          <div className="pt-1 text-[8.5px] text-slate-400 leading-tight border-t border-narad-border/20">
            <span className="text-narad-cyan/90 font-semibold">WHY: </span>
            {lastTelemetry.why_this_choice}
          </div>
        )}

        {fallbackOccurred && (
          <div className="mt-1 p-1.5 rounded-md bg-amber-500/12 border border-amber-500/35 text-[10px] text-amber-300 flex items-center justify-between animate-pulse">
            <span className="flex items-center gap-1 font-semibold">
              <Zap size={10} className="text-amber-400" />
              <span>{fallbackPath || 'FAILOVER'} // LIVE</span>
            </span>
            {fallbackReason && (
              <span className="text-[8px] text-amber-200 uppercase opacity-80">
                ({fallbackReason})
              </span>
            )}
          </div>
        )}
      </div>

      {/* Provider Matrix (CONFIGURED != AVAILABLE != ACTIVE) */}
      <div className="pt-1.5 border-t border-narad-border/25 space-y-1.5">
        <div className="text-[10px] font-mono text-narad-textDim uppercase flex items-center justify-between">
          <span>Provider Truth Matrix</span>
          <span className="text-[9px] text-narad-saffron font-semibold">
            {currentProvider.toUpperCase()} ACTIVE
          </span>
        </div>

        <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
          {providers.map((p) => {
            const pInfo = getProviderInfo(p.id);
            const isActive = currentProvider === p.id;

            return (
              <div 
                key={p.id} 
                className={`p-1.5 rounded-md flex items-center justify-between transition-all duration-200 ${
                  isActive
                    ? 'bg-narad-card/90 border border-narad-saffron/50 text-white shadow-sm ring-1 ring-narad-saffron/30'
                    : pInfo.available
                    ? 'bg-narad-card/40 border border-narad-border/30 text-slate-200'
                    : pInfo.configured
                    ? 'bg-amber-500/8 border border-amber-500/25 text-amber-300'
                    : 'bg-narad-card/20 border border-narad-border/15 text-slate-400 opacity-60'
                }`}
                title={`${p.name} — Configured: ${pInfo.configured ? 'YES' : 'NO'} | Available: ${pInfo.available ? 'YES' : 'NO'} | Active: ${isActive ? 'YES' : 'NO'}`}
              >
                <div className="flex items-center gap-1 truncate max-w-[80px]">
                  {isActive && <span className="w-1.5 h-1.5 rounded-full bg-narad-saffron animate-ping flex-shrink-0" />}
                  <span className="truncate">{p.label}</span>
                </div>

                <div className="flex-shrink-0">
                  {isActive ? (
                    <span className="text-[8px] px-1 py-0.5 rounded bg-narad-saffron/20 text-narad-gold font-bold">ACT</span>
                  ) : pInfo.available ? (
                    <span className="text-[8px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-400 font-semibold">ON</span>
                  ) : pInfo.configured ? (
                    <span className="text-[8px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-300 font-semibold">STB</span>
                  ) : (
                    <span className="text-[8px] px-1 py-0.5 rounded bg-slate-500/15 text-slate-400 flex items-center gap-0.5" title="Not configured">
                      <Lock size={7} />
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
