import React, { useState, useMemo } from 'react';
import {
  FileText,
  Search,
  RefreshCw,
  Play,
  Edit2,
  Check,
  Clock,
  AlertCircle,
} from 'lucide-react';
import { TranscriptSegment } from '../../types';

interface TranscriptTabProps {
  segments: TranscriptSegment[];
  isTranscribing: boolean;
  onStartTranscription: () => Promise<void>;
  onUpdateSegment: (segmentId: string, text: string) => Promise<void>;
  onSeekVideo: (timestamp: number) => void;
  activeSegmentId?: string | null;
  transcriptionError?: string | null;
  isMediaReady: boolean;
}

export const TranscriptTab: React.FC<TranscriptTabProps> = ({
  segments,
  isTranscribing,
  onStartTranscription,
  onUpdateSegment,
  onSeekVideo,
  activeSegmentId,
  transcriptionError,
  isMediaReady,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [savingId, setSavingId] = useState<string | null>(null);

  const filteredSegments = useMemo(() => {
    if (!searchQuery.trim()) return segments;
    const q = searchQuery.toLowerCase().trim();
    return segments.filter((s) => s.text.toLowerCase().includes(q));
  }, [segments, searchQuery]);

  const handleStartEdit = (seg: TranscriptSegment) => {
    setEditingId(seg.id);
    setEditText(seg.text);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditText('');
  };

  const handleSaveEdit = async (segmentId: string) => {
    if (!editText.trim()) return;
    try {
      setSavingId(segmentId);
      await onUpdateSegment(segmentId, editText.trim());
      setEditingId(null);
      setEditText('');
    } catch (err: any) {
      alert(`Error updating segment: ${err.message}`);
    } finally {
      setSavingId(null);
    }
  };

  const formatTimestamp = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    const ms = Math.floor((secs % 1) * 1000);
    return `${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  };

  return (
    <div className="space-y-6">
      {/* Action and Search Toolbar */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-emerald-600" />
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
              English Transcript (Speech-to-Text)
            </h3>
          </div>
          <p className="text-xs text-slate-500">
            Faster-Whisper neural model with VAD speech segmentation. Click timestamps to seek video.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search transcript..."
              className="pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 w-48 sm:w-60"
            />
          </div>

          <button
            onClick={onStartTranscription}
            disabled={!isMediaReady || isTranscribing}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5 shrink-0"
          >
            {isTranscribing ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Transcribing...</span>
              </>
            ) : segments.length > 0 ? (
              <>
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retranscribe All</span>
              </>
            ) : (
              <>
                <FileText className="w-3.5 h-3.5" />
                <span>Start Transcription</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error alert */}
      {transcriptionError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{transcriptionError}</span>
          </div>
          <button
            onClick={onStartTranscription}
            className="px-3 py-1 rounded bg-rose-600 text-white font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading view */}
      {isTranscribing ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
          <h4 className="text-sm font-bold text-slate-800">Transcribing Speech with Faster-Whisper...</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Extracting Voice Activity Detection (VAD) audio chunks and generating timestamped English transcript segments.
          </p>
        </div>
      ) : segments.length === 0 ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <FileText className="w-10 h-10 text-slate-400 mx-auto" />
          <h4 className="text-sm font-bold text-slate-800">No Transcript Generated</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Click the "Start Transcription" button above to transcribe speech from the uploaded video.
          </p>
        </div>
      ) : (
        /* Segment List */
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <span>
              Total Segments: <strong className="text-slate-800 font-semibold">{segments.length}</strong>
              {searchQuery && ` (filtered: ${filteredSegments.length})`}
            </span>
            <span className="hidden sm:inline">Click timestamp or play button to seek video player</span>
          </div>

          <div className="space-y-2.5">
            {filteredSegments.map((seg) => {
              const isEditing = editingId === seg.id;
              const isSaving = savingId === seg.id;
              const isActive = activeSegmentId === seg.id;
              const duration = (seg.end_time - seg.start_time).toFixed(2);

              return (
                <div
                  key={seg.id}
                  className={`p-4 rounded-xl border transition-all ${
                    isActive
                      ? 'bg-indigo-50/70 border-indigo-300 ring-1 ring-indigo-400 shadow-sm'
                      : 'bg-white border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                        #{seg.segment_order}
                      </span>
                      <button
                        onClick={() => onSeekVideo(seg.start_time)}
                        className="text-xs font-mono text-slate-600 hover:text-indigo-600 flex items-center gap-1 font-semibold group"
                        title="Seek video to this segment"
                      >
                        <Clock className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600" />
                        <span>
                          {formatTimestamp(seg.start_time)} → {formatTimestamp(seg.end_time)}
                        </span>
                        <span className="text-[10px] text-slate-400 font-normal">({duration}s)</span>
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5 self-end sm:self-auto">
                      <button
                        onClick={() => onSeekVideo(seg.start_time)}
                        className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition"
                        title="Play in Video"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>

                      {!isEditing ? (
                        <button
                          onClick={() => handleStartEdit(seg)}
                          className="p-1 rounded text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
                          title="Edit Transcript Text"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                      ) : null}
                    </div>
                  </div>

                  {/* Text Content / Inline Edit */}
                  <div className="pt-2.5">
                    {isEditing ? (
                      <div className="space-y-2">
                        <textarea
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          className="w-full text-xs sm:text-sm p-3 rounded-lg border border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                          rows={2}
                          autoFocus
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={handleCancelEdit}
                            className="px-3 py-1 rounded text-xs text-slate-500 hover:bg-slate-100"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSaveEdit(seg.id)}
                            disabled={isSaving || !editText.trim()}
                            className="px-3.5 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1 shadow-sm"
                          >
                            <Check className="w-3 h-3" />
                            {isSaving ? 'Saving...' : 'Save'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs sm:text-sm text-slate-800 font-medium leading-relaxed">
                        {seg.text}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
