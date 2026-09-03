import React from 'react';
import { Cpu, Lock, CheckCircle2, AlertCircle } from 'lucide-react';

export default function ProviderInfo({ 
  activeProvider = 'gemini', 
  activeModel = 'gemini-2.5-flash',
  isConfigured = false,
  lastTelemetry = null
}) {
  const isGemini = activeProvider === 'gemini';
  const effectiveModel = lastTelemetry?.model || activeModel || 'gemini-2.5-flash';
  const isKeyInvalid = lastTelemetry?.status === 'api_error';

  const futureSlots = [
    { name: 'OpenRouter', status: 'Slot 2 // Reserved' },
    { name: 'Groq LPU', status: 'Slot 3 // Reserved' },
    { name: 'Claude 3.5', status: 'Slot 4 // Reserved' },
    { name: 'OpenAI GPT', status: 'Slot 5 // Reserved' },
  ];

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono tracking-wider text-narad-textDim uppercase flex items-center gap-1.5">
          <Cpu size={12} className="text-narad-cyan" />
          Model Router
        </span>
        <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded border ${
          isKeyInvalid
            ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
            : isConfigured
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
        }`}>
          {isKeyInvalid 
            ? 'KEY INVALID' 
            : isConfigured 
            ? 'GEMINI READY' 
            : 'KEY REQUIRED'}
        </span>
      </div>

      {/* Active Model Card */}
      <div className="bg-narad-bg/70 p-2.5 rounded-lg border border-narad-border/50 space-y-1">
        <div className="flex items-center justify-between text-xs font-mono font-semibold text-white">
          <span className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${isKeyInvalid ? 'bg-rose-400' : 'bg-narad-cyan'} animate-pulse`} />
            <span>{isGemini ? 'Google Gemini' : activeProvider.toUpperCase()}</span>
          </span>
          <span className="text-[10px] text-narad-cyan font-mono">{effectiveModel}</span>
        </div>
        <div className="text-[10px] font-sans text-narad-textDim leading-normal">
          {isKeyInvalid
            ? 'Google Gemini rejected the API key (HTTP 400). Replace with a valid key in backend/.env.'
            : isConfigured 
            ? 'Model router is connected to live Gemini AI engine.' 
            : 'Set GEMINI_API_KEY in backend/.env to activate live responses.'}
        </div>
      </div>

      {/* Provider Connector Pipeline Slots */}
      <div className="pt-1.5 border-t border-narad-border/30 space-y-1.5">
        <div className="text-[10px] font-mono text-narad-textDim uppercase flex items-center justify-between">
          <span>Connector Pipeline</span>
          <span className="text-[9px] text-narad-cyan">Primary: Gemini</span>
        </div>

        <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
          <div className="p-1.5 rounded bg-narad-card/70 border border-narad-cyan/30 flex items-center justify-between">
            <span className="text-white truncate max-w-[85px]">Gemini (Active)</span>
            <CheckCircle2 size={10} className="text-emerald-400 flex-shrink-0" />
          </div>

          {futureSlots.map((c, idx) => (
            <div 
              key={idx} 
              className="p-1.5 rounded bg-narad-card/40 border border-narad-border/30 flex items-center justify-between opacity-75"
              title={`${c.name} connector is reserved for future expansion.`}
            >
              <span className="text-slate-400 truncate max-w-[85px]">{c.name}</span>
              <Lock size={10} className="text-narad-textDim flex-shrink-0" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
