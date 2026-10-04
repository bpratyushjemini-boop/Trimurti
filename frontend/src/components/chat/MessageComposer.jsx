import React, { useState, useRef, useEffect } from 'react';
import { 
  Send, 
  Paperclip, 
  Mic, 
  Sparkles, 
  Volume2, 
  Radio, 
  AlertCircle, 
  Loader2, 
  Square, 
  Settings2,
  Cpu,
  Wrench,
  XCircle
} from 'lucide-react';
import { api } from '../../services/api';
import { vaaniService } from '../../services/voice';

export default function MessageComposer({
  onSendMessage,
  disabled,
  draftPrompt = '',
  onClearDraftPrompt,
  isVoiceMode = false,
  onToggleVoiceMode,
  interactionState = 'IDLE',
  currentTool = null,
  onCancel = null,
  onOpenVoiceSettings = null,
  isDryRun = false,
  onToggleDryRun = null,
  onEmergencyStop = null,
  agentState = 'IDLE',
  onVoiceInteraction = null,
  onOpenKnowledgeBase = null
}) {
  const [content, setContent] = useState('');
  const [voiceError, setVoiceError] = useState(null);
  const textareaRef = useRef(null);

  const isMediaSupported = vaaniService.isMediaRecorderSupported();

  // When an external starter prompt is provided, populate textarea and focus
  useEffect(() => {
    if (draftPrompt) {
      setContent(draftPrompt);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
      if (onClearDraftPrompt) {
        onClearDraftPrompt();
      }
    }
  }, [draftPrompt, onClearDraftPrompt]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [content]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!content.trim() || disabled) return;
    onSendMessage(content.trim());
    setContent('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Toggle Speech Input (Local Whisper STT via MediaRecorder)
  const handleToggleVoiceInput = async () => {
    setVoiceError(null);

    // 1. Immediate barge-in: stop playback if speaking
    if (interactionState === 'SPEAKING' || vaaniService.isSpeaking) {
      vaaniService.stopSpeaking();
      return;
    }

    // 2. If already listening, stop recording and trigger processing
    if (interactionState === 'LISTENING') {
      try {
        const audioBlob = await vaaniService.stopRecording();
        if (!audioBlob || audioBlob.size < 100) {
          return;
        }

        // Two-way interaction mode if voice mode or onVoiceInteraction is available
        if (onVoiceInteraction && isVoiceMode) {
          await onVoiceInteraction(audioBlob);
        } else {
          // Dictation mode: transcribe via Local Whisper STT and insert into textarea
          setVoiceError('Transcribing speech via Local Whisper...');
          const sttResult = await api.transcribeAudio(audioBlob, 'auto');
          setVoiceError(null);
          if (sttResult?.text) {
            setContent((prev) => {
              const updated = prev.trim() ? `${prev.trim()} ${sttResult.text}` : sttResult.text;
              return updated;
            });
          }
        }
      } catch (err) {
        console.error('[Vāṇī] STT error:', err);
        setVoiceError(`STT Error: ${err.message || 'Transcription failed'}`);
        setTimeout(() => setVoiceError(null), 6000);
      }
      return;
    }

    // 3. If idle, start recording
    const started = await vaaniService.startRecording({
      onError: (err) => {
        const msg = err.name === 'NotAllowedError' || err.message?.includes('denied')
          ? 'Microphone permission denied. Please grant microphone access in browser.'
          : `Microphone error: ${err.message || err.name || 'unreachable'}`;
        setVoiceError(msg);
        setTimeout(() => setVoiceError(null), 6000);
      }
    });

    if (!started && !voiceError) {
      setVoiceError(vaaniService.getLastError() || 'Could not access microphone.');
      setTimeout(() => setVoiceError(null), 5000);
    }
  };

  const handleStopAll = () => {
    vaaniService.halt();
    if (onCancel) {
      onCancel();
    }
  };

  const isBusy = interactionState !== 'IDLE';

  return (
    <div className="p-4 border-t border-narad-border bg-narad-surface/90 backdrop-blur-xl relative z-10">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto space-y-2">
        
        {/* VĀṆĪ INPUT Status & Telemetry Banner */}
        <div className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-narad-card/40 border border-narad-border/30 text-[10px] font-mono select-none">
          <div className="flex items-center gap-2">
            <span className="font-bold text-narad-cyan tracking-wider">VĀṆĪ INPUT</span>
            <span className="text-narad-border/60">•</span>
            <span className="text-narad-textDim">ENGINE:</span>
            <span className="text-emerald-400 font-semibold">LOCAL WHISPER</span>
            <span className="text-narad-border/60">•</span>
            <span className="text-narad-textDim">MIC:</span>
            <span className={`font-semibold ${
              voiceError ? 'text-rose-400' : 'text-emerald-400'
            }`}>
              {voiceError ? 'ERROR' : isMediaSupported ? 'READY' : 'UNAVAILABLE'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-narad-textDim">STATUS:</span>
            <span className={`font-bold px-1.5 py-0.5 rounded border text-[9px] ${
              interactionState === 'LISTENING'
                ? 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse'
                : interactionState === 'PROCESSING' || interactionState === 'THINKING' || interactionState === 'TOOL_EXECUTION'
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
                : interactionState === 'SPEAKING'
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 animate-bounce'
                : voiceError
                ? 'bg-rose-500/20 text-rose-400 border-rose-500/40'
                : 'bg-narad-card text-narad-cyan border-narad-cyan/30'
            }`}>
              {interactionState === 'LISTENING'
                ? 'LISTENING'
                : interactionState === 'PROCESSING' || interactionState === 'THINKING' || interactionState === 'TOOL_EXECUTION'
                ? 'PROCESSING'
                : interactionState === 'SPEAKING'
                ? 'SPEAKING'
                : voiceError
                ? 'ERROR'
                : 'READY'}
            </span>
          </div>
        </div>

        <div className="hud-panel rounded-xl p-3 flex flex-col gap-2.5 relative group focus-within:hud-panel-active transition-all duration-300 shadow-hud-subtle focus-within:shadow-hud-focus">
          
          {/* Turn-Taking State Banner */}
          {isBusy && (
            <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-narad-card/80 border border-narad-cyan/30 text-xs font-mono animate-fadeIn">
              <div className="flex items-center gap-2.5">
                {interactionState === 'LISTENING' && (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
                    <span className="text-rose-400 font-semibold tracking-wider flex items-center gap-1.5">
                      <Radio size={13} className="animate-pulse" />
                      VĀṆĪ // LISTENING...
                    </span>
                  </>
                )}

                {interactionState === 'THINKING' && (
                  <>
                    <Loader2 size={13} className="text-narad-saffron animate-spin" />
                    <span className="text-narad-saffron font-semibold tracking-wider flex items-center gap-1.5">
                      <Cpu size={13} />
                      NARAD // THINKING...
                    </span>
                  </>
                )}

                {interactionState === 'TOOL_EXECUTION' && (
                  <>
                    <Loader2 size={13} className="text-narad-cyan animate-spin" />
                    <span className="text-narad-cyan font-semibold tracking-wider flex items-center gap-1.5">
                      <Wrench size={13} className="animate-pulse" />
                      KRĪYA // TOOL{currentTool ? `: ${currentTool}` : ''}...
                    </span>
                  </>
                )}

                {interactionState === 'GENERATING' && (
                  <>
                    <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                    <span className="text-cyan-300 font-semibold tracking-wider flex items-center gap-1.5">
                      <Sparkles size={13} className="animate-spin" />
                      GENERATING...
                    </span>
                  </>
                )}

                {interactionState === 'SPEAKING' && (
                  <>
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="text-emerald-400 font-semibold tracking-wider flex items-center gap-1.5">
                      <Volume2 size={13} className="animate-bounce" />
                      VĀṆĪ // SPEAKING...
                    </span>
                  </>
                )}

                {interactionState === 'CANCELLED' && (
                  <>
                    <XCircle size={13} className="text-amber-400" />
                    <span className="text-amber-400 font-semibold tracking-wider">
                      CANCELLED // READY
                    </span>
                  </>
                )}

                {interactionState === 'ERROR' && (
                  <>
                    <AlertCircle size={13} className="text-rose-400" />
                    <span className="text-rose-400 font-semibold tracking-wider">
                      ERROR // RESETTING
                    </span>
                  </>
                )}
              </div>

              {/* STOP Button */}
              <button
                type="button"
                onClick={handleStopAll}
                className="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 hover:text-white border border-rose-500/40 text-[10px] font-mono font-bold flex items-center gap-1.5 transition-all duration-200 cursor-pointer shadow-[0_0_8px_rgba(244,63,94,0.2)]"
                title="Stop all operations"
              >
                <Square size={10} className="fill-rose-400 text-rose-400" />
                <span>STOP</span>
              </button>
            </div>
          )}

          {/* Voice error */}
          {voiceError && (
            <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-sans animate-fadeIn">
              <AlertCircle size={14} className="flex-shrink-0" />
              <span>{voiceError}</span>
            </div>
          )}

          {/* Main Input Textarea */}
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={
              isVoiceMode
                ? "🎙️ Voice Mode — speak or type... (Enter to transmit)"
                : "Instruct NARAD — request analysis or assign directive... (Enter to transmit)"
            }
            rows={2}
            className="w-full bg-transparent resize-none text-sm text-narad-text placeholder:text-narad-textDim focus:outline-none px-2 py-1 font-sans max-h-48 overflow-y-auto leading-relaxed"
          />

          {/* Action Toolbar */}
          <div className="flex items-center justify-between pt-2 border-t border-narad-border/30 px-1 select-none">
            <div className="flex items-center gap-1.5">
              {/* Attachment / Knowledge Ingestion */}
              <button
                type="button"
                onClick={onOpenKnowledgeBase}
                className="p-1.5 rounded-md text-narad-textDim hover:text-narad-cyan hover:bg-narad-card transition-colors cursor-pointer"
                title="Knowledge Base Vault & Document Ingestion"
              >
                <Paperclip size={14} />
              </button>

              {/* Mic / PTT / Interrupt */}
              <button
                type="button"
                onClick={handleToggleVoiceInput}
                className={`p-1.5 rounded-md transition-all duration-200 flex items-center gap-1.5 ${
                  interactionState === 'SPEAKING'
                    ? 'bg-amber-500/25 text-amber-300 border border-amber-500/50 shadow-[0_0_10px_rgba(245,158,11,0.3)] animate-pulse cursor-pointer'
                    : interactionState === 'LISTENING'
                    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40 shadow-[0_0_10px_rgba(244,63,94,0.3)] animate-pulse cursor-pointer'
                    : interactionState === 'PROCESSING' || interactionState === 'THINKING' || interactionState === 'TOOL_EXECUTION'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 cursor-wait'
                    : 'text-narad-textDim hover:text-narad-cyan hover:bg-narad-card cursor-pointer'
                }`}
                title={
                  interactionState === 'SPEAKING'
                    ? 'Speaking — Click to Interrupt (Barge-in)'
                    : interactionState === 'LISTENING'
                    ? 'Listening... Click to finish and transmit directive'
                    : interactionState === 'PROCESSING'
                    ? 'Processing voice directive...'
                    : 'Voice Input (Click to speak)'
                }
              >
                {interactionState === 'SPEAKING' ? (
                  <Square size={12} className="fill-amber-400 text-amber-400" />
                ) : interactionState === 'PROCESSING' || interactionState === 'THINKING' || interactionState === 'TOOL_EXECUTION' ? (
                  <Loader2 size={13} className="animate-spin text-cyan-400" />
                ) : (
                  <Mic size={14} className={interactionState === 'LISTENING' ? 'animate-bounce text-rose-400' : ''} />
                )}
                {interactionState === 'LISTENING' && (
                  <span className="text-[9px] font-mono font-semibold tracking-wider text-rose-400">REC</span>
                )}
                {interactionState === 'SPEAKING' && (
                  <span className="text-[9px] font-mono font-bold tracking-wider text-amber-300">INTERRUPT</span>
                )}
              </button>

              {/* Voice Mode Toggle */}
              {onToggleVoiceMode && (
                <button
                  type="button"
                  onClick={onToggleVoiceMode}
                  className={`px-2 py-0.5 rounded-md text-[10px] font-mono border transition-all duration-200 flex items-center gap-1.5 ${
                    isVoiceMode
                      ? 'bg-cyan-500/15 text-narad-cyan border-cyan-500/40 shadow-glow-cyan'
                      : 'bg-narad-card/40 text-narad-textDim border-narad-border/40 hover:text-slate-300'
                  }`}
                  title={isVoiceMode ? 'Voice Mode Active' : 'Enable Voice Mode'}
                >
                  <Volume2 size={10} className={isVoiceMode ? 'text-narad-cyan animate-pulse' : ''} />
                  <span>VOICE: {isVoiceMode ? 'ON' : 'OFF'}</span>
                </button>
              )}

              {/* Dry Run Toggle */}
              {onToggleDryRun && (
                <button
                  type="button"
                  onClick={onToggleDryRun}
                  className={`px-2 py-0.5 rounded-md text-[10px] font-mono border transition-all duration-200 flex items-center gap-1.5 ${
                    isDryRun
                      ? 'bg-narad-saffron/20 text-narad-saffron border-narad-saffron/50 shadow-glow-saffron font-bold'
                      : 'bg-narad-card/40 text-narad-textDim border-narad-border/40 hover:text-slate-300'
                  }`}
                  title={isDryRun ? 'Dry Run Active' : 'Enable Dry Run'}
                >
                  <span>DRY RUN: {isDryRun ? 'ON' : 'OFF'}</span>
                </button>
              )}

              {/* Voice Settings */}
              {onOpenVoiceSettings && (
                <button
                  type="button"
                  onClick={onOpenVoiceSettings}
                  className="p-1.5 rounded-md text-narad-textDim hover:text-white hover:bg-narad-card transition-colors"
                  title="Voice Settings"
                >
                  <Settings2 size={13} />
                </button>
              )}

              {/* Emergency Stop */}
              {onEmergencyStop && agentState !== 'IDLE' && agentState !== 'COMPLETED' && agentState !== 'CANCELLED' && (
                <button
                  type="button"
                  onClick={onEmergencyStop}
                  className="px-2.5 py-0.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-mono text-[10px] font-bold flex items-center gap-1.5 shadow-[0_0_12px_rgba(239,68,68,0.4)] animate-pulse cursor-pointer"
                  title="EMERGENCY STOP"
                >
                  <Square size={9} className="fill-white" />
                  <span>STOP AGENT</span>
                </button>
              )}

              <div className="h-3 w-[1px] bg-narad-border/40 mx-1" />

              <span className="text-[10px] font-mono text-narad-textDim flex items-center gap-1.5">
                <Sparkles size={10} className="text-narad-saffron" />
                <span className="hidden sm:inline">TRIMURTI AI</span>
              </span>
            </div>

            {/* Right: Send */}
            <div className="flex items-center gap-2">
              <span className="hidden sm:inline text-[10px] font-mono text-narad-textDim">
                ↵ SEND • ⇧↵ NEWLINE
              </span>

              <button
                type="submit"
                disabled={!content.trim() || disabled}
                className={`px-4 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center gap-2 transition-all duration-200 ${
                  content.trim() && !disabled
                    ? 'bg-gradient-to-r from-narad-saffron to-narad-cyan text-narad-bg hover:shadow-[0_0_20px_rgba(0,240,255,0.4)] cursor-pointer active:scale-95 animate-gradient-shift'
                    : 'bg-narad-card text-narad-textDim border border-narad-border/50 cursor-not-allowed'
                }`}
              >
                <span>TRANSMIT</span>
                <Send size={12} className={content.trim() && !disabled ? 'translate-x-0.5' : ''} />
              </button>
            </div>
          </div>
        </div>

        {/* Footer Status */}
        <div className="flex justify-between items-center px-2 pt-1 text-[10px] font-mono text-narad-textDim select-none">
          <span className="flex items-center gap-1.5" title="NARAD — Neural Assistant for Rizz & Absolute Destruction">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>NARAD V7 // नारद</span>
          </span>
          <span className="text-narad-textDim/60">TRIMURTI AI • PERSONAL INTELLIGENCE</span>
        </div>
      </form>
    </div>
  );
}
