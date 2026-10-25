import React, { useState, useEffect, useRef } from 'react';
import {
  AlertTriangle,
  X,
  Trash2,
  RefreshCw,
  Film,
  FileText,
  Languages,
  Mic2,
  CheckCircle,
} from 'lucide-react';
import { api } from '../../services/api';

interface DeleteProjectModalProps {
  isOpen: boolean;
  project: { id: string; title: string } | null;
  onClose: () => void;
  onDeleted: (projectId: string) => void;
}

export const DeleteProjectModal: React.FC<DeleteProjectModalProps> = ({
  isOpen,
  project,
  onClose,
  onDeleted,
}) => {
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (project && isOpen) {
      setConfirmText('');
      setError(null);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [project, isOpen]);

  if (!isOpen || !project) return null;

  const isMatched = confirmText.trim() === project.title.trim();

  const handleDelete = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isMatched) return;

    try {
      setLoading(true);
      setError(null);
      await api.deleteProject(project.id);
      onDeleted(project.id);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to delete project. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="bg-white rounded-2xl shadow-2xl border border-rose-100 max-w-lg w-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4.5 bg-rose-50/60 border-b border-rose-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-rose-950">Delete Project</h3>
              <p className="text-xs text-rose-700/80 mt-0.5">Permanent & irreversible action</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-white/80 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleDelete} className="p-6 space-y-5">
          {/* Target Project Callout */}
          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Project to be deleted
            </div>
            <div className="text-sm font-bold text-slate-900 mt-1 break-words">
              {project.title}
            </div>
          </div>

          {/* Warning Checklist */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-700">
              The following resources and files will be permanently deleted:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-600 bg-rose-50/40 p-3 rounded-xl border border-rose-100">
              <div className="flex items-center gap-2">
                <Film className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Uploaded video & audio</span>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Whisper transcript segments</span>
              </div>
              <div className="flex items-center gap-2">
                <Languages className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Khmer translations</span>
              </div>
              <div className="flex items-center gap-2">
                <Mic2 className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Synthesized speech files</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Exported dubbed MP4 video</span>
              </div>
              <div className="flex items-center gap-2">
                <Trash2 className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>All database job records</span>
              </div>
            </div>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>Deletion Blocked</span>
              </div>
              <p className="pl-5 text-rose-600 leading-relaxed">{error}</p>
            </div>
          )}

          {/* Confirmation Input */}
          <div className="space-y-2">
            <label className="block text-xs font-semibold text-slate-700">
              To confirm, type <span className="font-bold text-slate-900 select-all">"{project.title}"</span> below:
            </label>
            <input
              ref={inputRef}
              type="text"
              value={confirmText}
              onChange={(e) => {
                setConfirmText(e.target.value);
                if (error) setError(null);
              }}
              disabled={loading}
              placeholder={project.title}
              className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-rose-500 focus:border-rose-500 transition-all text-slate-900"
            />
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !isMatched}
              className="inline-flex items-center gap-1.5 px-4.5 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl shadow-xs transition-all"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Deleting...</span>
                </>
              ) : (
                <>
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Permanently Delete Project</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
