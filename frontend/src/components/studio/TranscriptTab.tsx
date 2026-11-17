import React, { useState, useEffect, useMemo } from 'react';
import {
  FileText,
  Search,
  RefreshCw,
  Play,
  Edit2,
  Check,
  Clock,
  AlertCircle,
  Layers,
  AlertTriangle,
  X,
  Scissors,
  GitMerge,
  Sparkles,
  Users,
  Upload,
  Download,
  ChevronDown,
  FileUp,
  FileCheck,
  CheckCircle2,
} from 'lucide-react';
import { TranscriptSegment, SegmentationPreviewResponse, ProjectSpeaker } from '../../types';
import { api } from '../../services/api';

interface TranscriptTabProps {
  projectId: string;
  segmentationMode?: string;
  segments: TranscriptSegment[];
  speakers?: ProjectSpeaker[];
  isTranscribing: boolean;
  onStartTranscription: () => Promise<void>;
  onUpdateSegment: (segmentId: string, text: string) => Promise<void>;
  onUpdateSegmentSpeaker?: (segmentId: string, speakerLabel: string | null) => Promise<void>;
  onSeekVideo: (timestamp: number) => void;
  onResegmentSuccess?: () => Promise<void>;
  activeSegmentId?: string | null;
  selectedSegmentId?: string | null;
  transcriptionError?: string | null;
  isMediaReady: boolean;
}

