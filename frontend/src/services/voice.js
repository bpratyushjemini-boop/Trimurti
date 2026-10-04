/**
 * VĀṆĪ (वाणी) Voice Service for NARAD V7.
 * Real two-way local voice interaction:
 * MIC -> Local Whisper STT -> NARAD Core (Tools / Fast Path) -> TTS Router (Chatterbox / IndicVoice) -> Playback.
 * 
 * Hardware-honest Apple Silicon (MPS / CPU) telemetry.
 * In-memory zero-leak audio handling.
 * Safe barge-in and immediate audio interruption.
 */

import { api } from './api';

const SETTINGS_STORAGE_KEY = 'narad_vaani_settings';

const DEFAULT_SETTINGS = {
  voiceMode: false,
  autoSpeak: true,
  speechRate: 1.0,
  voiceVolume: 1.0,
  selectedVoice: '',
  sttProvider: 'local_whisper', // 'local_whisper' | 'browser'
  ttsRouterPolicy: 'auto'        // 'auto' | 'chatterbox_only' | 'indicvoice_only'
};

// Check browser capability support
const SpeechRecognitionAPI =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition || null
    : null;

const SpeechSynthesisAPI =
  typeof window !== 'undefined' && 'speechSynthesis' in window
    ? window.speechSynthesis
    : null;

class VaaniVoiceService {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.mediaStream = null;
    this.isListening = false;
    this.isProcessing = false;
    this.isSpeaking = false;
    this.speechSynthesis = SpeechSynthesisAPI;
    this.currentUtterance = null;
    this.audioElement = null;
    this.currentAudioUrl = null;

    // Real status telemetry
    this.sttStatus = null;
    this.ttsStatus = null;
    this.ttsEngines = {};
    this.lastTelemetry = null;
    this.lastError = null;

    this.onStateChangeCallbacks = new Set();
    this.onTelemetryCallbacks = new Set();
    
    // Unified turn-taking states:
    // 'IDLE' | 'LISTENING' | 'PROCESSING' | 'SPEAKING' | 'ERROR' | 'CANCELLED'
    this.state = 'IDLE';

    // Load persisted voice settings
    this.settings = this._loadSettings();

