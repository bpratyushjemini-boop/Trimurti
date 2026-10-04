import React from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import SystemStatus from './SystemStatus';
import ProviderInfo from './ProviderInfo';
import ContextPanel from './ContextPanel';
import QuickTools from './QuickTools';
import ToolActivity from './ToolActivity';
import SubsystemsStatus from './SubsystemsStatus';
import VisualDebugPanel from './VisualDebugPanel';
import TaskEnginePanel from './TaskEnginePanel';

export default function RightSidebar({
  healthData,
  runtimeTruth = null,
  onRefreshHealth,
  messages = [],
  onSelectPrompt,
  isOpen = true,
  lastTelemetry = null,
  isSending = false,
  isVoiceMode = false,
  voiceState = 'IDLE',
  agentTelemetry = { state: 'IDLE', current_action: null, dry_run: false }
}) {
  if (!isOpen) return null;

  return (
    <aside className="w-80 h-full bg-narad-surface border-l border-narad-border flex flex-col select-none overflow-y-auto flex-shrink-0 z-10 transition-all duration-200 saffron-accent-top">
      {/* HUD Header */}
      <div className="p-4 border-b border-narad-border flex items-center justify-between sticky top-0 bg-narad-surface/95 backdrop-blur-xl z-10">
        <div className="flex items-center gap-2">
          <Activity size={15} className="text-narad-saffron animate-pulse" />
          <h2 className="font-display font-semibold text-xs tracking-widest text-white uppercase">
            System Telemetry
          </h2>
          <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-narad-saffron/15 border border-narad-saffron/30 text-narad-saffron">
            LIVE TRUTH
          </span>
        </div>

        <button
          onClick={onRefreshHealth}
          className="p-1.5 rounded-md text-narad-textDim hover:text-narad-cyan hover:bg-narad-card transition-all duration-200 cursor-pointer hover:rotate-180"
          title="Refresh Telemetry"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Modular HUD Content */}
      <div className="p-3.5 space-y-3">
        <SystemStatus healthData={healthData} runtimeTruth={runtimeTruth} lastTelemetry={lastTelemetry} />
        <ProviderInfo
          activeProvider={runtimeTruth?.inference?.provider || healthData?.active_provider}
          activeModel={runtimeTruth?.inference?.model || healthData?.active_model}
          isConfigured={healthData?.is_configured}
          healthData={healthData}
          runtimeTruth={runtimeTruth}
          lastTelemetry={lastTelemetry}
        />
        <ContextPanel messages={messages} />
        <QuickTools onSelectPrompt={onSelectPrompt} />
        <ToolActivity lastTelemetry={lastTelemetry} isSending={isSending} messages={messages} />
        <TaskEnginePanel />
        <VisualDebugPanel agentTelemetry={agentTelemetry} />
        <SubsystemsStatus 
          isVoiceMode={isVoiceMode} 
          voiceState={voiceState} 
          agentTelemetry={agentTelemetry}
          lastTelemetry={lastTelemetry}
          runtimeTruth={runtimeTruth}
        />
      </div>
    </aside>
  );
}