export const TranscriptTab: React.FC<TranscriptTabProps> = ({
  projectId,
  segmentationMode = 'sentence',
  segments,
  speakers = [],
  isTranscribing,
  onStartTranscription,
  onUpdateSegment,
  onUpdateSegmentSpeaker,
  onSeekVideo,
  onResegmentSuccess,
  activeSegmentId,
  selectedSegmentId,
  transcriptionError,
  isMediaReady,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [savingId, setSavingId] = useState<string | null>(null);

  // Segmentation Mode & Preview Modal State
  const [currentMode, setCurrentMode] = useState<string>(segmentationMode);
  const [previewTargetMode, setPreviewTargetMode] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<SegmentationPreviewResponse | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);
  const [isApplyingSegmentation, setIsApplyingSegmentation] = useState<boolean>(false);
  const [segmentationError, setSegmentationError] = useState<string | null>(null);

  // Manual Split Modal / Prompt State
  const [splitTargetSeg, setSplitTargetSeg] = useState<TranscriptSegment | null>(null);
  const [splitWordIndex, setSplitWordIndex] = useState<number>(1);
  const [isSplitting, setIsSplitting] = useState<boolean>(false);
  const [isMerging, setIsMerging] = useState<string | null>(null);

  // Import & Export State
  const [showExportMenu, setShowExportMenu] = useState<boolean>(false);
  const [showImportModal, setShowImportModal] = useState<boolean>(false);
  const [importTab, setImportTab] = useState<'file' | 'text'>('file');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importRawText, setImportRawText] = useState<string>('');
  const [isImporting, setIsImporting] = useState<boolean>(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccessMsg, setImportSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (segmentationMode) {
      setCurrentMode(segmentationMode);
    }
  }, [segmentationMode]);

  const speakerNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const s of speakers) {
      map[s.speaker_label] = s.display_name;
    }
    return map;
  }, [speakers]);

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

  // Scroll matching segment into view when selected from timeline
  useEffect(() => {
    if (!selectedSegmentId) return;
    const el = document.getElementById(`transcript-seg-${selectedSegmentId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [selectedSegmentId]);

  // Prevent accidental loss of unsaved transcript edits on window/tab close
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (editingId && editText.trim() !== '') {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [editingId, editText]);

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
    const totalMs = Math.round(secs * 1000);
    const mins = Math.floor(totalMs / 60000);
    const s = Math.floor(totalMs / 1000) % 60;
    const ms = totalMs % 1000;
    return `${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  };

  // Mode Selection & Preview Handler
  const handleSelectMode = async (mode: string) => {
    if (mode === currentMode || isTranscribing || segments.length === 0) return;
    setPreviewTargetMode(mode);
    setIsPreviewLoading(true);
    setSegmentationError(null);
    try {
      const data = await api.previewTranscriptSegmentation(projectId, mode);
      setPreviewData(data);
    } catch (err: any) {
      setSegmentationError(err.message || 'Failed to generate segmentation preview');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleCancelPreview = () => {
    setPreviewTargetMode(null);
    setPreviewData(null);
    setSegmentationError(null);
  };

  const handleApplySegmentation = async () => {
    if (!previewTargetMode) return;
    try {
      setIsApplyingSegmentation(true);
      setSegmentationError(null);
      const res = await api.applyTranscriptSegmentation(projectId, previewTargetMode, true);
      setCurrentMode(res.segmentation_mode);
      handleCancelPreview();
      if (onResegmentSuccess) {
        await onResegmentSuccess();
      }
    } catch (err: any) {
      setSegmentationError(err.message || 'Failed to apply segmentation');
    } finally {
      setIsApplyingSegmentation(false);
    }
  };

  // Manual Split Handler
  const handleOpenSplit = (seg: TranscriptSegment) => {
    const words = seg.text.trim().split(/\s+/);
    setSplitTargetSeg(seg);
    setSplitWordIndex(Math.max(1, Math.floor(words.length / 2)));
  };

  const handleConfirmSplit = async () => {
    if (!splitTargetSeg) return;
    try {
      setIsSplitting(true);
      await api.splitTranscriptSegment(projectId, splitTargetSeg.id, splitWordIndex);
      setSplitTargetSeg(null);
      if (onResegmentSuccess) {
        await onResegmentSuccess();
      }
    } catch (err: any) {
      alert(`Failed to split segment: ${err.message}`);
    } finally {
      setIsSplitting(false);
    }
  };

  // Manual Merge Handler
  const handleMergeNext = async (seg: TranscriptSegment) => {
    if (!window.confirm(`Merge segment #${seg.segment_order} with segment #${seg.segment_order + 1}?`)) {
      return;
    }
    try {
      setIsMerging(seg.id);
      await api.mergeTranscriptSegmentNext(projectId, seg.id);
      if (onResegmentSuccess) {
        await onResegmentSuccess();
      }
    } catch (err: any) {
      alert(`Failed to merge segment: ${err.message}`);
    } finally {
      setIsMerging(null);
    }
  };

  // Quick Clone Voice from Segment Handler
  const [cloningSegId, setCloningSegId] = useState<string | null>(null);
  const [cloneSegNotification, setCloneSegNotification] = useState<string | null>(null);
  const [isAutoCloningSpeakers, setIsAutoCloningSpeakers] = useState(false);
  const [autoCloneSuccessMsg, setAutoCloneSuccessMsg] = useState<string | null>(null);

  const handleAutoCloneSpeakers = async () => {
    setIsAutoCloningSpeakers(true);
    setAutoCloneSuccessMsg(null);
    try {
      const res = await api.autoDetectAndCloneSpeakers(projectId, {
        min_speakers: 1,
        max_speakers: 6,
        store_in_voice_studio: false,
      });
      setAutoCloneSuccessMsg(`Detected ${res.speakers_detected} character(s) and cloned reference voices to speak Khmer!`);
      setTimeout(() => setAutoCloneSuccessMsg(null), 6000);
      if (onResegmentSuccess) {
        await onResegmentSuccess();
      }
    } catch (err: any) {
      alert(`Auto-detect & clone failed: ${err.message}`);
    } finally {
      setIsAutoCloningSpeakers(false);
    }
  };

  const handleCloneVoiceFromSegment = async (seg: TranscriptSegment) => {
    const dur = seg.end_time - seg.start_time;
    const voiceName = window.prompt(
      `Clone voice from Segment #${seg.segment_order} (${dur.toFixed(1)}s)?\n\nEnter a name for this cloned voice:`,
      `Segment #${seg.segment_order} Speaker`
    );
    if (!voiceName || !voiceName.trim()) return;

    try {
      setCloningSegId(seg.id);
      const profile = await api.cloneVoiceFromVideo(projectId, {
        segment_id: seg.id,
        voice_name: voiceName.trim(),
        set_as_project_voice: true,
      });
      setCloneSegNotification(`Voice "${profile.name}" cloned successfully and assigned as project default voice!`);
      setTimeout(() => setCloneSegNotification(null), 5000);
      if (onResegmentSuccess) {
        await onResegmentSuccess();
      }
    } catch (err: any) {
      alert(`Voice cloning failed: ${err.message}`);
    } finally {
      setCloningSegId(null);
    }
  };

  const handleExportTranscript = (format: string, mode: string = 'cues') => {
    setShowExportMenu(false);
    const url = api.getProjectTranscriptExportUrl(projectId, format, mode);
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleImportTranscript = async () => {
    setIsImporting(true);
    setImportError(null);
    try {
      let res;
      if (importTab === 'file') {
        if (!importFile) {
          setImportError('Please select a subtitle or transcript file (.srt, .vtt, .txt, .json).');
          setIsImporting(false);
          return;
        }
        res = await api.importProjectTranscript(projectId, importFile);
      } else {
        if (!importRawText.trim()) {
          setImportError('Please enter transcript text.');
          setIsImporting(false);
          return;
        }
        res = await api.importProjectTranscript(projectId, undefined, importRawText.trim());
      }
      setImportSuccessMsg(res.message || `Imported ${res.segment_count} segments successfully!`);
      setTimeout(() => {
        setShowImportModal(false);
        setImportFile(null);
        setImportRawText('');
        setImportSuccessMsg(null);
      }, 1200);
      if (onResegmentSuccess) {
        await onResegmentSuccess();
      }
    } catch (err: any) {
      setImportError(err.message || 'Failed to import transcript.');
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="space-y-6">
      {cloneSegNotification && (
        <div className="p-3.5 rounded-xl bg-purple-50 border border-purple-200 text-purple-700 text-xs flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-600 shrink-0" />
            <span className="font-medium">{cloneSegNotification}</span>
          </div>
          <button
            type="button"
            onClick={() => setCloneSegNotification(null)}
            className="text-purple-400 hover:text-purple-600 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {autoCloneSuccessMsg && (
        <div className="p-3.5 rounded-xl bg-purple-50 border border-purple-200 text-purple-700 text-xs flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-purple-600 shrink-0" />
            <span className="font-medium">{autoCloneSuccessMsg}</span>
          </div>
          <button
            type="button"
            onClick={() => setAutoCloneSuccessMsg(null)}
            className="text-purple-400 hover:text-purple-600 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Action, Search and Segmentation Control Toolbar */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                English Transcript (Speech-to-Text)
              </h3>
            </div>
            <p className="text-xs text-slate-500">
              Faster-Whisper neural model with word-level speech segmentation. Click timestamps to seek video.
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
                className="pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 w-44 sm:w-56"
              />
            </div>

            {/* Export Dropdown */}
            {segments.length > 0 && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowExportMenu(!showExportMenu)}
                  className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition flex items-center gap-1.5 shrink-0"
                  title="Export transcript as SRT, VTT, TXT, or JSON"
                >
                  <Download className="w-3.5 h-3.5 text-slate-600" />
                  <span>Export</span>
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                </button>
                {showExportMenu && (
                  <div
                    className="absolute right-0 mt-1 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-1.5 z-50 text-xs"
                    onMouseLeave={() => setShowExportMenu(false)}
                  >
                    <div className="px-3 py-1 text-[10px] font-bold text-indigo-600 uppercase tracking-wider bg-indigo-50/50">
                      For AI Translation (Grouped)
                    </div>
                    <button
                      onClick={() => handleExportTranscript('srt', 'dubbing_units')}
                      className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-600 flex items-center justify-between"
                      title="Optimized for ChatGPT/Claude: merges short broken fragments into full conversational sentences"
                    >
                      <span className="font-medium text-slate-800">AI Dubbing Units</span>
                      <span className="font-mono text-[10px] text-indigo-500 font-bold">.SRT</span>
                    </button>
                    <button
                      onClick={() => handleExportTranscript('json', 'dubbing_units')}
                      className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-600 flex items-center justify-between"
                    >
                      <span className="font-medium text-slate-800">AI Units with Timing</span>
                      <span className="font-mono text-[10px] text-indigo-500 font-bold">.JSON</span>
                    </button>

                    <div className="mt-1 px-3 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider border-t border-slate-100">
                      Original Subtitle Cues
                    </div>
                    <button
                      onClick={() => handleExportTranscript('srt', 'cues')}
                      className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-600 flex items-center justify-between"
                    >
                      <span>Subtitle Cues</span>
                      <span className="font-mono text-[10px] text-slate-400 font-bold">.SRT</span>
                    </button>
                    <button
                      onClick={() => handleExportTranscript('vtt', 'cues')}
                      className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-600 flex items-center justify-between"
                    >
                      <span>WebVTT</span>
                      <span className="font-mono text-[10px] text-slate-400 font-bold">.VTT</span>
                    </button>
                    <button
                      onClick={() => handleExportTranscript('txt', 'cues')}
                      className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-600 flex items-center justify-between"
                    >
                      <span>Plain Text</span>
                      <span className="font-mono text-[10px] text-slate-400 font-bold">.TXT</span>
                    </button>
                    <button
                      onClick={() => handleExportTranscript('json', 'cues')}
                      className="w-full text-left px-3 py-1.5 hover:bg-indigo-50 hover:text-indigo-600 flex items-center justify-between"
                    >
                      <span>Cues JSON</span>
                      <span className="font-mono text-[10px] text-slate-400 font-bold">.JSON</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Import Button */}
            <button
              type="button"
              onClick={() => {
                setShowImportModal(true);
                setImportError(null);
                setImportSuccessMsg(null);
              }}
              className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition flex items-center gap-1.5 shrink-0"
              title="Import transcript from SRT, VTT, TXT, or JSON file"
            >
              <Upload className="w-3.5 h-3.5 text-slate-600" />
              <span>Import</span>
            </button>

            {/* Auto-Clone Multi-Speaker Voices Button */}
            {segments.length > 0 && (
              <button
                type="button"
                onClick={handleAutoCloneSpeakers}
                disabled={isAutoCloningSpeakers || isTranscribing}
                className="px-3.5 py-2 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 text-xs font-semibold transition flex items-center gap-1.5 shrink-0 shadow-2xs"
                title="Auto-detect all speakers in this video and clone their voices to speak Khmer"
              >
                {isAutoCloningSpeakers ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-600" />
                    <span>Cloning Speakers...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                    <span>Auto-Clone Speakers</span>
                  </>
                )}
              </button>
            )}

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

        {/* Compact Segmentation Control */}
        {segments.length > 0 && (
          <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-semibold text-slate-600 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-indigo-600" />
                Segmentation:
              </span>
              <div className="inline-flex rounded-xl p-0.5 bg-slate-100 border border-slate-200 text-xs">
                <button
                  type="button"
                  onClick={() => handleSelectMode('original')}
                  className={`px-3 py-1 rounded-lg font-medium transition ${
                    currentMode === 'original'
                      ? 'bg-white text-indigo-700 shadow-sm font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Original
                </button>
                <button
                  type="button"
                  onClick={() => handleSelectMode('sentence')}
                  className={`px-3 py-1 rounded-lg font-medium transition ${
                    currentMode === 'sentence'
                      ? 'bg-white text-indigo-700 shadow-sm font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Sentence-Based
                </button>
                <button
                  type="button"
                  onClick={() => handleSelectMode('dubbing')}
                  className={`px-3 py-1 rounded-lg font-medium transition ${
                    currentMode === 'dubbing'
                      ? 'bg-white text-indigo-700 shadow-sm font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Dubbing-Optimized
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>
                Active Mode: <strong className="text-slate-800 font-semibold">{currentMode.toUpperCase()}</strong>
              </span>
              <span>•</span>
              <span>
                Total: <strong className="text-indigo-600 font-semibold">{segments.length}</strong> segments
              </span>
            </div>
          </div>
        )}
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
            Extracting word-level timestamps and segmenting spoken sentences.
          </p>
        </div>
      ) : segments.length === 0 ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <FileText className="w-10 h-10 text-slate-400 mx-auto" />
          <h4 className="text-sm font-bold text-slate-800">No Transcript Generated</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Click the "Start Transcription" button above to transcribe speech from the uploaded video.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-3">
            <button
              onClick={onStartTranscription}
              disabled={!isMediaReady || isTranscribing}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Start Transcription</span>
            </button>
            <button
              onClick={() => {
                setShowImportModal(true);
                setImportError(null);
                setImportSuccessMsg(null);
              }}
              className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition flex items-center gap-1.5"
            >
              <Upload className="w-3.5 h-3.5 text-slate-600" />
              <span>Or Import Subtitle File (.SRT / .VTT / .TXT / .JSON)</span>
            </button>
          </div>
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
            {filteredSegments.map((seg, idx) => {
              const isEditing = editingId === seg.id;
              const isSaving = savingId === seg.id;
              const isActive = activeSegmentId === seg.id;
              const isSelected = Boolean(selectedSegmentId) && selectedSegmentId === seg.id;
              const duration = (seg.end_time - seg.start_time).toFixed(2);
              const isLast = idx === filteredSegments.length - 1;

              return (
                <div
                  key={seg.id}
                  id={`transcript-seg-${seg.id}`}
                  className={`p-4 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-indigo-50/90 border-indigo-500 ring-2 ring-indigo-500/80 shadow-md'
                      : isActive
                      ? 'bg-indigo-50/70 border-indigo-300 ring-1 ring-indigo-400 shadow-sm'
                      : 'bg-white border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-mono font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                        #{seg.segment_order}
                      </span>

                      {speakers.length > 0 ? (
                        <div className="flex items-center gap-1">
                          <Users className="w-3.5 h-3.5 text-indigo-500" />
                          <select
                            aria-label={`Speaker for segment ${seg.segment_order}`}
                            value={seg.speaker_label || ''}
                            onChange={async (e) => {
                              const val = e.target.value ? e.target.value : null;
                              if (onUpdateSegmentSpeaker) {
                                await onUpdateSegmentSpeaker(seg.id, val);
                              }
                            }}
                            className="text-[11px] font-semibold bg-indigo-50/80 text-indigo-800 border border-indigo-200 rounded px-1.5 py-0.5 outline-hidden cursor-pointer hover:bg-indigo-100"
                          >
                            <option value="">Unassigned</option>
                            {speakers.map((s) => (
                              <option key={s.speaker_label} value={s.speaker_label}>
                                {s.display_name} ({s.detected_gender})
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : seg.speaker_label ? (
                        <span className="text-[10px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200 flex items-center gap-1">
                          <Users className="w-3 h-3" />
                          <span>{speakerNameMap[seg.speaker_label] || seg.speaker_label}</span>
                        </span>
                      ) : null}

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

                      {seg.is_approximate && (
                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                          Alignment review
                        </span>
                      )}
                      {seg.is_manually_edited && (
                        <span className="text-[10px] font-medium text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                          Edited
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1 self-end sm:self-auto">
                      <button
                        onClick={() => onSeekVideo(seg.start_time)}
                        className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition"
                        title="Play in Video"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>

                      {!isEditing ? (
                        <>
                          <button
                            onClick={() => handleStartEdit(seg)}
                            className="p-1 rounded text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
                            title="Edit Transcript Text"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>

                          <button
                            onClick={() => handleOpenSplit(seg)}
                            className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition"
                            title="Split Segment"
                          >
                            <Scissors className="w-3.5 h-3.5" />
                          </button>

                          <button
                            onClick={() => handleCloneVoiceFromSegment(seg)}
                            disabled={cloningSegId === seg.id}
                            className="p-1 rounded text-slate-400 hover:text-purple-600 hover:bg-purple-50 transition"
                            title="Clone voice from this segment"
                          >
                            {cloningSegId === seg.id ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin text-purple-600" />
                            ) : (
                              <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                            )}
                          </button>

                          {!isLast && (
                            <button
                              onClick={() => handleMergeNext(seg)}
                              disabled={isMerging === seg.id}
                              className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition disabled:opacity-40"
                              title="Merge with Next Segment"
                            >
                              <GitMerge className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </>
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
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                              e.preventDefault();
                              handleSaveEdit(seg.id);
                            } else if (e.key === 'Escape') {
                              handleCancelEdit();
                            }
                          }}
                          className="w-full text-xs sm:text-sm p-3 rounded-lg border border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                          rows={2}
                          autoFocus
                          placeholder="Edit English transcript..."
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

      {/* Segmentation Preview & Confirmation Modal */}
      {previewTargetMode && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full border border-slate-200 shadow-2xl flex flex-col max-h-[85vh] animate-in fade-in duration-200">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-100 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2.5">
                <Layers className="w-5 h-5 text-indigo-600" />
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Preview Segmentation:{' '}
                    <span className="text-indigo-600 capitalize">
                      {previewTargetMode === 'sentence'
                        ? 'Sentence-Based'
                        : previewTargetMode === 'dubbing'
                        ? 'Dubbing-Optimized'
                        : 'Original'}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500">
                    Review proposed segment boundaries before applying changes.
                  </p>
                </div>
              </div>
              <button
                onClick={handleCancelPreview}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4 flex-1">
              {isPreviewLoading ? (
                <div className="py-12 text-center space-y-2">
                  <RefreshCw className="w-6 h-6 text-indigo-600 animate-spin mx-auto" />
                  <p className="text-xs text-slate-600 font-medium">Calculating segment timestamps...</p>
                </div>
              ) : segmentationError ? (
                <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                  <span>{segmentationError}</span>
                </div>
              ) : previewData ? (
                <>
                  {/* Segment Count Summary */}
                  <div className="grid grid-cols-2 gap-3 p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                    <div>
                      <span className="text-slate-500 block">Current Segments</span>
                      <strong className="text-slate-800 text-sm font-bold">
                        {previewData.current_segment_count} segments
                      </strong>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Proposed Segments</span>
                      <strong className="text-indigo-600 text-sm font-bold">
                        {previewData.proposed_segment_count} segments
                      </strong>
                    </div>
                  </div>

                  {/* Impact Warning Banner */}
                  {previewData.requires_confirmation && (
                    <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-1">
                      <div className="flex items-center gap-2 font-semibold text-amber-800">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                        <span>Downstream Impact Warning</span>
                      </div>
                      <p className="leading-relaxed pl-6">
                        {previewData.impact_warning ||
                          'Applying this segmentation will mark existing translations and audio clips as outdated.'}
                      </p>
                    </div>
                  )}

                  {/* Proposed Segments List */}
                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-slate-700 block">
                      Proposed Segments Preview ({previewData.proposed_segments.length}):
                    </span>
                    <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                      {previewData.proposed_segments.map((seg) => (
                        <div
                          key={seg.segment_order}
                          className="p-3 rounded-lg border border-slate-200 bg-white text-xs space-y-1"
                        >
                          <div className="flex items-center justify-between text-slate-500 font-mono text-[11px]">
                            <span className="font-semibold text-indigo-700">#{seg.segment_order}</span>
                            <span>
                              {formatTimestamp(seg.start_time)} → {formatTimestamp(seg.end_time)} ({seg.duration}s)
                            </span>
                          </div>
                          <p className="text-slate-800 font-medium">{seg.text}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex items-center justify-end gap-2.5 shrink-0">
              <button
                type="button"
                onClick={handleCancelPreview}
                disabled={isApplyingSegmentation}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-200 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleApplySegmentation}
                disabled={isApplyingSegmentation || isPreviewLoading || !previewData}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center gap-1.5"
              >
                {isApplyingSegmentation ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Applying...</span>
                  </>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>Apply {previewTargetMode ? previewTargetMode.toUpperCase() : ''} Segmentation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Split Dialog Modal */}
      {splitTargetSeg && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full border border-slate-200 shadow-2xl p-5 space-y-4 animate-in fade-in duration-200">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Scissors className="w-4 h-4 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Split Segment #{splitTargetSeg.segment_order}
                </h3>
              </div>
              <button
                onClick={() => setSplitTargetSeg(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <p className="text-slate-600 font-medium bg-slate-50 p-3 rounded-lg border border-slate-200 leading-relaxed">
                "{splitTargetSeg.text}"
              </p>

              <div>
                <label className="block text-slate-600 font-semibold mb-1">
                  Split at Word Index (1 to {splitTargetSeg.text.trim().split(/\s+/).length - 1}):
                </label>
                <input
                  type="number"
                  min={1}
                  max={Math.max(1, splitTargetSeg.text.trim().split(/\s+/).length - 1)}
                  value={splitWordIndex}
                  onChange={(e) => setSplitWordIndex(parseInt(e.target.value) || 1)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-xs"
                />
              </div>

              {/* Split Preview */}
              <div className="p-3 rounded-lg bg-indigo-50/50 border border-indigo-100 space-y-1">
                <span className="font-semibold text-indigo-900">Preview Split:</span>
                <p className="text-slate-700">
                  Part 1:{' '}
                  <strong>
                    {splitTargetSeg.text.trim().split(/\s+/).slice(0, splitWordIndex).join(' ')}
                  </strong>
                </p>
                <p className="text-slate-700">
                  Part 2:{' '}
                  <strong>
                    {splitTargetSeg.text.trim().split(/\s+/).slice(splitWordIndex).join(' ')}
                  </strong>
                </p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                onClick={() => setSplitTargetSeg(null)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmSplit}
                disabled={isSplitting}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm flex items-center gap-1.5"
              >
                {isSplitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Splitting...</span>
                  </>
                ) : (
                  <>
                    <Scissors className="w-3.5 h-3.5" />
                    <span>Split Segment</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Transcript Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-xl w-full border border-slate-200 shadow-2xl p-6 space-y-5 animate-in fade-in duration-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-indigo-50 text-indigo-600 rounded-xl">
                  <Upload className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Import Source Transcript</h3>
                  <p className="text-xs text-slate-500">
                    Upload or paste subtitle cues (.srt, .vtt, .txt, .json) to populate transcript segments.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  if (!isImporting) setShowImportModal(false);
                }}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Error or Success banner */}
            {importError && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                <span>{importError}</span>
              </div>
            )}
            {importSuccessMsg && (
              <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
                <FileCheck className="w-4 h-4 shrink-0 text-emerald-600" />
                <span>{importSuccessMsg}</span>
              </div>
            )}

            {/* Tabs: Upload File vs Paste Text */}
            <div className="flex items-center gap-2 border-b border-slate-100 pb-2">
              <button
                type="button"
                onClick={() => setImportTab('file')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                  importTab === 'file'
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                <FileUp className="w-3.5 h-3.5" />
                <span>Upload File</span>
              </button>
              <button
                type="button"
                onClick={() => setImportTab('text')}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                  importTab === 'text'
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Paste Subtitle Text</span>
              </button>
            </div>

            {/* Tab 1: File Upload */}
            {importTab === 'file' && (
              <div className="space-y-3">
                <label className="border-2 border-dashed border-slate-200 hover:border-indigo-400 rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer bg-slate-50 hover:bg-indigo-50/30 transition text-center">
                  <Upload className="w-8 h-8 text-indigo-500 mb-2" />
                  <span className="text-xs font-semibold text-slate-700">
                    {importFile ? importFile.name : 'Click to select subtitle or transcript file'}
                  </span>
                  <span className="text-[11px] text-slate-400 mt-1">
                    Supports .SRT, .VTT, .TXT, .JSON (Max 25MB)
                  </span>
                  {importFile && (
                    <span className="text-[11px] text-emerald-600 font-medium mt-1">
                      {(importFile.size / 1024).toFixed(1)} KB selected
                    </span>
                  )}
                  <input
                    type="file"
                    accept=".srt,.vtt,.txt,.json,text/plain,application/json"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setImportFile(e.target.files[0]);
                        setImportError(null);
                      }
                    }}
                  />
                </label>
              </div>
            )}

            {/* Tab 2: Paste Raw Text */}
            {importTab === 'text' && (
              <div className="space-y-2">
                <label className="block text-xs font-medium text-slate-600">
                  Paste SRT, WebVTT, JSON, or line-separated text:
                </label>
                <textarea
                  value={importRawText}
                  onChange={(e) => {
                    setImportRawText(e.target.value);
                    setImportError(null);
                  }}
                  rows={8}
                  placeholder={`1\n00:00:01,000 --> 00:00:04,500\nHello, welcome to this video tutorial.\n\n2\n00:00:05,000 --> 00:00:08,200\nToday we will walk through the dubbing workflow.`}
                  className="w-full text-xs font-mono p-3 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-slate-50"
                />
              </div>
            )}

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-500 space-y-1">
              <span className="font-semibold text-slate-700 block">Note:</span>
              <p>
                Importing will replace any existing transcript cues and align with video timing. You can edit segments anytime afterwards.
              </p>
            </div>

            {/* Footer Buttons */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                disabled={isImporting}
                className="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleImportTranscript}
                disabled={isImporting || (importTab === 'file' ? !importFile : !importRawText.trim())}
                className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm flex items-center gap-2 transition"
              >
                {isImporting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Importing...</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    <span>Import Transcript</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
