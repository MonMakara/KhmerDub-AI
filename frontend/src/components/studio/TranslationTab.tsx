import React, { useState, useMemo } from 'react';
import {
  Languages,
  Search,
  RefreshCw,
  Sparkles,
  Layers,
  Edit2,
  Check,
  Play,
  AlertTriangle,
  Clock,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import {
  TranslationSegment,
  TranscriptSegment,
  GeneratedAudio,
  TimingConflict,
  TranslationProviderInfo,
} from '../../types';
import { AIImproveModal } from './AIImproveModal';

interface TranslationTabProps {
  projectId: string;
  translationSegments: TranslationSegment[];
  transcriptSegments: TranscriptSegment[];
  generatedAudios: GeneratedAudio[];
  timingConflicts: TimingConflict[];
  providers: TranslationProviderInfo[];
  selectedProvider: string;
  selectedStyle: string;
  isTranslating: boolean;
  onUpdateTranslationSettings: (provider: string, style: string) => Promise<void>;
  onStartTranslation: () => Promise<void>;
  onUpdateSegment: (segmentId: string, khmerText: string) => Promise<void>;
  onRetranslateSegment: (segmentId: string) => Promise<void>;
  onApplyAIImprovement: (segmentId: string, khmerText: string, style?: string, explanation?: string) => Promise<void>;
  onSeekVideo: (timestamp: number) => void;
  activeSegmentId?: string | null;
  translationError?: string | null;
  isTranscriptReady: boolean;
}

export const TranslationTab: React.FC<TranslationTabProps> = ({
  projectId,
  translationSegments,
  transcriptSegments,
  generatedAudios,
  timingConflicts,
  providers,
  selectedProvider,
  selectedStyle,
  isTranslating,
  onUpdateTranslationSettings,
  onStartTranslation,
  onUpdateSegment,
  onRetranslateSegment,
  onApplyAIImprovement,
  onSeekVideo,
  activeSegmentId,
  translationError,
  isTranscriptReady,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [savingId, setSavingId] = useState<string | null>(null);
  const [retranslatingId, setRetranslatingId] = useState<string | null>(null);

  // Modal states
  const [modalSegment, setModalSegment] = useState<TranslationSegment | null>(null);
  const [modalMode, setModalMode] = useState<'improve' | 'alternatives'>('improve');

  // Conflict lookup by segment_order
  const conflictMap = useMemo(() => {
    const map = new Map<number, TimingConflict>();
    timingConflicts.forEach((c) => map.set(c.segment_order, c));
    return map;
  }, [timingConflicts]);

  // Audio lookup by translation_segment_id
  const audioMap = useMemo(() => {
    const map = new Map<string, GeneratedAudio>();
    generatedAudios.forEach((a) => {
      if (a.translation_segment_id) {
        map.set(a.translation_segment_id, a);
      }
    });
    return map;
  }, [generatedAudios]);

  // Transcript lookup by ID
  const transcriptMap = useMemo(() => {
    const map = new Map<string, TranscriptSegment>();
    transcriptSegments.forEach((t) => map.set(t.id, t));
    return map;
  }, [transcriptSegments]);

  // Filtered segments
  const filteredSegments = useMemo(() => {
    if (!searchQuery.trim()) return translationSegments;
    const q = searchQuery.toLowerCase().trim();
    return translationSegments.filter(
      (s) =>
        s.khmer_text.toLowerCase().includes(q) ||
        (s.english_text && s.english_text.toLowerCase().includes(q))
    );
  }, [translationSegments, searchQuery]);

  const handleStartEdit = (seg: TranslationSegment) => {
    setEditingId(seg.id);
    setEditText(seg.khmer_text);
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
      alert(`Error saving translation: ${err.message}`);
    } finally {
      setSavingId(null);
    }
  };

  const handleRetranslate = async (segmentId: string) => {
    try {
      setRetranslateLoading(segmentId, true);
      await onRetranslateSegment(segmentId);
    } catch (err: any) {
      alert(`Retranslation failed: ${err.message}`);
    } finally {
      setRetranslateLoading(segmentId, false);
    }
  };

  const setRetranslateLoading = (id: string, val: boolean) => {
    setRetranslatingId(val ? id : null);
  };

  const openAIModal = (seg: TranslationSegment, mode: 'improve' | 'alternatives') => {
    setModalSegment(seg);
    setModalMode(mode);
  };

  const formatTimestamp = (secs?: number | null) => {
    if (secs === undefined || secs === null) return '00:00.000';
    const mins = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    const ms = Math.floor((secs % 1) * 1000);
    return `${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  };

  const activeProvider = providers.find((p) => p.id === selectedProvider);

  return (
    <div className="space-y-6">
      {/* Top Toolbar: Provider, Style, Actions, Search */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-3 border-b border-slate-100">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Languages className="w-5 h-5 text-purple-600" />
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Bilingual Khmer Translation Studio
              </h3>
            </div>
            <p className="text-xs text-slate-500">
              Comparative English & Khmer translation editor. Refine timing and style with AI.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Provider Selector */}
            <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 px-2.5 py-1.5 rounded-xl text-xs">
              <span className="font-semibold text-slate-500 uppercase text-[10px]">Provider:</span>
              <select
                value={selectedProvider}
                onChange={(e) => onUpdateTranslationSettings(e.target.value, selectedStyle)}
                disabled={isTranslating}
                className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
              >
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.type === 'local' ? '(Local Free)' : p.is_configured ? '(Ready)' : '(Key Needed)'}
                  </option>
                ))}
              </select>
            </div>

            {/* Style Selector */}
            <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 px-2.5 py-1.5 rounded-xl text-xs">
              <span className="font-semibold text-slate-500 uppercase text-[10px]">Style:</span>
              <select
                value={selectedStyle}
                onChange={(e) => onUpdateTranslationSettings(selectedProvider, e.target.value)}
                disabled={isTranslating}
                className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
              >
                <option value="natural">Natural Spoken (Default)</option>
                <option value="short">Short for Video Dubbing</option>
                <option value="simple">Simple & Clear Words</option>
                <option value="formal">Formal / Professional</option>
                <option value="standard">Standard / Faithful</option>
              </select>
            </div>

            {/* Translate Button */}
            <button
              onClick={onStartTranslation}
              disabled={!isTranscriptReady || isTranslating}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5 shrink-0"
            >
              {isTranslating ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Translating...</span>
                </>
              ) : translationSegments.length > 0 ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retranslate All</span>
                </>
              ) : (
                <>
                  <Languages className="w-3.5 h-3.5" />
                  <span>Translate to Khmer</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Second Row: Provider Status Reminder & Search Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            {selectedProvider !== 'nllb' ? (
              activeProvider?.is_configured ? (
                <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200 font-medium text-[11px]">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                  {activeProvider.name} is configured and ready
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-amber-800 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200 font-medium text-[11px]">
                  <AlertCircle className="w-3 h-3 text-amber-600" />
                  {activeProvider?.name || selectedProvider} API key missing. Configure in Settings.
                </span>
              )
            ) : (
              <span className="inline-flex items-center gap-1 text-slate-700 bg-slate-100 px-2.5 py-1 rounded-lg font-medium text-[11px]">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Meta NLLB-200 offline CPU translation (zero cost)
              </span>
            )}
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search English or Khmer text..."
              className="pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 w-full sm:w-64"
            />
          </div>
        </div>
      </div>

      {/* Error banner */}
      {translationError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{translationError}</span>
          </div>
          <button
            onClick={onStartTranslation}
            className="px-3 py-1 rounded bg-rose-600 text-white font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {isTranslating ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
          <h4 className="text-sm font-bold text-slate-800">
            Translating with {activeProvider?.name || 'AI Model'}...
          </h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Applying terminology glossary alignment, dubbing timing rules, and scriptio continua spacing compaction.
          </p>
        </div>
      ) : translationSegments.length === 0 ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <Languages className="w-10 h-10 text-slate-400 mx-auto" />
          <h4 className="text-sm font-bold text-slate-800">No Khmer Translations Yet</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Click "Translate to Khmer" above to translate the English transcript using Meta NLLB-200 or Google Gemini.
          </p>
        </div>
      ) : (
        /* Bilingual Segment Cards List */
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <span>
              Total Segments: <strong className="text-slate-800 font-semibold">{translationSegments.length}</strong>
              {searchQuery && ` (filtered: ${filteredSegments.length})`}
            </span>
            <span className="hidden sm:inline">Side-by-side comparative review with 1-click AI improvement</span>
          </div>

          <div className="space-y-3">
            {filteredSegments.map((seg) => {
              const transcriptSeg = seg.transcript_segment_id ? transcriptMap.get(seg.transcript_segment_id) : null;
              const startTime = seg.start_time ?? transcriptSeg?.start_time ?? 0;
              const endTime = seg.end_time ?? transcriptSeg?.end_time ?? 0;
              const availableDuration = endTime > startTime ? endTime - startTime : 0;

              const audio = audioMap.get(seg.id);
              const conflict = conflictMap.get(seg.segment_order);
              const isEditing = editingId === seg.id;
              const isSaving = savingId === seg.id;
              const isRetranslating = retranslatingId === seg.id;
              const isActive = activeSegmentId === seg.id;

              return (
                <div
                  key={seg.id}
                  className={`p-4 rounded-xl border transition-all ${
                    isActive
                      ? 'bg-indigo-50/70 border-indigo-300 ring-1 ring-indigo-400 shadow-sm'
                      : conflict
                      ? 'bg-amber-50/30 border-amber-300'
                      : 'bg-white border-slate-200 hover:border-slate-300'
                  }`}
                >
                  {/* Segment Header */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-mono font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                        #{seg.segment_order}
                      </span>

                      <button
                        onClick={() => onSeekVideo(startTime)}
                        className="text-xs font-mono text-slate-600 hover:text-indigo-600 flex items-center gap-1 font-semibold group"
                        title="Seek video to this timestamp"
                      >
                        <Clock className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600" />
                        <span>
                          {formatTimestamp(startTime)} → {formatTimestamp(endTime)}
                        </span>
                        <span className="text-[10px] text-slate-400 font-normal">
                          (~{availableDuration.toFixed(2)}s)
                        </span>
                      </button>

                      {seg.is_manually_edited && (
                        <span className="text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-medium border border-slate-200">
                          Manually Edited
                        </span>
                      )}

                      {seg.style && (
                        <span className="text-[10px] bg-purple-100 text-purple-800 px-1.5 py-0.5 rounded font-medium capitalize">
                          {seg.style}
                        </span>
                      )}

                      {/* Timing Warning Badge */}
                      {conflict && (
                        <span className="text-[10px] bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full font-bold flex items-center gap-1 animate-pulse">
                          <AlertTriangle className="w-3 h-3 text-amber-600" />
                          Speech exceeds window (+{conflict.overflow_seconds.toFixed(2)}s)
                        </span>
                      )}
                    </div>

                    {/* Action Bar */}
                    <div className="flex items-center gap-1 self-end sm:self-auto">
                      {/* Play in video */}
                      <button
                        onClick={() => onSeekVideo(startTime)}
                        className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition"
                        title="Play in Video"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>

                      {/* AI Improve */}
                      <button
                        onClick={() => openAIModal(seg, 'improve')}
                        className="px-2 py-1 rounded bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold flex items-center gap-1 transition"
                        title="Refine translation with AI"
                      >
                        <Sparkles className="w-3 h-3 text-indigo-600" />
                        <span>AI Improve</span>
                      </button>

                      {/* 3 Alternatives */}
                      <button
                        onClick={() => openAIModal(seg, 'alternatives')}
                        className="px-2 py-1 rounded bg-purple-50 hover:bg-purple-100 text-purple-700 text-xs font-semibold flex items-center gap-1 transition"
                        title="View 3 translation alternatives"
                      >
                        <Layers className="w-3 h-3 text-purple-600" />
                        <span className="hidden sm:inline">Alternatives</span>
                      </button>

                      {/* Retranslate Segment */}
                      <button
                        onClick={() => handleRetranslate(seg.id)}
                        disabled={isRetranslating}
                        className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                        title="Retranslate this segment"
                      >
                        <RotateCcw className={`w-3.5 h-3.5 ${isRetranslating ? 'animate-spin' : ''}`} />
                      </button>

                      {/* Edit Segment */}
                      {!isEditing && (
                        <button
                          onClick={() => handleStartEdit(seg)}
                          className="p-1 rounded text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
                          title="Edit Khmer text"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Bilingual Side-by-Side Content */}
                  <div className="pt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Left: Original English */}
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                        Original English
                      </span>
                      <p className="text-slate-700 font-medium leading-relaxed">
                        {seg.english_text || transcriptSeg?.text || 'N/A'}
                      </p>
                    </div>

                    {/* Right: Khmer Translation & Audio */}
                    <div className="p-3 rounded-lg bg-indigo-50/30 border border-indigo-100 text-xs space-y-2">
                      <div className="flex items-center justify-between text-[10px] font-semibold text-indigo-900 uppercase tracking-wider">
                        <span>Khmer Dubbing Translation</span>
                        {audio && (
                          <span className="text-[10px] font-mono font-normal text-slate-500">
                            Audio: {audio.duration_seconds?.toFixed(2)}s
                          </span>
                        )}
                      </div>

                      {isEditing ? (
                        <div className="space-y-2">
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            className="w-full text-xs sm:text-sm font-khmer p-2.5 rounded-lg border border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                            rows={3}
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
                        <p className="font-khmer text-sm text-slate-900 font-semibold leading-relaxed">
                          {seg.khmer_text}
                        </p>
                      )}

                      {/* Segment Audio Player (if synthesized) */}
                      {audio && (
                        <div className="pt-1 flex items-center justify-between border-t border-indigo-100/60">
                          <audio
                            controls
                            src={`/api/tts/stream/${audio.id}`}
                            className="w-full max-w-xs h-7"
                          />
                          {audio.is_outdated && (
                            <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-medium">
                              Audio Outdated
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Refinement & Alternatives Modal */}
      {modalSegment && (
        <AIImproveModal
          segment={modalSegment}
          projectId={projectId}
          onClose={() => setModalSegment(null)}
          onApply={async (text, style, explanation) => {
            await onApplyAIImprovement(modalSegment.id, text, style, explanation);
            setModalSegment(null);
          }}
          targetDuration={
            modalSegment.end_time && modalSegment.start_time
              ? modalSegment.end_time - modalSegment.start_time
              : undefined
          }
          activeProviderId={selectedProvider}
          providers={providers}
          initialMode={modalMode}
        />
      )}
    </div>
  );
};
