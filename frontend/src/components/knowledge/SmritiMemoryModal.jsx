import React, { useState, useEffect } from 'react';
import {
  Brain,
  Search,
  Plus,
  Trash2,
  Edit3,
  RefreshCw,
  X,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Tag,
  Clock,
  Sparkles,
  ArrowUpRight
} from 'lucide-react';
import { api } from '../../services/api';

const CATEGORIES = [
  'ALL',
  'IDENTITY',
  'PREFERENCES',
  'PROJECTS',
  'DEVICES',
  'SKILLS',
  'PLANS',
  'FACTS'
];

const CATEGORY_COLORS = {
  IDENTITY: 'text-narad-cyan bg-narad-cyan/10 border-narad-cyan/30',
  PREFERENCES: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
  PROJECTS: 'text-narad-saffron bg-narad-saffron/10 border-narad-saffron/30',
  DEVICES: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  SKILLS: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  PLANS: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  FACTS: 'text-gray-300 bg-gray-500/10 border-gray-500/30',
  ROUTINES: 'text-pink-400 bg-pink-500/10 border-pink-500/30',
  RELATIONSHIPS: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
};

function formatDate(dateStr) {
  if (!dateStr) return 'Never';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return dateStr;
  }
}

export default function SmritiMemoryModal({ isOpen, onClose, onMemoryChange }) {
  const [memories, setMemories] = useState([]);
  const [statusData, setStatusData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [editingMemory, setEditingMemory] = useState(null);
  const [isAdding, setIsAdding] = useState(false);
  const [formKey, setFormKey] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formCategory, setFormCategory] = useState('FACTS');
  const [formImportance, setFormImportance] = useState(0.5);
  const [notification, setNotification] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, selectedCategory]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [st, memList] = await Promise.all([
        api.getMemoryStatus(),
        api.getMemories({
          category: selectedCategory === 'ALL' ? null : selectedCategory,
          search: searchTerm || null,
          limit: 100
        })
      ]);
      setStatusData(st);
      setMemories(memList || []);
      if (onMemoryChange) onMemoryChange(memList ? memList.length : 0);
    } catch (err) {
      console.error('[Smriti UI] Failed to load memories:', err);
      showNotification('error', 'Failed to retrieve Smṛti memories');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    loadData();
  };

  const showNotification = (type, message) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 4000);
  };

  const handleSaveMemory = async (e) => {
    e.preventDefault();
    if (!formKey.trim() || !formValue.trim()) return;

    try {
      if (editingMemory) {
        await api.updateMemory(editingMemory.id, {
          value: formValue.trim(),
          category: formCategory,
          importance: parseFloat(formImportance)
        });
        showNotification('success', `Updated memory '${editingMemory.key}' in Smṛti.`);
      } else {
        await api.saveMemory({
          key: formKey.trim(),
          value: formValue.trim(),
          category: formCategory,
          importance: parseFloat(formImportance)
        });
        showNotification('success', `Saved '${formKey.trim()}' to Smṛti memory vault.`);
      }
      setIsAdding(false);
      setEditingMemory(null);
      setFormKey('');
      setFormValue('');
      setFormCategory('FACTS');
      setFormImportance(0.5);
      loadData();
    } catch (err) {
      showNotification('error', err.message || 'Operation failed');
    }
  };

  const handleDelete = async (id, key) => {
    try {
      await api.deleteMemory(id);
      setDeleteConfirmId(null);
      showNotification('success', `Deleted '${key}' from Smṛti.`);
      loadData();
    } catch (err) {
      showNotification('error', err.message || 'Failed to delete memory');
    }
  };

  const handleStartEdit = (m) => {
    setEditingMemory(m);
    setFormKey(m.key);
    setFormValue(m.value);
    setFormCategory(m.category || 'FACTS');
    setFormImportance(m.importance !== undefined ? m.importance : 0.5);
    setIsAdding(true);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="bg-narad-surface border border-narad-border rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden relative saffron-accent-top">
        
        {/* Header */}
        <div className="p-4 border-b border-narad-border flex items-center justify-between bg-gradient-panel flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-narad-saffron/15 border border-narad-saffron/40 text-narad-saffron">
              <Brain size={22} className="animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold font-display text-white tracking-wider">
                  SMṚTI // PERSONAL MEMORY VAULT
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  ONLINE
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-narad-saffron/15 border border-narad-saffron/30 text-narad-gold">
                  V3.0
                </span>
              </div>
              <p className="text-xs text-narad-textMuted font-mono">
                Persistent Memory Intelligence • SQLite Ground Truth • Zero Hallucination
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadData}
              disabled={isLoading}
              className="p-2 rounded-lg bg-narad-card hover:bg-narad-card/80 border border-narad-border text-narad-textDim hover:text-white transition-all cursor-pointer"
              title="Refresh Memory Vault"
            >
              <RefreshCw size={15} className={isLoading ? 'animate-spin text-narad-cyan' : ''} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-narad-card hover:bg-narad-card/80 border border-narad-border text-narad-textDim hover:text-white transition-all cursor-pointer"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Notification Toast */}
        {notification && (
          <div className={`px-4 py-2 text-xs font-mono flex items-center gap-2 transition-all ${
            notification.type === 'success' ? 'bg-emerald-500/20 text-emerald-300 border-b border-emerald-500/40' : 'bg-rose-500/20 text-rose-300 border-b border-rose-500/40'
          }`}>
            {notification.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
            <span>{notification.message}</span>
          </div>
        )}

        {/* Toolbar: Category Chips + Add Action */}
        <div className="p-3 border-b border-narad-border/60 bg-narad-bg/60 flex flex-wrap items-center justify-between gap-3 flex-shrink-0">
          {/* Category Chips */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-[70%]">
            {CATEGORIES.map((cat) => {
              const isSelected = selectedCategory === cat;
              const count = cat === 'ALL'
                ? statusData?.total_memories || memories.length
                : statusData?.categories?.[cat] || 0;

              return (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-all flex items-center gap-1.5 cursor-pointer flex-shrink-0 ${
                    isSelected
                      ? 'bg-narad-saffron/20 border border-narad-saffron text-narad-gold font-bold shadow-[0_0_8px_rgba(255,153,51,0.2)]'
                      : 'bg-narad-card/50 hover:bg-narad-card border border-narad-border/50 text-narad-textDim hover:text-white'
                  }`}
                >
                  <span>{cat}</span>
                  <span className={`text-[10px] px-1 py-0.2 rounded ${isSelected ? 'bg-narad-saffron/30 text-white' : 'bg-narad-bg/70 text-narad-textDim'}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Search & Add Button */}
          <div className="flex items-center gap-2 flex-grow justify-end">
            <form onSubmit={handleSearch} className="relative flex-grow max-w-xs">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-narad-textDim" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search memories..."
                className="w-full bg-narad-card border border-narad-border/60 rounded-lg pl-8 pr-3 py-1.5 text-xs font-mono text-white placeholder:text-narad-textDim focus:outline-none focus:border-narad-cyan/60"
              />
            </form>

            <button
              onClick={() => {
                setEditingMemory(null);
                setFormKey('');
                setFormValue('');
                setFormCategory(selectedCategory === 'ALL' ? 'FACTS' : selectedCategory);
                setFormImportance(0.5);
                setIsAdding(!isAdding);
              }}
              className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-narad-saffron/20 to-narad-cyan/15 hover:from-narad-saffron/30 hover:to-narad-cyan/25 border border-narad-saffron/50 text-narad-gold text-xs font-mono font-semibold flex items-center gap-1.5 transition-all cursor-pointer flex-shrink-0"
            >
              <Plus size={14} />
              <span>{isAdding ? 'CANCEL' : 'ADD MEMORY'}</span>
            </button>
          </div>
        </div>

        {/* Add / Edit Form Modal Drawer */}
        {isAdding && (
          <div className="p-4 border-b border-narad-border bg-narad-card/70 animate-in slide-in-from-top-2 duration-150 flex-shrink-0">
            <form onSubmit={handleSaveMemory} className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-narad-gold font-bold flex items-center gap-1.5">
                  <Sparkles size={14} className="text-narad-saffron" />
                  {editingMemory ? `EDITING MEMORY: ${editingMemory.key}` : 'NEW PERSISTENT MEMORY RECORD'}
                </span>
                <span className="text-[10px] font-mono text-narad-textDim">
                  Protected by Smṛti Secret-Redaction Guardrail
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] font-mono text-narad-textDim block mb-1">
                    KEY (ENTITY / TOPIC)
                  </label>
                  <input
                    type="text"
                    value={formKey}
                    onChange={(e) => setFormKey(e.target.value)}
                    disabled={!!editingMemory}
                    placeholder="e.g. favorite_color, device, main_project"
                    required
                    className="w-full bg-narad-bg border border-narad-border rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-narad-cyan disabled:opacity-60"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-mono text-narad-textDim block mb-1">
                    CATEGORY
                  </label>
                  <select
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="w-full bg-narad-bg border border-narad-border rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-narad-cyan"
                  >
                    {CATEGORIES.filter((c) => c !== 'ALL').map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[10px] font-mono text-narad-textDim block mb-1 flex justify-between">
                    <span>IMPORTANCE</span>
                    <span className="text-narad-cyan font-bold">{Math.round(formImportance * 100)}%</span>
                  </label>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={formImportance}
                    onChange={(e) => setFormImportance(parseFloat(e.target.value))}
                    className="w-full accent-narad-saffron cursor-pointer"
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] font-mono text-narad-textDim block mb-1">
                  VALUE (FACTUAL DECLARATION)
                </label>
                <textarea
                  value={formValue}
                  onChange={(e) => setFormValue(e.target.value)}
                  placeholder="e.g. blue, MacBook Pro M3, NARAD Phase 2..."
                  required
                  rows={2}
                  className="w-full bg-narad-bg border border-narad-border rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-narad-cyan"
                />
              </div>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsAdding(false);
                    setEditingMemory(null);
                  }}
                  className="px-3 py-1.5 rounded text-xs font-mono text-narad-textDim hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 rounded bg-narad-saffron hover:bg-narad-saffron/90 text-black font-mono text-xs font-bold transition-all"
                >
                  {editingMemory ? 'SAVE CHANGES' : 'STORE IN SMṚTI'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Memories List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5 min-h-[300px]">
          {isLoading ? (
            <div className="py-16 text-center text-xs font-mono text-narad-textDim flex flex-col items-center gap-2">
              <RefreshCw size={20} className="animate-spin text-narad-saffron" />
              <span>Querying Smṛti memory database...</span>
            </div>
          ) : memories.length === 0 ? (
            <div className="py-16 text-center text-xs font-mono text-narad-textDim flex flex-col items-center gap-2">
              <Brain size={32} className="text-narad-border" />
              <span className="text-sm font-semibold text-white">No memories found</span>
              <p className="max-w-md text-narad-textDim">
                {searchTerm
                  ? `No memories matched '${searchTerm}'.`
                  : 'Tell NARAD durable facts in chat like "My favorite color is blue" or click "+ ADD MEMORY" above.'}
              </p>
            </div>
          ) : (
            memories.map((m) => {
              const catColor = CATEGORY_COLORS[m.category] || CATEGORY_COLORS.FACTS;
              const isConfirmingDelete = deleteConfirmId === m.id;

              return (
                <div
                  key={m.id}
                  className="p-3 rounded-lg bg-narad-card/60 hover:bg-narad-card border border-narad-border/60 hover:border-narad-border transition-all flex flex-col gap-2 group"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-semibold ${catColor}`}>
                        {m.category || 'FACTS'}
                      </span>
                      <span className="font-mono text-xs font-bold text-white tracking-wide">
                        {m.key}
                      </span>
                      <span className="text-[10px] font-mono text-narad-textDim">
                        • {m.source || 'conversation'}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 opacity-90 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleStartEdit(m)}
                        className="p-1.5 rounded hover:bg-narad-bg text-narad-textDim hover:text-narad-cyan transition-colors"
                        title="Edit Memory"
                      >
                        <Edit3 size={13} />
                      </button>

                      {isConfirmingDelete ? (
                        <div className="flex items-center gap-1 bg-rose-500/10 border border-rose-500/40 rounded px-1.5 py-0.5 animate-in fade-in">
                          <span className="text-[10px] font-mono text-rose-400">Forget?</span>
                          <button
                            onClick={() => handleDelete(m.id, m.key)}
                            className="text-[10px] font-mono font-bold text-rose-400 hover:text-rose-200 px-1"
                          >
                            YES
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="text-[10px] font-mono text-narad-textDim hover:text-white px-1"
                          >
                            NO
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirmId(m.id)}
                          className="p-1.5 rounded hover:bg-rose-500/20 text-narad-textDim hover:text-rose-400 transition-colors"
                          title="Forget/Delete Memory"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Memory Value */}
                  <div className="text-xs font-sans text-narad-text bg-narad-bg/50 p-2.5 rounded border border-narad-border/30 whitespace-pre-wrap break-words">
                    {m.value}
                  </div>

                  {/* Footer telemetry */}
                  <div className="flex items-center justify-between text-[10px] font-mono text-narad-textDim pt-1 border-t border-narad-border/20">
                    <div className="flex items-center gap-3">
                      <span>Conf: {Math.round((m.confidence || 1.0) * 100)}%</span>
                      <span>Imp: {Math.round((m.importance || 0.5) * 100)}%</span>
                      <span>Used: {m.times_used || 0}x</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Clock size={11} />
                      <span>Updated: {formatDate(m.updated_at)}</span>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer: Quick Natural Commands Reference */}
        <div className="p-3 border-t border-narad-border bg-narad-bg/80 flex items-center justify-between text-xs font-mono text-narad-textDim flex-shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck size={14} className="text-emerald-400" />
            <span>Privacy Guardrail Active • Secrets & Credentials Auto-Redacted</span>
          </div>
          <div className="hidden md:flex items-center gap-2">
            <span className="text-narad-gold">Chat Commands:</span>
            <span className="text-narad-textMuted">"Remember that...", "Forget that...", "Show my memories"</span>
          </div>
        </div>
      </div>
    </div>
  );
}
