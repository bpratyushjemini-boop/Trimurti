import React, { useState, useEffect, useRef } from 'react';
import {
  Database,
  UploadCloud,
  FileText,
  Trash2,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  X,
  RefreshCw,
  FileCode,
  Layers,
  ArrowRight,
  ShieldCheck
} from 'lucide-react';
import { api } from '../../services/api';

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateStr) {
  if (!dateStr) return 'Unknown';
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

export default function KnowledgeBaseModal({ isOpen, onClose, onDocumentChange }) {
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('documents'); // 'documents' | 'search'
  const [uploadStatus, setUploadStatus] = useState(null); // { status: 'idle'|'uploading'|'success'|'error', telemetry: [], message: '' }
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      loadDocuments();
      setUploadStatus(null);
      setSearchResults(null);
      setSearchQuery('');
    }
  }, [isOpen]);

  const loadDocuments = async () => {
    setIsLoading(true);
    try {
      const data = await api.getKnowledgeDocuments();
      setDocuments(data.documents || []);
      if (onDocumentChange) {
        onDocumentChange(data.documents || []);
      }
    } catch (err) {
      console.error('Failed to load knowledge documents:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;

    const allowedExts = ['.pdf', '.txt', '.md', '.markdown', '.docx'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowedExts.includes(ext)) {
      setUploadStatus({
        status: 'error',
        telemetry: ['INGESTING', 'FAILED'],
        message: `Unsupported format '${ext}'. Allowed: PDF, TXT, MD, DOCX`
      });
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      setUploadStatus({
        status: 'error',
        telemetry: ['INGESTING', 'FAILED'],
        message: 'File size exceeds maximum 25 MB limit.'
      });
      return;
    }

    setUploadStatus({
      status: 'uploading',
      telemetry: ['INGESTING', 'EXTRACTING', 'INDEXING'],
      message: `Ingesting '${file.name}' into private local index...`
    });

    try {
      const res = await api.uploadKnowledgeDocument(file);
      setUploadStatus({
        status: 'success',
        telemetry: res.telemetry || ['INGESTING', 'EXTRACTING', 'INDEXING', 'READY'],
        message: `Document '${file.name}' indexed successfully (${res.chunks_indexed || res.document?.chunk_count || 1} chunks ready).`
      });
      loadDocuments();
    } catch (err) {
      setUploadStatus({
        status: 'error',
        telemetry: ['INGESTING', 'FAILED'],
        message: err.message || 'Ingestion failure.'
      });
    }
  };

  const handleDelete = async (docId) => {
    try {
      await api.deleteKnowledgeDocument(docId);
      setDeleteConfirmId(null);
      loadDocuments();
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    try {
      const res = await api.searchKnowledge(searchQuery.trim(), 4);
      setSearchResults(res);
    } catch (err) {
      console.error('Search failed:', err);
      setSearchResults({ count: 0, results: [], error: err.message });
    } finally {
      setIsSearching(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fade-in select-none">
      <div 
        className="w-full max-w-3xl bg-narad-surface border border-narad-cyan/40 rounded-2xl shadow-[0_0_50px_rgba(0,240,255,0.15)] flex flex-col max-h-[85vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 border-b border-narad-border bg-narad-card/40 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-narad-cyan/15 border border-narad-cyan/40 flex items-center justify-center text-narad-cyan shadow-[0_0_12px_rgba(0,240,255,0.2)]">
              <Database size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display tracking-widest text-sm font-bold text-white">
                  KNOWLEDGE BASE
                </h2>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-narad-cyan/20 text-narad-cyan border border-narad-cyan/40">
                  V2.2 LOCAL VAULT
                </span>
              </div>
              <p className="text-[11px] font-mono text-narad-textDim flex items-center gap-1.5">
                <ShieldCheck size={12} className="text-emerald-400" />
                <span>Private local index • Zero cloud document uploads</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadDocuments}
              className="p-1.5 rounded-lg border border-narad-border hover:border-narad-cyan/40 text-narad-textDim hover:text-white transition-colors cursor-pointer"
              title="Refresh list"
            >
              <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg border border-narad-border hover:border-rose-500/50 text-narad-textDim hover:text-rose-400 transition-colors cursor-pointer"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-narad-border bg-narad-bg/50 px-4 pt-2">
          <button
            onClick={() => setActiveTab('documents')}
            className={`pb-2 px-3 text-xs font-mono tracking-wider flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
              activeTab === 'documents'
                ? 'border-narad-cyan text-narad-cyan font-semibold'
                : 'border-transparent text-narad-textDim hover:text-white'
            }`}
          >
            <FileText size={13} />
            <span>DOCUMENTS ({documents.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('search')}
            className={`pb-2 px-3 text-xs font-mono tracking-wider flex items-center gap-2 border-b-2 transition-all cursor-pointer ${
              activeTab === 'search'
                ? 'border-narad-cyan text-narad-cyan font-semibold'
                : 'border-transparent text-narad-textDim hover:text-white'
            }`}
          >
            <Search size={13} />
            <span>SEARCH KNOWLEDGE</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {activeTab === 'documents' ? (
            <>
              {/* Upload Drop Zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                    handleFileUpload(e.dataTransfer.files[0]);
                  }
                }}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-5 flex flex-col items-center justify-center gap-2.5 transition-all cursor-pointer ${
                  isDragging
                    ? 'border-narad-cyan bg-narad-cyan/10 scale-[0.99]'
                    : 'border-narad-border/80 hover:border-narad-cyan/50 bg-narad-card/20 hover:bg-narad-card/40'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.md,.markdown,.docx"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileUpload(e.target.files[0]);
                    }
                  }}
                />
                <div className="w-10 h-10 rounded-full bg-narad-cyan/10 border border-narad-cyan/30 flex items-center justify-center text-narad-cyan">
                  <UploadCloud size={20} />
                </div>
                <div className="text-center">
                  <p className="text-xs font-mono font-medium text-white">
                    Drop document here or <span className="text-narad-cyan underline">browse files</span>
                  </p>
                  <p className="text-[10px] font-mono text-narad-textDim mt-0.5">
                    Supported: PDF • TXT • Markdown (.md) • DOCX (Max 25 MB)
                  </p>
                </div>
              </div>

              {/* Upload Status / Telemetry Feedback */}
              {uploadStatus && (
                <div className={`p-3 rounded-xl border text-xs font-mono space-y-2 transition-all ${
                  uploadStatus.status === 'success'
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                    : uploadStatus.status === 'error'
                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                    : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold flex items-center gap-1.5">
                      {uploadStatus.status === 'success' && <CheckCircle2 size={14} className="text-emerald-400" />}
                      {uploadStatus.status === 'error' && <AlertCircle size={14} className="text-rose-400" />}
                      {uploadStatus.status === 'uploading' && <RefreshCw size={14} className="animate-spin text-amber-400" />}
                      {uploadStatus.message}
                    </span>
                  </div>

                  {/* Telemetry Pipeline Trace */}
                  {uploadStatus.telemetry && uploadStatus.telemetry.length > 0 && (
                    <div className="flex items-center gap-1.5 text-[10px] text-slate-300 pt-1 border-t border-white/10">
                      <span className="text-narad-textDim">Telemetry:</span>
                      {uploadStatus.telemetry.map((step, idx) => (
                        <React.Fragment key={idx}>
                          <span className={`px-1.5 py-0.2 rounded ${
                            step === 'READY'
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : step === 'FAILED'
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                              : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                          }`}>
                            {step}
                          </span>
                          {idx < uploadStatus.telemetry.length - 1 && (
                            <ArrowRight size={10} className="text-narad-textDim" />
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Documents List */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[10px] font-mono text-narad-textDim px-1 uppercase tracking-wider">
                  <span>Indexed Documents</span>
                  <span>{documents.length} Total</span>
                </div>

                {documents.length === 0 ? (
                  <div className="py-12 text-center text-xs font-mono text-narad-textDim border border-narad-border/40 rounded-xl bg-narad-card/20">
                    No documents indexed yet. Upload a PDF, TXT, MD, or DOCX to activate local retrieval.
                  </div>
                ) : (
                  documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="p-3 rounded-xl bg-narad-card/40 border border-narad-border/60 hover:border-narad-cyan/40 transition-all flex items-center justify-between gap-3 group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-narad-bg border border-narad-border flex items-center justify-center text-narad-cyan flex-shrink-0">
                          {doc.file_type === 'pdf' ? (
                            <FileText size={16} />
                          ) : doc.file_type === 'docx' ? (
                            <FileCode size={16} />
                          ) : (
                            <Layers size={16} />
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-mono font-semibold text-white truncate group-hover:text-narad-cyan transition-colors">
                            {doc.filename}
                          </p>
                          <div className="flex items-center gap-2 text-[10px] font-mono text-narad-textDim mt-0.5">
                            <span className="uppercase px-1 py-0.2 rounded bg-narad-bg border border-narad-border text-narad-cyan">
                              {doc.file_type}
                            </span>
                            <span>{formatBytes(doc.file_size)}</span>
                            <span>•</span>
                            <span>{doc.chunk_count || 0} chunks</span>
                            <span>•</span>
                            <span>{formatDate(doc.indexed_at || doc.created_at)}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {/* Status Badge */}
                        <span className={`text-[9px] font-mono px-2 py-0.5 rounded border ${
                          doc.status === 'READY'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : doc.status === 'FAILED'
                            ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                            : 'bg-amber-500/10 text-amber-300 border-amber-500/30 animate-pulse'
                        }`}>
                          {doc.status}
                        </span>

                        {/* Delete Action with Confirmation */}
                        {deleteConfirmId === doc.id ? (
                          <div className="flex items-center gap-1.5 animate-fade-in">
                            <span className="text-[10px] font-mono text-rose-400">Delete?</span>
                            <button
                              onClick={() => handleDelete(doc.id)}
                              className="px-2 py-0.5 text-[10px] font-mono bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 rounded transition-colors cursor-pointer"
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setDeleteConfirmId(null)}
                              className="px-2 py-0.5 text-[10px] font-mono bg-narad-card text-narad-textDim hover:text-white border border-narad-border rounded transition-colors cursor-pointer"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDeleteConfirmId(doc.id)}
                            className="p-1.5 rounded-lg border border-narad-border/60 hover:border-rose-500/50 text-narad-textDim hover:text-rose-400 transition-colors cursor-pointer"
                            title="Delete document"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          ) : (
            /* Interactive Search Knowledge Tab */
            <div className="space-y-4">
              <form onSubmit={handleSearch} className="flex gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-narad-textDim" />
                  <input
                    type="text"
                    placeholder="Search indexed local documents (e.g., 'Trimurti purpose', 'modules')..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-narad-card/40 border border-narad-border focus:border-narad-cyan rounded-xl pl-9 pr-3 py-2 text-xs font-mono text-white placeholder:text-narad-textDim focus:outline-none transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  disabled={isSearching || !searchQuery.trim()}
                  className="px-4 py-2 bg-narad-cyan/15 hover:bg-narad-cyan/25 border border-narad-cyan/40 hover:border-narad-cyan/70 text-narad-cyan text-xs font-mono font-semibold rounded-xl flex items-center gap-1.5 transition-all disabled:opacity-50 cursor-pointer"
                >
                  <Search size={13} className={isSearching ? 'animate-spin' : ''} />
                  <span>SEARCH</span>
                </button>
              </form>

              {/* Search Results */}
              {searchResults && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-[10px] font-mono text-narad-textDim px-1">
                    <span>Matches for "{searchResults.query}"</span>
                    <span>{searchResults.count || 0} retrieved</span>
                  </div>

                  {searchResults.count === 0 ? (
                    <div className="py-8 text-center text-xs font-mono text-narad-textDim border border-narad-border/40 rounded-xl bg-narad-card/20">
                      No matching passages found in indexed documents.
                    </div>
                  ) : (
                    searchResults.results.map((item, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-xl bg-narad-card/40 border border-narad-border/60 space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="text-narad-cyan font-semibold flex items-center gap-1">
                            <FileText size={11} />
                            {item.document_name}
                          </span>
                          {item.relevance_score !== undefined && (
                            <span className="text-narad-textDim">
                              Rank: {item.relevance_score}
                            </span>
                          )}
                        </div>
                        <p className="text-xs font-sans text-slate-200 bg-narad-bg/60 p-2.5 rounded-lg border border-narad-border/30 whitespace-pre-wrap leading-relaxed">
                          {item.passage}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-narad-border bg-narad-card/30 flex items-center justify-between text-[10px] font-mono text-narad-textDim">
          <span>NARAD Krīya Tool: `search_knowledge` active</span>
          <span>Storage: `backend/data/knowledge_base/`</span>
        </div>
      </div>
    </div>
  );
}
