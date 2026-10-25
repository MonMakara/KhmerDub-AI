import React, { useEffect, useRef } from 'react';
import {
  AlertTriangle,
  X,
  Trash2,
  RefreshCw,
  FileAudio,
  FileText,
  Languages,
  Archive,
  Layers,
  Calendar,
} from 'lucide-react';
import { ToolkitTask } from '../../types';

interface DeleteToolkitTaskModalProps {
  isOpen: boolean;
  task: ToolkitTask | null;
  dependentCount?: number;
  loading?: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void> | void;
}

export const DeleteToolkitTaskModal: React.FC<DeleteToolkitTaskModalProps> = ({
  isOpen,
  task,
  dependentCount = 0,
  loading = false,
  onClose,
  onConfirm,
}) => {
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, loading, onClose]);

  // Autofocus Cancel button on modal open for safety
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        cancelButtonRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  if (!isOpen || !task) return null;

  const getToolDisplayName = (toolType: string): string => {
    switch (toolType) {
      case 'video_to_audio':
        return 'Video to Audio';
      case 'video_to_transcript':
        return 'Video to Transcript';
      case 'video_to_text':
        return 'Video to Text';
      case 'audio_to_transcript':
        return 'Audio to Transcript';
      case 'audio_to_text':
        return 'Audio to Text';
      case 'text_to_speech':
        return 'Text-to-Speech Studio';
      case 'transcript_to_audio':
        return 'Transcript to Audio';
      case 'standalone_translation':
        return 'Translation Studio (Plain Text)';
      case 'transcript_translation':
        return 'Translation Studio (Transcript)';
      case 'subtitle_converter':
        return 'Subtitle Converter';
      default:
        return toolType.replace(/_/g, ' ').toUpperCase();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150 select-none"
      onClick={!loading ? onClose : undefined}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-toolkit-modal-title"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-rose-100 max-w-lg w-full overflow-hidden text-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4.5 bg-rose-50/70 border-b border-rose-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 id="delete-toolkit-modal-title" className="font-bold text-base text-rose-950">
                Delete Toolkit Task
              </h3>
              <p className="text-xs text-rose-700/80 mt-0.5">Permanent & irreversible action</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-white/80 transition-colors disabled:opacity-40"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 space-y-4">
          {/* Target Task Details Box */}
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200/80 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Toolkit Item to be Deleted
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100">
                {getToolDisplayName(task.tool_type)}
              </span>
            </div>

            <div className="text-sm font-bold text-slate-900 break-words flex items-center gap-2">
              <span className="truncate">{task.source_filename || 'Standalone Task'}</span>
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 shrink-0">
                {task.target_format}
              </span>
            </div>

            <div className="flex items-center gap-3 text-xs text-slate-500 pt-1 border-t border-slate-200/60">
              <span className="flex items-center gap-1 text-[11px]">
                <Calendar className="w-3 h-3 text-slate-400" />
                {new Date(task.created_at).toLocaleString()}
              </span>
              <span>•</span>
              <span className="capitalize text-[11px] font-medium text-slate-600">
                Status: {task.status}
              </span>
            </div>
          </div>

          {/* Lineage Dependency Notice (if downstream tasks exist) */}
          {dependentCount > 0 && (
            <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 space-y-1 text-xs">
              <div className="font-bold flex items-center gap-1.5 text-amber-800">
                <Layers className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Lineage Warning</span>
              </div>
              <p className="leading-relaxed text-amber-800/90 pl-5">
                This item has <strong>{dependentCount}</strong> downstream derived task(s) (e.g. translated transcripts or audio narrations). Deleting this source item will preserve your derived tasks, but disconnect the lineage connection.
              </p>
            </div>
          )}

          {/* Resources Checklist */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-700">
              The following files and resources will be permanently removed:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-600 bg-rose-50/40 p-3 rounded-xl border border-rose-100">
              <div className="flex items-center gap-2">
                <FileAudio className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Audio/Video media outputs</span>
              </div>
              <div className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Speech segments & timestamps</span>
              </div>
              <div className="flex items-center gap-2">
                <Languages className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Translations & subtitle cues</span>
              </div>
              <div className="flex items-center gap-2">
                <Archive className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Task history & ZIP bundles</span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-100">
            <button
              ref={cancelButtonRef}
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-4.5 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl shadow-xs transition-all cursor-pointer"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Deleting...</span>
                </>
              ) : (
                <>
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Delete Task</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
