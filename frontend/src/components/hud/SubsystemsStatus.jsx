import React, { useState, useEffect } from 'react';
import { Layers, Mic, Cpu, Volume2, Sparkles } from 'lucide-react';
import { vaaniService } from '../../services/voice';
import { naradApi } from '../../services/api';

export default function SubsystemsStatus({
  isVoiceMode = false,
  voiceState = 'IDLE',
  agentTelemetry = { state: 'IDLE', current_action: null, dry_run: false },
  lastTelemetry = null,
  runtimeTruth = null
}) {
  const isMediaSupported = vaaniService.isMediaRecorderSupported();
  const [ttsStatus, setTtsStatus] = useState(vaaniService.getTTSStatus());
  const [sttStatus, setSttStatus] = useState(vaaniService.getSTTStatus());
  const [ttsEngines, setTtsEngines] = useState(vaaniService.getTTSEngines());
  const [localAIStatus, setLocalAIStatus] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      await vaaniService.refreshAllStatuses();
      const localAi = await naradApi.getLocalAIStatus();
      if (mounted) {
        setTtsStatus(vaaniService.getTTSStatus());
        setSttStatus(vaaniService.getSTTStatus());
        setTtsEngines(vaaniService.getTTSEngines());
        if (localAi) setLocalAIStatus(localAi);
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    const unsub = vaaniService.onTelemetry((t) => {
      if (mounted) {
        if (t.stt_status) setSttStatus(t.stt_status);
        if (t.tts_status) setTtsStatus(t.tts_status);
        if (t.tts_engines) setTtsEngines(t.tts_engines);
      }
    });

    return () => {
      mounted = false;
      clearInterval(interval);
      unsub();
    };
  }, []);

  const rawSubs = runtimeTruth?.subsystems || {};
  const getSubStatus = (key, fallback = 'ONLINE') => rawSubs[key] || fallback;

  const subsystems = [
    { name: 'NARAD Core', role: 'Conversational Coordinator', status: getSubStatus('core', 'ONLINE'), active: getSubStatus('core') === 'ONLINE', color: 'text-narad-saffron' },
    { name: 'Task Engine', role: 'Multi-Step Execution', status: getSubStatus('task_engine', 'ONLINE'), active: getSubStatus('task_engine') === 'ONLINE', color: 'text-narad-cyan' },
    { name: 'Trinetra', role: 'Screen Vision & Feedback', status: getSubStatus('trinetra', 'ONLINE'), active: getSubStatus('trinetra') === 'ONLINE', color: 'text-cyan-400' },
    { name: 'Manthan', role: 'Planning & Observation', status: getSubStatus('manthan', 'ONLINE'), active: getSubStatus('manthan') === 'ONLINE', color: 'text-amber-400' },
    { name: 'Kriya', role: 'Action & Computer Tools', status: getSubStatus('kriya', 'ONLINE'), active: getSubStatus('kriya') === 'ONLINE', color: 'text-amber-400' },
    { name: 'Smriti', role: 'Persistent Memory', status: getSubStatus('smriti', 'ONLINE'), active: getSubStatus('smriti') === 'ONLINE', color: 'text-emerald-400' },
    { name: 'Knowledge', role: 'Document Retrieval', status: getSubStatus('knowledge_base', 'ONLINE'), active: getSubStatus('knowledge_base') === 'ONLINE', color: 'text-emerald-400' },
    { name: 'Vāṇī', role: 'Two-Way Voice Stack', status: getSubStatus('vani', 'ONLINE'), active: getSubStatus('vani') === 'ONLINE', color: 'text-narad-cyan' },
    { name: 'Model Router', role: 'Dynamic Capability Routing', status: getSubStatus('model_router', 'ONLINE'), active: getSubStatus('model_router') === 'ONLINE', color: 'text-narad-gold' },
    { name: 'Computer Agent', role: 'macOS Automation', status: getSubStatus('computer_agent', 'ONLINE'), active: getSubStatus('computer_agent') === 'ONLINE', color: 'text-blue-400' },
    { name: 'STT', role: 'Speech to Text (Whisper)', status: getSubStatus('stt', 'ONLINE'), active: getSubStatus('stt') === 'ONLINE', color: 'text-cyan-300' },
    { name: 'TTS', role: 'Voice Synthesis Engine', status: getSubStatus('tts', 'ONLINE'), active: getSubStatus('tts') === 'ONLINE', color: 'text-pink-400' },
    { name: 'Ollama', role: 'Local Fast Inference', status: getSubStatus('ollama', 'UNAVAILABLE'), active: getSubStatus('ollama') === 'ONLINE', color: 'text-amber-300' },
    { name: 'Vision', role: 'Multimodal Screen Reasoning', status: getSubStatus('vision', 'ONLINE'), active: getSubStatus('vision') === 'ONLINE', color: 'text-purple-400' },
  ];

  const agentState = agentTelemetry.state || 'IDLE';

  const chatterbox = ttsEngines?.chatterbox || ttsStatus?.engines?.chatterbox;
  const indicvoice = ttsEngines?.indicvoice || ttsStatus?.engines?.indicvoice;

  // Real Latency telemetry from last interaction
  const sttLatency = lastTelemetry?.stt_latency;
  const llmLatency = lastTelemetry?.llm_latency;
  const ttsLatency = lastTelemetry?.tts_latency;
  const totalLatency = lastTelemetry?.total_latency;
  const detectedLang = lastTelemetry?.detected_language;
  const activeDevice = lastTelemetry?.tts_device || lastTelemetry?.device || ttsStatus?.device || 'MPS';

  return (
    <div className="hud-panel rounded-xl p-3.5 space-y-2.5 shadow-hud-subtle">
      <div className="flex items-center justify-between">
        <span className="hud-section-title flex items-center gap-1.5">
          <Layers size={12} className="text-narad-saffron" />
          Trimurti Subsystems
        </span>
        <span className="text-[9px] font-mono text-narad-gold font-bold tracking-wider">
          {subsystems.filter(s => s.active).length} ONLINE
        </span>
      </div>

      {/* Compact subsystem list */}
      <div className="space-y-0.5 text-[10px] font-mono">
        {subsystems.map((sub, idx) => (
          <div 
            key={idx}
            className="flex items-center justify-between py-1 px-1.5 rounded-md hover:bg-narad-card/20 transition-colors"
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={`w-1.5 h-1.5 rounded-full ${sub.active ? 'bg-emerald-400' : 'bg-slate-600'} flex-shrink-0`} />
              <span className={`font-semibold ${sub.color}`}>{sub.name}</span>
              <span className="text-narad-textDim text-[9px] hidden sm:inline truncate">— {sub.role}</span>
            </div>
            <span className="text-[8px] px-1 py-0.5 rounded bg-narad-card/50 border border-narad-border/20 text-narad-textDim flex-shrink-0">
              {sub.status}
            </span>
          </div>
        ))}
      </div>

      {/* Computer Agent State */}
      <div className="pt-2 border-t border-narad-border/30 space-y-1.5 font-mono text-[10px]">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-narad-saffron font-semibold tracking-wider">
            <Cpu size={11} className={agentState !== 'IDLE' ? 'animate-spin' : ''} />
            COMPUTER AGENT
          </span>
          <span className={`text-[9px] px-1.5 py-0.5 rounded-md border font-bold ${
            agentState === 'EXECUTING' || agentState === 'OBSERVING'
              ? 'bg-amber-500/15 text-amber-300 border-amber-500/35 animate-pulse'
              : agentState === 'WAITING_FOR_PERMISSION'
              ? 'bg-rose-500/15 text-rose-300 border-rose-500/35 animate-pulse'
              : 'bg-narad-card text-emerald-400 border-emerald-500/25'
          }`}>
            {agentState}
          </span>
        </div>

        {agentTelemetry.current_action && (
          <div className="p-1.5 rounded-md bg-zinc-900/50 border border-zinc-800/80 text-[9px] text-zinc-300 truncate">
            <span className="text-zinc-500">→ </span>{agentTelemetry.current_action}
          </div>
        )}
      </div>

      {/* Vāṇī Voice Telemetry (Section 10 & 3 Spec) */}
      <div className="pt-2 border-t border-narad-border/30 space-y-2 font-mono text-[10px]">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-narad-cyan font-semibold tracking-wider">
            <Mic size={11} className={voiceState === 'LISTENING' ? 'animate-bounce text-rose-400' : ''} />
            VĀṆĪ VOICE SYSTEM
          </span>
          <div className="flex items-center gap-1">
            <span className="text-[8px] px-1.5 py-0.5 rounded bg-narad-card/60 text-cyan-300 font-bold uppercase border border-cyan-500/30">
              {activeDevice}
            </span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded-md border font-semibold ${
              isVoiceMode 
                ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40 shadow-[0_0_8px_rgba(0,240,255,0.25)]' 
                : 'bg-narad-card text-narad-textDim border-narad-border/25'
            }`}>
              {isVoiceMode ? 'VOICE ON' : 'VOICE OFF'}
            </span>
          </div>
        </div>

        {/* 1. INPUT: Local Whisper */}
        <div className="p-2 rounded-md bg-narad-card/40 border border-narad-border/30 space-y-1">
          <div className="flex items-center justify-between text-[9px]">
            <span className="text-narad-textDim font-bold">INPUT:</span>
            <span className="font-bold text-emerald-400 tracking-wider">LOCAL WHISPER</span>
          </div>
          <div className="flex items-center justify-between text-[9px]">
            <span className="text-narad-textDim">STATUS:</span>
            <span className={`font-semibold ${
              voiceState === 'LISTENING'
                ? 'text-rose-400 animate-pulse'
                : voiceState === 'PROCESSING'
                ? 'text-amber-300 animate-pulse'
                : sttStatus?.ready
                ? 'text-emerald-400'
                : 'text-slate-400'
            }`}>
              {voiceState === 'LISTENING' ? 'LISTENING' : voiceState === 'PROCESSING' ? 'PROCESSING' : sttStatus?.ready ? 'READY' : 'STANDBY'}
            </span>
          </div>
          <div className="flex items-center justify-between text-[9px]">
            <span className="text-narad-textDim">MIC HARDWARE:</span>
            <span className={isMediaSupported ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
              {isMediaSupported ? 'READY' : 'UNAVAILABLE'}
            </span>
          </div>
        </div>

        {/* 2. OUTPUT: TTS Engines (Chatterbox & IndicVoice) */}
        <div className="p-2 rounded-md bg-narad-card/40 border border-narad-border/30 space-y-1.5">
          <div className="flex items-center justify-between text-[9px] pb-1 border-b border-narad-border/20">
            <span className="text-narad-textDim font-bold">OUTPUT:</span>
            <span className="font-bold text-narad-saffron tracking-wider">
              {lastTelemetry?.tts_engine ? lastTelemetry.tts_engine.toUpperCase() : (ttsStatus?.provider ? ttsStatus.provider.toUpperCase() : 'CHATTERBOX')}
            </span>
          </div>

          {/* Chatterbox Engine */}
          <div className="space-y-0.5 text-[8.5px]">
            <div className="flex justify-between items-center">
              <span className="text-zinc-300 font-semibold">CHATTERBOX</span>
              <span className="text-emerald-400 font-bold">
                {chatterbox?.model_loaded || ttsStatus?.model_loaded ? 'LOADED' : 'READY'}
              </span>
            </div>
            <div className="flex justify-between text-narad-textDim">
              <span>DEVICE: <strong className="text-cyan-300">{chatterbox?.device || ttsStatus?.device || 'MPS'}</strong></span>
              <span>STATUS: <strong className="text-emerald-400">READY</strong></span>
            </div>
          </div>

          {/* IndicVoice Engine */}
          <div className="space-y-0.5 text-[8.5px] pt-1 border-t border-narad-border/20">
            <div className="flex justify-between items-center">
              <span className="text-zinc-300 font-semibold">INDICVOICE (HINDI)</span>
              <span className="text-emerald-400 font-bold">
                {indicvoice?.model_loaded ? 'LOADED' : 'READY'}
              </span>
            </div>
            <div className="flex justify-between text-narad-textDim">
              <span>DEVICE: <strong className="text-cyan-300">{indicvoice?.device || 'CPU'}</strong></span>
              <span>STATUS: <strong className="text-emerald-400">READY</strong></span>
            </div>
          </div>
        </div>

        {/* 3. Real Latency Telemetry (No fake values) */}
        {totalLatency !== undefined && totalLatency !== null && (
          <div className="p-2 rounded-md bg-black/40 border border-cyan-500/30 space-y-1 text-[9px]">
            <div className="flex items-center justify-between text-narad-cyan font-bold border-b border-narad-border/20 pb-0.5">
              <span>REAL LATENCY</span>
              <span className="text-narad-gold font-mono">{detectedLang ? detectedLang.toUpperCase() : 'AUTO'}</span>
            </div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[8.5px]">
              <div className="flex justify-between text-narad-textDim">
                <span>STT:</span>
                <span className="text-white font-mono">{sttLatency !== undefined ? `${sttLatency}s` : '—'}</span>
              </div>
              <div className="flex justify-between text-narad-textDim">
                <span>LLM:</span>
                <span className="text-white font-mono">{llmLatency !== undefined ? `${llmLatency}s` : '—'}</span>
              </div>
              <div className="flex justify-between text-narad-textDim">
                <span>TTS:</span>
                <span className="text-white font-mono">{ttsLatency !== undefined ? `${ttsLatency}s` : '—'}</span>
              </div>
              <div className="flex justify-between text-narad-textDim font-bold">
                <span className="text-narad-cyan">TOTAL:</span>
                <span className="text-narad-cyan font-mono">{totalLatency !== undefined ? `${totalLatency}s` : '—'}</span>
              </div>
            </div>
          </div>
        )}

        {/* 4. Local AI Telemetry (Hugging Face Layer) */}
        <div className="p-2 rounded-md bg-black/40 border border-purple-500/30 space-y-1.5 text-[9px]">
          <div className="flex items-center justify-between text-purple-300 font-bold border-b border-purple-500/20 pb-0.5">
            <span className="flex items-center gap-1">
              <Cpu size={11} className="text-purple-400" />
              LOCAL AI (HUGGING FACE)
            </span>
            <span className={`font-mono text-[8px] px-1 py-0.2 rounded ${localAIStatus?.llm?.is_loaded ? 'bg-emerald-500/20 text-emerald-400' : 'bg-purple-500/20 text-purple-300'}`}>
              {localAIStatus?.llm?.status || 'STANDBY'}
            </span>
          </div>
          <div className="space-y-0.5 text-[8.5px]">
            <div className="flex justify-between text-narad-textDim">
              <span>MODEL:</span>
              <span className="text-zinc-200 font-mono truncate max-w-[140px]">
                {localAIStatus?.llm?.model?.split('/')[1] || 'SmolLM2-135M'}
              </span>
            </div>
            <div className="flex justify-between text-narad-textDim">
              <span>DEVICE:</span>
              <span className="text-cyan-300 font-mono">{localAIStatus?.llm?.device || 'CPU'}</span>
            </div>
            <div className="flex justify-between text-narad-textDim">
              <span>CACHE:</span>
              <span className="text-emerald-400 font-mono">
                {localAIStatus?.llm?.cache_hit ? 'HIT' : 'READY'}
              </span>
            </div>
            {localAIStatus?.llm?.load_time_ms > 0 && (
              <div className="flex justify-between text-narad-textDim">
                <span>LOAD:</span>
                <span className="text-white font-mono">{localAIStatus.llm.load_time_ms} ms</span>
              </div>
            )}
            {localAIStatus?.llm?.last_inference_ms > 0 && (
              <div className="flex justify-between text-narad-textDim">
                <span>INFERENCE:</span>
                <span className="text-purple-300 font-mono">{localAIStatus.llm.last_inference_ms} ms</span>
              </div>
            )}
            <div className="flex justify-between text-narad-textDim pt-0.5 border-t border-purple-500/20">
              <span>EMBEDDINGS:</span>
              <span className="text-cyan-300 font-mono">
                {localAIStatus?.embeddings?.provider_status?.device || 'MPS'} (all-MiniLM)
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

