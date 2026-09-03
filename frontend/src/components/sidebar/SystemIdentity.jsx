import React from 'react';
import { ShieldCheck, HardDrive } from 'lucide-react';

/**
 * SystemIdentity: Communicates private, single-user local architecture.
 * Replaces commercial/multi-user SaaS account or profile cards.
 */
export default function SystemIdentity() {
  return (
    <div className="p-3 border-t border-narad-border bg-narad-surface/95 flex items-center justify-between select-none">
      <div className="flex items-center gap-2.5 min-w-0">
        {/* Local Node Shield Icon */}
        <div 
          className="w-8 h-8 rounded-lg border border-narad-borderBright bg-narad-card flex items-center justify-center text-narad-cyan flex-shrink-0 shadow-hud-subtle relative"
          title="Private Single-User Node"
        >
          <ShieldCheck size={16} className="text-narad-cyan" />
          <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 border border-narad-bg shadow-[0_0_6px_#34d399]" />
        </div>

        <div className="min-w-0">
          <div className="text-xs font-semibold text-white truncate flex items-center gap-1.5 font-mono">
            <span>NARAD CORE</span>
            <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-narad-card border border-narad-cyan/40 text-narad-cyan">
              LOCAL
            </span>
          </div>
          <div className="text-[10px] font-mono text-narad-textDim flex items-center gap-1 truncate">
            <HardDrive size={10} className="text-emerald-400 flex-shrink-0" />
            <span className="truncate">Private Vault // 127.0.0.1</span>
          </div>
        </div>
      </div>

      <div className="text-[9px] font-mono text-narad-textDim px-1.5 py-0.5 rounded border border-narad-border/40 bg-narad-card/50 flex-shrink-0">
        STANDALONE
      </div>
    </div>
  );
}
