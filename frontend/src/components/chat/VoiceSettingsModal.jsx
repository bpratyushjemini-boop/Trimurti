import React, { useState, useEffect } from 'react';
import { X, Volume2, Mic, Settings2, Play, Check, Cpu, Sparkles, Loader2, Square } from 'lucide-react';
import { api } from '../../services/api';
import { vaaniService } from '../../services/voice';

export default function VoiceSettingsModal({ isOpen, onClose }) {
  const [settings, setSettings] = useState(vaaniService.getSettings());
  const [sttStatus, setSttStatus] = useState(vaaniService.getSTTStatus());
  const [ttsStatus, setTtsStatus] = useState(vaaniService.getTTSStatus());
  const [ttsEngines, setTtsEngines] = useState(vaaniService.getTTSEngines());
  const [playingKey, setPlayingKey] = useState(null);
  const [testError, setTestError] = useState(null);

  useEffect(() => {
    if (!isOpen) return;

    const loadStatuses = async () => {
      await vaaniService.refreshAllStatuses();
      setSettings(vaaniService.getSettings());
      setSttStatus(vaaniService.getSTTStatus());
      setTtsStatus(vaaniService.getTTSStatus());
      setTtsEngines(vaaniService.getTTSEngines());
    };

    loadStatuses();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleToggle = (key) => {
    const updated = { ...settings, [key]: !settings[key] };
    setSettings(updated);
    vaaniService.saveSettings(updated);
  };

  const handleChange = (key, value) => {
    const updated = { ...settings, [key]: value };
    setSettings(updated);
    vaaniService.saveSettings(updated);
  };

  const handleTestDiagnostic = async (sampleKey) => {
    if (playingKey === sampleKey) {
      vaaniService.stopSpeaking();
      setPlayingKey(null);
      return;
    }

    vaaniService.stopSpeaking();
    setPlayingKey(sampleKey);
    setTestError(null);

    try {
      const audioBlob = await api.testTTS(sampleKey);
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      
      audio.volume = settings.voiceVolume ?? 1.0;

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        setPlayingKey(null);
      };

      audio.onerror = (e) => {
        console.warn('[Diagnostic] Audio playback error:', e);
        URL.revokeObjectURL(audioUrl);
        setPlayingKey(null);
        setTestError('Audio playback failed in browser');
      };

      await audio.play();
    } catch (err) {
      console.error('[Diagnostic] Test failed:', err);
      setTestError(`Diagnostic error: ${err.message || 'Synthesis failed'}`);
      setPlayingKey(null);
    }
  };

  const chatterbox = ttsEngines?.chatterbox || ttsStatus?.engines?.chatterbox;
  const indicvoice = ttsEngines?.indicvoice || ttsStatus?.engines?.indicvoice;

  const diagnosticSamples = [
    { key: 'english', label: 'English Greeting', lang: 'EN', engine: 'Chatterbox', sample: 'Hello, I am NARAD. How can I help you?' },
    { key: 'hindi', label: 'Hindi Greeting', lang: 'HI', engine: 'IndicVoice', sample: 'नमस्ते, मैं नारद हूँ। मैं आपकी कैसे सहायता कर सकता हूँ?' },
    { key: 'hinglish', label: 'Hinglish Greeting', lang: 'HINGLISH', engine: 'Chatterbox', sample: 'Namaste, main NARAD hoon. Aaj hum kya kar rahe hain?' },
    { key: 'voice_command', label: 'Voice Command', lang: 'EN', engine: 'Chatterbox', sample: 'Opening Google Chrome for you now, Operator.' },
    { key: 'voice_tool_command', label: 'Voice Tool Action', lang: 'EN', engine: 'Chatterbox', sample: 'Launching Apple Music and cueing Back in Black by AC/DC.' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-lg bg-narad-surface border border-narad-border rounded-xl shadow-2xl p-5 space-y-4 font-mono text-xs text-narad-text max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-narad-border/60">
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-narad-cyan" />
            <span className="text-sm font-bold text-white tracking-wider">VĀṆĪ VOICE ARCHITECTURE</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-narad-textDim hover:text-white hover:bg-narad-card transition-colors cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Status Alert if error */}
        {testError && (
          <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] font-sans">
            {testError}
          </div>
        )}

        {/* Engine Hardware Status Cards */}
        <div className="space-y-2">
          <div className="text-[11px] font-bold text-narad-cyan tracking-wider uppercase">Local Voice Engines</div>
          
          <div className="grid grid-cols-2 gap-2">
            {/* Chatterbox Multilingual */}
            <div className="p-2.5 rounded-lg bg-narad-card/50 border border-narad-border/40 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-white text-[10.5px]">CHATTERBOX</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-bold">
                  {chatterbox?.model_loaded || ttsStatus?.model_loaded ? 'LOADED' : 'READY'}
                </span>
              </div>
              <div className="text-[9px] text-narad-textDim">Resemble AI Multilingual</div>
              <div className="flex justify-between text-[9px] pt-1 border-t border-narad-border/20">
                <span>DEVICE:</span>
                <span className="text-cyan-300 font-bold">{chatterbox?.device || ttsStatus?.device || 'MPS'}</span>
              </div>
              <div className="flex justify-between text-[9px]">
                <span>LANGUAGES:</span>
                <span className="text-narad-gold">EN, HI, HINGLISH</span>
              </div>
            </div>

            {/* IndicVoice Neural TTS */}
            <div className="p-2.5 rounded-lg bg-narad-card/50 border border-narad-border/40 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-white text-[10.5px]">INDICVOICE</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-bold">
                  {indicvoice?.model_loaded ? 'LOADED' : 'READY'}
                </span>
              </div>
              <div className="text-[9px] text-narad-textDim">Kokoro-82M Indic G2P</div>
              <div className="flex justify-between text-[9px] pt-1 border-t border-narad-border/20">
                <span>DEVICE:</span>
                <span className="text-cyan-300 font-bold">{indicvoice?.device || 'CPU'}</span>
              </div>
              <div className="flex justify-between text-[9px]">
                <span>LANGUAGES:</span>
                <span className="text-narad-gold">PURE HINDI (HI)</span>
              </div>
            </div>
          </div>

          {/* Local Whisper STT Card */}
          <div className="p-2.5 rounded-lg bg-narad-card/50 border border-narad-border/40 flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="font-bold text-white text-[10.5px] flex items-center gap-1.5">
                <Mic size={12} className="text-emerald-400" />
                <span>LOCAL WHISPER (SPEECH-TO-TEXT)</span>
              </div>
              <div className="text-[9px] text-narad-textDim">faster-whisper • local CPU int8 • zero external API</div>
            </div>
            <span className="text-[9px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-bold">
              {sttStatus?.ready ? 'READY' : 'STANDBY'}
            </span>
          </div>
        </div>

        {/* Diagnostic Voice Tests */}
        <div className="space-y-2 pt-1 border-t border-narad-border/40">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-narad-saffron tracking-wider uppercase">Voice Diagnostics</span>
            <span className="text-[9px] text-narad-textDim">Click to test synthesis</span>
          </div>

          <div className="space-y-1.5">
            {diagnosticSamples.map((diag) => {
              const isPlaying = playingKey === diag.key;
              return (
                <div
                  key={diag.key}
                  className="flex items-center justify-between p-2 rounded-lg bg-narad-card/30 border border-narad-border/25 hover:border-narad-cyan/40 transition-colors"
                >
                  <div className="min-w-0 pr-2">
                    <div className="flex items-center gap-2 font-semibold text-white">
                      <span>{diag.label}</span>
                      <span className="text-[8px] px-1 py-0.2 rounded bg-narad-card text-narad-gold border border-narad-border/30">
                        {diag.lang}
                      </span>
                      <span className="text-[8px] text-narad-textDim truncate">
                        via {diag.engine}
                      </span>
                    </div>
                    <div className="text-[9px] text-narad-textDim font-sans truncate mt-0.5">
                      "{diag.sample}"
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleTestDiagnostic(diag.key)}
                    className={`px-2.5 py-1 rounded text-[10px] font-bold flex items-center gap-1.5 transition-all cursor-pointer flex-shrink-0 ${
                      isPlaying
                        ? 'bg-amber-500 text-black shadow-[0_0_8px_rgba(245,158,11,0.4)]'
                        : 'bg-narad-card hover:bg-narad-border text-narad-cyan border border-narad-cyan/30'
                    }`}
                  >
                    {isPlaying ? <Square size={10} className="fill-current" /> : <Play size={10} />}
                    <span>{isPlaying ? 'STOP' : 'TEST'}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Setting 1: Voice Mode (Hands-Free) */}
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-narad-card/50 border border-narad-border/40">
          <div>
            <div className="font-semibold text-white flex items-center gap-1.5">
              <Mic size={13} className={settings.voiceMode ? "text-narad-cyan" : "text-narad-textDim"} />
              <span>Voice Mode (Two-Way Hands-Free)</span>
            </div>
            <div className="text-[10px] text-narad-textDim font-sans mt-0.5">
              Automatically transmits microphone recordings to NARAD and reads answers aloud.
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleToggle('voiceMode')}
            className={`w-10 h-5 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
              settings.voiceMode ? 'bg-narad-cyan justify-end' : 'bg-slate-700 justify-start'
            }`}
          >
            <div className={`w-3.5 h-3.5 rounded-full ${settings.voiceMode ? 'bg-narad-bg' : 'bg-slate-400'}`} />
          </button>
        </div>

        {/* Setting 2: Auto-Speak Responses */}
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-narad-card/50 border border-narad-border/40">
          <div>
            <div className="font-semibold text-white flex items-center gap-1.5">
              <Volume2 size={13} className={settings.autoSpeak ? "text-narad-cyan" : "text-narad-textDim"} />
              <span>Auto-Speak Responses</span>
            </div>
            <div className="text-[10px] text-narad-textDim font-sans mt-0.5">
              Read out text responses aloud through the local TTS router.
            </div>
          </div>
          <button
            type="button"
            onClick={() => handleToggle('autoSpeak')}
            className={`w-10 h-5 flex items-center rounded-full p-1 transition-colors cursor-pointer ${
              settings.autoSpeak ? 'bg-narad-cyan justify-end' : 'bg-slate-700 justify-start'
            }`}
          >
            <div className={`w-3.5 h-3.5 rounded-full ${settings.autoSpeak ? 'bg-narad-bg' : 'bg-slate-400'}`} />
          </button>
        </div>

        {/* Setting 3: Volume */}
        <div className="p-2.5 rounded-lg bg-narad-card/50 border border-narad-border/40 space-y-1.5">
          <div className="flex justify-between items-center">
            <span className="font-semibold text-white">Playback Volume</span>
            <span className="text-narad-cyan font-bold">{Math.round(settings.voiceVolume * 100)}%</span>
          </div>
          <input
            type="range"
            min="0.0"
            max="1.0"
            step="0.05"
            value={settings.voiceVolume}
            onChange={(e) => handleChange('voiceVolume', parseFloat(e.target.value))}
            className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-narad-cyan"
          />
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end pt-2 border-t border-narad-border/60">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-1.5 rounded bg-narad-cyan text-narad-bg font-bold hover:bg-narad-blue transition-colors shadow-[0_0_10px_rgba(0,240,255,0.3)] cursor-pointer"
          >
            DONE
          </button>
        </div>
      </div>
    </div>
  );
}
