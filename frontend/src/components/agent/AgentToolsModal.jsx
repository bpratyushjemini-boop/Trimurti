import React, { useState, useEffect } from 'react';
import {
  Wrench,
  X,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  RefreshCw,
  Terminal,
  ExternalLink,
  Cpu,
  Eye,
  Database,
  Globe,
  FolderOpen
} from 'lucide-react';
import { api } from '../../services/api';

export default function AgentToolsModal({ isOpen, onClose, onSelectPrompt }) {
  const [tools, setTools] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');

  useEffect(() => {
    if (isOpen) {
      loadTools();
    }
  }, [isOpen]);

  const loadTools = async () => {
    setIsLoading(true);
    try {
      const data = await api.getAgentTools();
      setTools(data.tools || []);
    } catch (err) {
      console.error('Failed to load agent tools:', err);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  const categorizeTool = (tool) => {
    const name = tool.name.toLowerCase();
    if (name.includes('time') || name.includes('date') || name.includes('calculator')) return 'CORE';
    if (name.includes('memory') || name.includes('smriti')) return 'MEMORY';
    if (name.includes('screen') || name.includes('screenshot') || name.includes('vision')) return 'VISION';
    if (name.includes('browser') || name.includes('url')) return 'BROWSER';
    if (name.includes('file') || name.includes('directory') || name.includes('folder')) return 'FILESYSTEM';
    if (name.includes('search') || name.includes('knowledge')) return 'KNOWLEDGE';
    if (name.includes('application') || name.includes('music') || name.includes('process') || name.includes('system')) return 'SYSTEM';
    return 'OTHER';
  };

  const categories = ['ALL', 'CORE', 'MEMORY', 'VISION', 'BROWSER', 'FILESYSTEM', 'KNOWLEDGE', 'SYSTEM'];

  const filteredTools = tools.filter((tool) => {
    const matchesSearch =
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (tool.description || '').toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;
    if (selectedCategory === 'ALL') return true;
    return categorizeTool(tool) === selectedCategory;
  });

  const getLevelBadge = (level) => {
    switch (level) {
      case 0:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            <ShieldCheck size={10} />
            <span>L0 SAFE</span>
          </span>
        );
      case 1:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
            <Shield size={10} />
            <span>L1 LOW RISK</span>
          </span>
        );
      case 2:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
            <ShieldAlert size={10} />
            <span>L2 CONFIRM</span>
          </span>
        );
      case 3:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30">
            <ShieldAlert size={10} />
            <span>L3 HIGH RISK</span>
          </span>
        );
      case 4:
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-purple-500/15 text-purple-400 border border-purple-500/30">
            <Shield size={10} />
            <span>L4 SANDBOXED</span>
          </span>
        );
    }
  };

  const handleUseToolInChat = (tool) => {
    let sample = `NARAD, execute tool '${tool.name}'`;
    if (tool.name === 'calculator') {
      sample = 'Calculate 4829 multiplied by 37';
    } else if (tool.name === 'get_current_time') {
      sample = 'What time is it right now?';
    } else if (tool.name === 'understand_screen') {
      sample = 'What is currently on my screen?';
    } else if (tool.name === 'web_search') {
      sample = 'Search the web for the latest updates on Python 3.13';
    } else if (tool.name === 'retrieve_memory') {
      sample = 'Retrieve my stored memories about my preferences';
    } else if (tool.name === 'control_apple_music') {
      sample = 'Play Back in Black on Apple Music';
    }
    if (onSelectPrompt) {
      onSelectPrompt(sample);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-4xl bg-narad-surface border border-narad-border rounded-xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden saffron-accent-top">
        {/* Header */}
        <div className="p-4 border-b border-narad-border flex items-center justify-between bg-gradient-panel">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-narad-card border border-narad-saffron/40 flex items-center justify-center shadow-hud-saffron">
              <Wrench size={16} className="text-narad-saffron" />
            </div>
            <div>
              <h2 className="font-display font-bold text-sm tracking-wider text-white flex items-center gap-2">
                <span>KRĪYA // AGENT TOOLS REGISTRY</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-narad-saffron/15 text-narad-gold border border-narad-saffron/30">
                  {tools.length} REGISTERED
                </span>
              </h2>
              <p className="text-[10px] font-mono text-narad-textDim">
                Provider-independent local & autonomous tool dispatcher with policy sandboxing
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadTools}
              disabled={isLoading}
              className="p-1.5 rounded-lg border border-narad-border/60 hover:border-narad-cyan/40 text-narad-textDim hover:text-narad-cyan bg-narad-card/40 transition-colors cursor-pointer"
              title="Refresh Registry"
            >
              <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg border border-narad-border/60 hover:border-rose-500/40 text-narad-textDim hover:text-rose-400 bg-narad-card/40 transition-colors cursor-pointer"
              title="Close"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Search & Category Filter Toolbar */}
        <div className="px-4 py-3 border-b border-narad-border/60 bg-narad-bg/40 flex flex-wrap items-center justify-between gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-narad-textDim" />
            <input
              type="text"
              placeholder="Search tools by name, action, or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-narad-bg/80 border border-narad-border/60 focus:border-narad-cyan/60 rounded-lg px-3 pl-8 py-1.5 text-xs text-narad-text placeholder:text-narad-textDim font-mono focus:outline-none transition-all duration-200"
            />
          </div>

          <div className="flex items-center gap-1 overflow-x-auto py-0.5">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded-md text-[10px] font-mono font-medium transition-all duration-200 cursor-pointer ${
                  selectedCategory === cat
                    ? 'bg-narad-saffron/20 text-narad-gold border border-narad-saffron/50 shadow-sm font-semibold'
                    : 'text-narad-textDim hover:text-white bg-narad-card/30 hover:bg-narad-card border border-transparent'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Security Policy Legend */}
        <div className="px-4 py-2 border-b border-narad-border/40 bg-narad-card/20 flex items-center justify-between text-[10px] font-mono text-narad-textDim overflow-x-auto">
          <span className="text-white font-medium flex items-center gap-1.5">
            <Shield size={11} className="text-narad-cyan" />
            <span>SECURITY MATRIX:</span>
          </span>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1 text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              L0: Immediate Safe
            </span>
            <span className="flex items-center gap-1 text-cyan-400">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              L1: Low Risk
            </span>
            <span className="flex items-center gap-1 text-amber-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              L2: User Approval
            </span>
            <span className="flex items-center gap-1 text-rose-400">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
              L3: Explicit Authorization
            </span>
            <span className="flex items-center gap-1 text-purple-400">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
              L4: Sandboxed / Path Validated
            </span>
          </div>
        </div>

        {/* Tool Cards Grid */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
          {isLoading ? (
            <div className="py-16 text-center space-y-2">
              <RefreshCw size={24} className="text-narad-cyan animate-spin mx-auto" />
              <p className="text-xs font-mono text-narad-textDim">Querying Krīya Tool Dispatcher...</p>
            </div>
          ) : filteredTools.length === 0 ? (
            <div className="py-16 text-center space-y-2 font-mono text-narad-textDim text-xs">
              <p>No tools matching "{searchQuery}"</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {filteredTools.map((tool) => {
                const params = tool.parameters?.properties ? Object.keys(tool.parameters.properties) : [];
                return (
                  <div
                    key={tool.name}
                    className="p-3.5 rounded-xl bg-narad-card/40 hover:bg-narad-card/70 border border-narad-border/50 hover:border-narad-cyan/40 transition-all duration-200 flex flex-col justify-between gap-3 group"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <Terminal size={14} className="text-narad-cyan group-hover:text-narad-saffron transition-colors flex-shrink-0" />
                          <span className="font-mono font-bold text-xs text-white group-hover:text-narad-cyan transition-colors">
                            {tool.name}
                          </span>
                        </div>
                        {getLevelBadge(tool.permission_level)}
                      </div>

                      <p className="text-xs text-narad-textMuted leading-relaxed">
                        {tool.description || 'No description provided.'}
                      </p>

                      {params.length > 0 && (
                        <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
                          <span className="text-[10px] font-mono text-narad-textDim">ARGS:</span>
                          {params.map((p) => (
                            <span
                              key={p}
                              className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-narad-bg border border-narad-border/50 text-slate-300"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="pt-2 border-t border-narad-border/30 flex items-center justify-between text-[10px] font-mono text-narad-textDim">
                      <span className="truncate max-w-[200px]" title={tool.reason || tool.summary}>
                        {tool.summary || 'Kriya registered'}
                      </span>
                      <button
                        onClick={() => handleUseToolInChat(tool)}
                        className="px-2 py-1 rounded bg-narad-saffron/15 hover:bg-narad-saffron/25 text-narad-gold border border-narad-saffron/30 hover:border-narad-saffron/50 flex items-center gap-1 transition-all duration-150 cursor-pointer font-semibold"
                        title="Use tool in chat prompt"
                      >
                        <ExternalLink size={10} />
                        <span>DIRECTIVE</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-narad-border bg-narad-bg/60 flex items-center justify-between text-[10px] font-mono text-narad-textDim">
          <span>KRĪYA DISPATCHER • PROVIDER INDEPENDENT</span>
          <span>AUTONOMY PROTECTION ACTIVE</span>
        </div>
      </div>
    </div>
  );
}
