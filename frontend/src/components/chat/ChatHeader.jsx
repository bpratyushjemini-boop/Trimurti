import React from 'react';
import { Cpu, PanelRight, Shield } from 'lucide-react';
import NaradCoreIcon from '../common/NaradCoreIcon';

export default function ChatHeader({
  title = 'Active Briefing',
  activeProvider = 'gemini',
  activeModel = 'gemini-2.5-flash',
  onToggleRightPanel,
  isRightPanelOpen = true
}) {
  return (
    <header className="h-14 border-b border-narad-border bg-narad-surface/85 backdrop-blur-md px-6 flex items-center justify-between z-10 select-none">
      {/* Title & Status Indicator */}
      <div className="flex items-center gap-3 min-w-0">
        <NaradCoreIcon size={22} animated={true} className="flex-shrink-0" />
        <div className="flex items-center gap-2 min-w-0">
          <h2 className="font-display font-semibold text-sm tracking-wide text-white truncate max-w-md">
            {title}
          </h2>
          <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-narad-card border border-narad-border text-[10px] font-mono text-narad-cyan flex-shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]" />
            <span>LOCAL VAULT // 127.0.0.1</span>
          </span>
        </div>
      </div>

      {/* Model Indicator & Panel Toggle */}
      <div className="flex items-center gap-2.5">
        <div 
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-narad-card border border-narad-border text-xs font-mono text-narad-cyan shadow-hud-subtle"
          title={`Active Route: ${activeProvider} -> ${activeModel}`}
        >
          <Cpu size={13} className="text-narad-cyan" />
          <span className="hidden md:inline text-narad-textDim">MODEL:</span>
          <span className="font-semibold text-white tracking-wide">{activeModel.toUpperCase()}</span>
        </div>

        {/* Right Telemetry Toggle Button */}
        {onToggleRightPanel && (
          <button
            onClick={onToggleRightPanel}
            className={`p-1.5 rounded border transition-colors cursor-pointer ${
              isRightPanelOpen 
                ? 'bg-narad-cyan/15 text-narad-cyan border-narad-cyan/40' 
                : 'text-narad-textDim hover:text-white border-narad-border/60 hover:bg-narad-card'
            }`}
            title={isRightPanelOpen ? "Collapse Telemetry Panel" : "Expand Telemetry Panel"}
          >
            <PanelRight size={15} />
          </button>
        )}
      </div>
    </header>
  );
}