    this.refreshAllStatuses();
  }

  async refreshAllStatuses() {
    try {
      const [stt, tts, engines] = await Promise.allSettled([
        api.getSTTStatus(),
        api.getTTSStatus(),
        api.getTTSEngines()
      ]);

      if (stt.status === 'fulfilled') this.sttStatus = stt.value;
      if (tts.status === 'fulfilled') this.ttsStatus = tts.value;
      if (engines.status === 'fulfilled') this.ttsEngines = engines.value;

      this._emitTelemetry();
    } catch (e) {
      console.warn('[Vāṇī] Could not refresh voice statuses:', e);
    }
  }

  async refreshTTSStatus() {
    try {
      this.ttsStatus = await api.getTTSStatus();
      this.ttsEngines = await api.getTTSEngines();
      this._emitTelemetry();
    } catch (e) {
      console.warn('[Vāṇī] Could not refresh TTS status:', e);
    }
    return this.ttsStatus;
  }

  getSTTStatus() {
    return this.sttStatus;
  }

  getTTSStatus() {
    return this.ttsStatus;
  }

  getTTSEngines() {
    return this.ttsEngines;
  }

  getLastTelemetry() {
    return this.lastTelemetry;
  }

  getLastError() {
    return this.lastError;
  }

  // Capability checks
  isMediaRecorderSupported() {
    return typeof window !== 'undefined' && Boolean(navigator?.mediaDevices?.getUserMedia) && Boolean(window.MediaRecorder);
  }

  isBrowserRecognitionSupported() {
    return Boolean(SpeechRecognitionAPI);
  }

  isSynthesisSupported() {
    return Boolean(SpeechSynthesisAPI);
  }

  getBrowserNotice() {
    if (!this.isMediaRecorderSupported() && !this.isBrowserRecognitionSupported()) {
      return 'MICROPHONE ACCESS UNAVAILABLE: Browser does not support MediaRecorder or SpeechRecognition.';
    }
    return null;
  }

  // Settings management
  _loadSettings() {
    if (typeof window === 'undefined') return { ...DEFAULT_SETTINGS };
    try {
      const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (raw) {
        return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
      }
    } catch (e) {
      console.warn('[Vāṇī] Failed to load voice settings:', e);
    }
    return { ...DEFAULT_SETTINGS };
  }

  getSettings() {
    return { ...this.settings };
  }

  saveSettings(newSettings) {
    this.settings = { ...this.settings, ...newSettings };
    try {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(this.settings));
    } catch (e) {
      console.warn('[Vāṇī] Failed to save voice settings:', e);
    }
    return this.settings;
  }

  getVoices() {
    if (!this.speechSynthesis) return [];
    return this.speechSynthesis.getVoices() || [];
  }

  getState() {
    return this.state;
  }

  setState(newState) {
    this.state = newState;
    this.onStateChangeCallbacks.forEach((cb) => {
      try {
        cb(newState);
      } catch (err) {
        console.error('[Vāṇī] State callback error:', err);
      }
    });
  }

  onStateChange(cb) {
    this.onStateChangeCallbacks.add(cb);
    return () => this.onStateChangeCallbacks.delete(cb);
  }

  onTelemetry(cb) {
    this.onTelemetryCallbacks.add(cb);
    return () => this.onTelemetryCallbacks.delete(cb);
  }

  _emitTelemetry(extra = {}) {
    const payload = {
      stt_status: this.sttStatus,
      tts_status: this.ttsStatus,
      tts_engines: this.ttsEngines,
      last_telemetry: this.lastTelemetry,
      state: this.state,
      error: this.lastError,
      ...extra
    };
    this.onTelemetryCallbacks.forEach((cb) => {
      try {
        cb(payload);
      } catch (err) {
        console.error('[Vāṇī] Telemetry callback error:', err);
      }
    });
  }

  // =========================================================================
  // Two-Way Voice Recording (Local Whisper STT) with Barge-In
  // =========================================================================

  /**
   * Start recording user speech via MediaRecorder.
   * Immediately interrupts any active speech playback (barge-in).
   */
  async startRecording({ onStart, onError } = {}) {
    // Immediate barge-in: stop any playing speech
    if (this.isSpeaking) {
      this.stopSpeaking();
    }

    if (!this.isMediaRecorderSupported()) {
      const err = new Error(this.getBrowserNotice() || 'MediaRecorder not supported');
      this.lastError = err.message;
      this.setState('ERROR');
      if (onError) onError(err);
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      this.mediaStream = stream;
      this.audioChunks = [];

      // Determine supported mimeType
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/wav');

      const recorder = new MediaRecorder(stream, { mimeType });
      this.mediaRecorder = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      recorder.onstart = () => {
        this.isListening = true;
        this.lastError = null;
        this.setState('LISTENING');
        if (onStart) onStart();
      };

      recorder.onerror = (event) => {
        console.error('[Vāṇī] MediaRecorder error:', event.error);
        this.isListening = false;
        this.lastError = event.error?.message || 'Recording error occurred';
        this.setState('ERROR');
        this._cleanupMediaStream();
        if (onError) onError(event.error);
      };

      recorder.start(100); // 100ms timeslice
      return true;
    } catch (err) {
      console.error('[Vāṇī] Microphone acquisition error:', err);
      this.isListening = false;
      this.lastError = err.name === 'NotAllowedError'
        ? 'Microphone permission denied. Please grant microphone access.'
        : `Microphone error: ${err.message}`;
      this.setState('ERROR');
      if (onError) onError(err);
      return false;
    }
  }

  /**
   * Stop recording and package audio chunks into Blob.
   * Returns audio Blob for STT / voice interaction.
   */
  async stopRecording() {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
        this.isListening = false;
        this._cleanupMediaStream();
        resolve(null);
        return;
      }

      this.mediaRecorder.onstop = () => {
        this.isListening = false;
        const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
        const blob = new Blob(this.audioChunks, { type: mimeType });
        this.audioChunks = [];
        this._cleanupMediaStream();
        resolve(blob);
      };

      try {
        this.mediaRecorder.stop();
      } catch (err) {
        console.warn('[Vāṇī] Error stopping mediaRecorder:', err);
        this.isListening = false;
        this._cleanupMediaStream();
        resolve(null);
      }
    });
  }

  _cleanupMediaStream() {
    if (this.mediaStream) {
      try {
        this.mediaStream.getTracks().forEach((track) => track.stop());
      } catch (e) {
        // ignore
      }
      this.mediaStream = null;
    }
    this.mediaRecorder = null;
  }

  // =========================================================================
  // Two-Way Voice Pipeline Dispatch
  // =========================================================================

  /**
   * Complete Two-Way Interaction:
   * 1. Stops recording to get Blob.
   * 2. Sets state to 'PROCESSING'.
   * 3. Posts to /api/voice/interact (Whisper STT -> Core / Tools -> Local TTS).
   * 4. Plays returned in-memory audio.
   * 5. Emits real telemetry and returns full interaction payload.
   */
  async processVoiceTurn(chatId = null, provider = null, model = null) {
    const audioBlob = await this.stopRecording();
    if (!audioBlob || audioBlob.size < 100) {
      this.setState('IDLE');
      return null;
    }

    this.isProcessing = true;
    this.setState('PROCESSING');

    try {
      const result = await api.voiceInteract(audioBlob, chatId, provider, model);

      this.isProcessing = false;
      this.lastTelemetry = result.telemetry || null;
      this._emitTelemetry({ last_telemetry: this.lastTelemetry, result });

      // If audio base64 is returned, play it in memory immediately
      if (result.audio_base64) {
        await this.playBase64Audio(result.audio_base64, result.audio_format || 'wav');
      } else {
        this.setState('IDLE');
      }

      return result;
    } catch (err) {
      console.error('[Vāṇī] Voice turn processing failed:', err);
      this.isProcessing = false;
      this.lastError = err.message;
      this.setState('ERROR');
      this._emitTelemetry();
      throw err;
    }
  }

  // =========================================================================
  // Speech Playback & In-Memory Audio Management
  // =========================================================================

  /**
   * Play base64-encoded audio directly in memory without creating persistent files.
   * Safely revokes Object URL on completion or interrupt.
   */
  async playBase64Audio(base64Data, format = 'wav') {
    this.stopSpeaking();

    try {
      const binaryString = window.atob(base64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const blob = new Blob([bytes.buffer], { type: `audio/${format}` });
      const audioUrl = URL.createObjectURL(blob);
      this.currentAudioUrl = audioUrl;

      const audio = new Audio(audioUrl);
      this.audioElement = audio;
      audio.volume = this.settings.voiceVolume ?? 1.0;

      audio.onplay = () => {
        this.isSpeaking = true;
        this.setState('SPEAKING');
      };

      audio.onended = () => {
        this._cleanupAudio();
        this.isSpeaking = false;
        if (this.state === 'SPEAKING') {
          this.setState('IDLE');
        }
      };

      audio.onerror = (e) => {
        console.warn('[Vāṇī] Audio playback error:', e);
        this._cleanupAudio();
        this.isSpeaking = false;
        this.setState('IDLE');
      };

      await audio.play();
      return true;
    } catch (err) {
      console.error('[Vāṇī] playBase64Audio error:', err);
      this._cleanupAudio();
      this.isSpeaking = false;
      this.setState('IDLE');
      return false;
    }
  }

  cleanTextForSpeech(text) {
    if (!text) return '';

    let clean = text;
    clean = clean.replace(/```[\s\S]*?```/g, ' [Code block omitted] ');
    clean = clean.replace(/`([^`]+)`/g, '$1');
    clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
    clean = clean.replace(/https?:\/\/\S+/g, '');
    clean = clean.replace(/\|.*?\|/g, ' ');
    clean = clean.replace(/[-:]{3,}/g, ' ');
    clean = clean.replace(/[*_]{1,3}(.*?)[*_]{1,3}/g, '$1');
    clean = clean.replace(/#+\s+/g, '');
    clean = clean.replace(/^\s*[-•*+]\s+/gm, '');
    clean = clean.replace(/\s+/g, ' ').trim();

    return clean;
  }

  /**
   * Synthesize and speak text through the TTS Router (Chatterbox / IndicVoice).
   * Falls back to Browser SpeechSynthesis if local engines are unavailable.
   */
  async speak(text, { onStart, onEnd, onError, rate, volume, voiceName, language = 'auto' } = {}) {
    this.stopSpeaking();

    const cleanText = this.cleanTextForSpeech(text);
    if (!cleanText) return false;

    if (!this.ttsStatus) {
      await this.refreshTTSStatus();
    }

    // Try Local TTS Router first
    if (this.ttsStatus && this.ttsStatus.ready) {
      try {
        const audioBlob = await api.synthesizeTTS(cleanText, language);
        const audioUrl = URL.createObjectURL(audioBlob);
        this.currentAudioUrl = audioUrl;
        
        const audio = new Audio(audioUrl);
        this.audioElement = audio;
        audio.volume = volume ?? this.settings.voiceVolume ?? 1.0;

        audio.onplay = () => {
          this.isSpeaking = true;
          this.setState('SPEAKING');
          if (onStart) onStart();
        };

        audio.onended = () => {
          this._cleanupAudio();
          this.isSpeaking = false;
          if (this.state === 'SPEAKING') {
            this.setState('IDLE');
          }
          if (onEnd) onEnd();
        };

        audio.onerror = (e) => {
          console.warn('[Vāṇī] Local audio playback error, falling back to browser synthesis:', e);
          this._cleanupAudio();
          this._speakBrowserFallback(cleanText, { onStart, onEnd, onError, rate, volume, voiceName });
        };

        await audio.play();
        return true;
      } catch (err) {
        console.warn('[Vāṇī] Local TTS synthesis failed, trying browser synthesis fallback:', err.message);
        this._cleanupAudio();
        return this._speakBrowserFallback(cleanText, { onStart, onEnd, onError, rate, volume, voiceName });
      }
    }

    // Browser Fallback
    const fallbackReason = this.ttsStatus?.error || 'Local TTS engines not ready';
    return this._speakBrowserFallback(cleanText, { onStart, onEnd, onError, rate, volume, voiceName }, fallbackReason);
  }

  _speakBrowserFallback(cleanText, { onStart, onEnd, onError, rate, volume, voiceName } = {}, reason = '') {
    if (!this.isSynthesisSupported()) {
      if (onError) onError(new Error('Speech Synthesis is not supported in this browser.'));
      return false;
    }

    console.info('[Vāṇī] Using Browser SpeechSynthesis Fallback. Reason:', reason);

    try {
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = rate ?? this.settings.speechRate ?? 1.0;
      utterance.volume = volume ?? this.settings.voiceVolume ?? 1.0;
      utterance.pitch = 1.0;
      utterance.lang = 'en-US';

      const targetVoiceName = voiceName || this.settings.selectedVoice;
      const voices = this.speechSynthesis.getVoices() || [];
      let selectedVoice = null;

      if (targetVoiceName) {
        selectedVoice = voices.find((v) => v.name === targetVoiceName);
      }

      if (!selectedVoice) {
        selectedVoice = voices.find(
          (v) =>
            (v.name.includes('Samantha') ||
              v.name.includes('Daniel') ||
              v.name.includes('Google US English') ||
              v.name.includes('Natural') ||
              v.name.includes('en-US')) &&
            v.lang.startsWith('en')
        );
      }

      if (selectedVoice) {
        utterance.voice = selectedVoice;
      }

      utterance.onstart = () => {
        this.isSpeaking = true;
        this.setState('SPEAKING');
        if (onStart) onStart();
      };

      utterance.onend = () => {
        this.isSpeaking = false;
        this.currentUtterance = null;
        if (this.state === 'SPEAKING') {
          this.setState('IDLE');
        }
        if (onEnd) onEnd();
      };

      utterance.onerror = (event) => {
        this.isSpeaking = false;
        this.currentUtterance = null;
        if (this.state === 'SPEAKING') {
          this.setState('IDLE');
        }
        if (onError && event.error !== 'interrupted' && event.error !== 'canceled') {
          onError(event);
        }
      };

      this.currentUtterance = utterance;
      this.speechSynthesis.speak(utterance);
      return true;
    } catch (err) {
      console.error('[Vāṇī] Fallback speech synthesis error:', err);
      this.isSpeaking = false;
      this.setState('IDLE');
      if (onError) onError(err);
      return false;
    }
  }

  _cleanupAudio() {
    if (this.audioElement) {
      try {
        this.audioElement.pause();
        this.audioElement.src = '';
      } catch (e) {
        // ignore
      }
      this.audioElement = null;
    }
    if (this.currentAudioUrl) {
      try {
        URL.revokeObjectURL(this.currentAudioUrl);
      } catch (e) {
        // ignore
      }
      this.currentAudioUrl = null;
    }
  }

  /**
   * Immediate Interrupt / Barge-In:
   * Instantly terminates playback, cleans up audio buffers, and sets state to IDLE.
   */
  stopSpeaking() {
    this._cleanupAudio();

    if (this.speechSynthesis) {
      try {
        this.speechSynthesis.cancel();
      } catch (err) {
        // ignore
      }
    }
    this.isSpeaking = false;
    this.currentUtterance = null;
    if (this.state === 'SPEAKING') {
      this.setState('IDLE');
    }
  }

  interrupt() {
    this.stopSpeaking();
    if (this.isListening) {
      this.stopRecording();
    }
  }

  /**
   * Universal halt: halts speech playback and listening, setting state to CANCELLED then IDLE.
   */
  halt() {
    this.stopSpeaking();
    this.stopRecording();
    this.setState('CANCELLED');
    setTimeout(() => {
      if (this.state === 'CANCELLED') {
        this.setState('IDLE');
      }
    }, 1000);
  }
}

// Global singleton instance for VĀṆĪ Voice Agent
export const vaaniService = new VaaniVoiceService();
