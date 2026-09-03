import React from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import SystemStatus from './SystemStatus';
import ProviderInfo from './ProviderInfo';
import ContextPanel from './ContextPanel';
import QuickTools from './QuickTools';
import ToolActivity from './ToolActivity';
import SubsystemsStatus from './SubsystemsStatus';

export default function RightSidebar({
  healthData,
  onRefreshHealth,
  messages = [],
  onSelectPrompt,
  isOpen = true,
  lastTelemetry = null
}) {
  if (!isOpen) return null;

  return (
    <aside className="w-80 h-full bg-narad-surface border-l border-narad-border flex flex-col select-none overflow-y-auto flex-shrink-0 z-10 transition-all duration-200">
      {/* HUD Header */}
      <div className="p-4 border-b border-narad-border flex items-center justify-between sticky top-0 bg-narad-surface/95 backdrop-blur-md z-10">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-narad-cyan animate-pulse" />
          <h2 className="font-display font-semibold text-xs tracking-widest text-white uppercase">
            System Telemetry
          </h2>
        </div>

        <button
          onClick={onRefreshHealth}
          className="p-1.5 rounded text-narad-textDim hover:text-narad-cyan hover:bg-narad-card transition-colors cursor-pointer"
          title="Refresh Telemetry Link"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Modular HUD Content */}
      <div className="p-3.5 space-y-3.5">
        {/* 1. Core Health & Engine Status */}
        <SystemStatus
          healthData={healthData}
          lastTelemetry={lastTelemetry}
        />

        {/* 2. Model Router / Provider Info */}
        <ProviderInfo
          activeProvider={healthData?.active_provider}
          activeModel={healthData?.active_model}
          isConfigured={healthData?.is_configured}
          lastTelemetry={lastTelemetry}
        />

        {/* 3. Working Memory & Context Token Counter */}
        <ContextPanel messages={messages} />

        {/* 4. Quick Directives & Tools */}
        <QuickTools onSelectPrompt={onSelectPrompt} />

        {/* 5. Tool Activity & Execution Queue */}
        <ToolActivity />

        {/* 6. TRIMURTI Subsystems Ecosystem Breakdown */}
        <SubsystemsStatus />
      </div>
    </aside>
  );
}
