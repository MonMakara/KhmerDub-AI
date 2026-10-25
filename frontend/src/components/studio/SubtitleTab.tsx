import React, { useState, useMemo, useEffect } from 'react';
import {
  Subtitles,
  Download,
  RotateCcw,
  Search,
  Clock,
  Play,
  Edit2,
  Check,
  Sliders,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  Zap,
  Scissors,
  Link2,
  ChevronDown,
  RefreshCw,
} from 'lucide-react';
import {
  SubtitleSegment,
  SubtitleStylePreferences,
} from '../../types';
import { api } from '../../services/api';

interface SubtitleTabProps {
  projectId: string;
  subtitles: SubtitleSegment[];
  currentLanguage: 'km' | 'en';
  onLanguageChange: (lang: 'km' | 'en') => void;
  onRefreshSubtitles: () => Promise<void>;
  onSeekVideo: (timeInSeconds: number) => void;
  activeSegmentId?: string | null;
  selectedSegmentId?: string | null;
  subtitleStyles: SubtitleStylePreferences;
  onUpdateStyles: (styles: SubtitleStylePreferences) => void;
}

export const SubtitleTab: React.FC<SubtitleTabProps> = ({
  projectId,
  subtitles,
  currentLanguage,
  onLanguageChange,
  onRefreshSubtitles,
  onSeekVideo,
  activeSegmentId,
  selectedSegmentId,
  subtitleStyles,
  onUpdateStyles,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [editingOrder, setEditingOrder] = useState<number | null>(null);
  const [editText, setEditText] = useState<string>('');
  const [editStartTime, setEditStartTime] = useState<number>(0);
  const [editEndTime, setEditEndTime] = useState<number>(1);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [isSplitting, setIsSplitting] = useState<boolean>(false);
  const [showStyleSettings, setShowStyleSettings] = useState<boolean>(false);
  const [showSplitSettings, setShowSplitSettings] = useState<boolean>(false);
  const [maxCharsThreshold, setMaxCharsThreshold] = useState<number>(75);
  const [maxDurationThreshold, setMaxDurationThreshold] = useState<number>(6.5);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Smooth scroll matching segment into view
  useEffect(() => {
    if (!selectedSegmentId && !activeSegmentId) return;
    const targetOrder = selectedSegmentId || activeSegmentId;
    const el = document.getElementById(`sub-seg-${targetOrder}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [selectedSegmentId, activeSegmentId]);

  // Filtered subtitle segments
  const filteredSegments = useMemo(() => {
    if (!searchQuery.trim()) return subtitles;
    const q = searchQuery.toLowerCase();
    return subtitles.filter(
      (s) =>
        s.text.toLowerCase().includes(q) ||
        (s.source_text && s.source_text.toLowerCase().includes(q)) ||
        s.segment_order.toString() === q
    );
  }, [subtitles, searchQuery]);

  // Format seconds into SRT timestamp
  const formatSrtTime = (seconds: number): string => {
    const totalMs = Math.round(seconds * 1000);
    const ms = totalMs % 1000;
    const totalSec = Math.floor(totalMs / 1000);
    const s = totalSec % 60;
    const totalMin = Math.floor(totalSec / 60);
    const m = totalMin % 60;
    const h = Math.floor(totalMin / 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
  };

  const handleStartEdit = (seg: SubtitleSegment) => {
    setEditingOrder(seg.segment_order);
    setEditText(seg.text);
    setEditStartTime(seg.start_time);
    setEditEndTime(seg.end_time);
    setStatusMessage(null);
    setErrorMessage(null);
  };

  const handleCancelEdit = () => {
    setEditingOrder(null);
    setEditText('');
  };

  const handleSaveEdit = async (segmentOrder: number) => {
    try {
      setIsSaving(true);
      setErrorMessage(null);

      if (editStartTime < 0) {
        throw new Error('Start time cannot be negative.');
      }
      if (editEndTime <= editStartTime) {
        throw new Error('End time must be greater than start time.');
      }

      await api.updateSubtitleSegment(projectId, segmentOrder, {
        text: editText,
        start_time: editStartTime,
        end_time: editEndTime,
        language: currentLanguage,
      });

      await onRefreshSubtitles();
      setEditingOrder(null);
      setStatusMessage(`Subtitle cue #${segmentOrder} updated successfully.`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to save subtitle edit.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleAutoSplit = async () => {
    try {
      setIsSplitting(true);
      setErrorMessage(null);
      const res = await api.autoSplitSubtitles(
        projectId,
        currentLanguage,
        maxCharsThreshold,
        maxDurationThreshold
      );
      await onRefreshSubtitles();
      setStatusMessage(`Auto-split complete! Subtitles now segmented into ${res.total_segments} readable cues.`);
      setTimeout(() => setStatusMessage(null), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to auto-split subtitles.');
    } finally {
      setIsSplitting(false);
    }
  };

  const handleManualSplit = async (segmentOrder: number) => {
    try {
      setIsSplitting(true);
      setErrorMessage(null);
      const res = await api.splitSubtitleCue(projectId, segmentOrder, currentLanguage, undefined, 0.5);
      await onRefreshSubtitles();
      setStatusMessage(`Cue #${segmentOrder} split into two cues. Total: ${res.total_segments} cues.`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to split subtitle cue.');
    } finally {
      setIsSplitting(false);
    }
  };

  const handleMergeWithNext = async (segmentOrder: number) => {
    try {
      setIsSplitting(true);
      setErrorMessage(null);
      const res = await api.mergeSubtitleCue(projectId, segmentOrder, currentLanguage);
      await onRefreshSubtitles();
      setStatusMessage(`Cue #${segmentOrder} merged with next cue. Total: ${res.total_segments} cues.`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to merge subtitle cue.');
    } finally {
      setIsSplitting(false);
    }
  };

  const handleKeepEdits = async (segmentOrder: number) => {
    try {
      setErrorMessage(null);
      await api.keepSubtitleEdits(projectId, segmentOrder, currentLanguage);
      await onRefreshSubtitles();
      setStatusMessage(`Preserved custom text for cue #${segmentOrder}. Outdated warning cleared.`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to keep subtitle edits.');
    }
  };

  const handleResetSingleCue = async (segmentOrder: number) => {
    try {
      setErrorMessage(null);
      await api.resetSubtitleCue(projectId, segmentOrder, currentLanguage);
      await onRefreshSubtitles();
      setStatusMessage(`Cue #${segmentOrder} reset to source translation text.`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to reset subtitle cue.');
    }
  };

  const handleResetSubtitles = async () => {
    const langLabel = currentLanguage === 'km' ? 'Khmer' : 'English';
    if (!window.confirm(`Reset all ${langLabel} subtitle customizations back to original source text?`)) {
      return;
    }
    try {
      setIsResetting(true);
      setErrorMessage(null);
      const res = await api.resetSubtitles(projectId, currentLanguage);
      await onRefreshSubtitles();
      setStatusMessage(res.message);
      setTimeout(() => setStatusMessage(null), 3500);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to reset subtitles.');
    } finally {
      setIsResetting(false);
    }
  };

  const handleApplyPreset = (preset: 'standard' | 'cinema' | 'custom') => {
    if (preset === 'cinema') {
      onUpdateStyles({
        preset: 'cinema',
        fontSize: 'lg',
        textColor: 'yellow',
        position: 'bottom',
        bgOpacity: 0,
        bottomMargin: 14,
        shadow: true,
      });
    } else if (preset === 'standard') {
      onUpdateStyles({
        preset: 'standard',
        fontSize: 'base',
        textColor: 'white',
        position: 'bottom',
        bgOpacity: 0.75,
        bottomMargin: 12,
        shadow: false,
      });
    } else {
      onUpdateStyles({
        ...subtitleStyles,
        preset: 'custom',
      });
    }
  };

  const hasCustomEdits = useMemo(() => {
    return subtitles.some((s) => s.is_customized);
  }, [subtitles]);

  const hasLongCues = useMemo(() => {
    return subtitles.some(
      (s) => s.text.length > maxCharsThreshold || (s.end_time - s.start_time) > maxDurationThreshold
    );
  }, [subtitles, maxCharsThreshold, maxDurationThreshold]);

  return (
    <div className="space-y-6">
      {/* Top Banner: Stage Header, Language Switcher, Export Buttons */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100">
              <Subtitles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Subtitle Readability & Synchronization</h2>
              <p className="text-xs text-slate-500">
                Segment paragraphs into readable caption cues, adjust timings, and export standard SRT & WebVTT.
              </p>
            </div>
          </div>

          {/* Language Toggle */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl self-start md:self-auto border border-slate-200">
            <button
              onClick={() => onLanguageChange('km')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                currentLanguage === 'km'
                  ? 'bg-white text-indigo-700 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Khmer (KM)
            </button>
            <button
              onClick={() => onLanguageChange('en')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                currentLanguage === 'en'
                  ? 'bg-white text-indigo-700 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              English (EN)
            </button>
          </div>
        </div>

        {/* Action Controls & Export Buttons */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-100 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-slate-500 font-medium">
              {subtitles.length} Cues
            </span>

            {/* Auto Split Action Button */}
            <button
              data-testid="auto-split-btn"
              onClick={handleAutoSplit}
              disabled={isSplitting}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition shadow-xs ${
                hasLongCues
                  ? 'bg-amber-500 hover:bg-amber-600 text-slate-950 animate-pulse'
                  : 'bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200'
              }`}
              title="Automatically split long captions into shorter, readable subtitle cues"
            >
              <Zap className="w-3.5 h-3.5 text-amber-950" />
              <span>{isSplitting ? 'Splitting...' : 'Auto Split Long Cues'}</span>
            </button>

            <button
              onClick={() => setShowSplitSettings(!showSplitSettings)}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 text-xs transition"
              title="Configure auto-split thresholds"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>

            {hasCustomEdits ? (
              <span className="flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                <Sparkles className="w-3 h-3 text-amber-600" />
                Custom Subtitles
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Synced with {currentLanguage === 'km' ? 'Translation' : 'Transcript'}
              </span>
            )}

            {hasCustomEdits && (
              <button
                data-testid="reset-subtitles-btn"
                onClick={handleResetSubtitles}
                disabled={isResetting}
                className="ml-2 text-[11px] text-slate-600 hover:text-rose-600 flex items-center gap-1 transition"
                title="Reset all edits back to source"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset All to Source</span>
              </button>
            )}
          </div>

          {/* Quick Export Downloads & Styling Toggle */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              data-testid="subtitle-styling-toggle"
              onClick={() => setShowStyleSettings(!showStyleSettings)}
              className={`px-2.5 py-1.5 rounded-lg border text-xs font-medium flex items-center gap-1.5 transition ${
                showStyleSettings
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                  : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Subtitle Styling</span>
            </button>

            <a
              data-testid="download-srt-btn"
              href={api.getSubtitleExportUrl(projectId, currentLanguage, 'srt')}
              download
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-1.5 transition shadow-xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .SRT</span>
            </a>

            <a
              data-testid="download-vtt-btn"
              href={api.getSubtitleExportUrl(projectId, currentLanguage, 'vtt')}
              download
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs flex items-center gap-1.5 transition shadow-xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .VTT</span>
            </a>
          </div>
        </div>

        {/* Collapsible Auto-Split Thresholds Settings */}
        {showSplitSettings && (
          <div className="p-4 rounded-xl bg-amber-50/50 border border-amber-200 text-xs space-y-3">
            <div className="font-semibold text-slate-800 flex items-center justify-between">
              <span>Auto Split Thresholds</span>
              <span className="text-[11px] text-slate-500 font-normal">
                Splits cues exceeding either threshold along natural sentence and clause boundaries
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] font-medium text-slate-700 flex justify-between">
                  <span>Max Characters Per Cue:</span>
                  <span className="font-mono font-bold text-indigo-600">{maxCharsThreshold} chars</span>
                </label>
                <input
                  type="range"
                  min="40"
                  max="120"
                  step="5"
                  value={maxCharsThreshold}
                  onChange={(e) => setMaxCharsThreshold(Number(e.target.value))}
                  className="w-full mt-1 accent-indigo-600"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-slate-700 flex justify-between">
                  <span>Max Duration Per Cue:</span>
                  <span className="font-mono font-bold text-indigo-600">{maxDurationThreshold.toFixed(1)}s</span>
                </label>
                <input
                  type="range"
                  min="3.0"
                  max="10.0"
                  step="0.5"
                  value={maxDurationThreshold}
                  onChange={(e) => setMaxDurationThreshold(Number(e.target.value))}
                  className="w-full mt-1 accent-indigo-600"
                />
              </div>
            </div>
          </div>
        )}

        {/* Collapsible Styling Preferences & Preset Controls */}
        {showStyleSettings && (
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-4 animate-fadeIn text-xs">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <span className="font-semibold text-slate-800">Caption Style Presets</span>
              <div className="flex items-center gap-1.5 bg-white p-1 rounded-lg border border-slate-200">
                <button
                  data-testid="preset-standard-btn"
                  onClick={() => handleApplyPreset('standard')}
                  className={`px-2.5 py-1 rounded text-xs font-semibold transition ${
                    subtitleStyles.preset === 'standard'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Standard Box
                </button>
                <button
                  data-testid="preset-cinema-btn"
                  onClick={() => handleApplyPreset('cinema')}
                  className={`px-2.5 py-1 rounded text-xs font-semibold transition ${
                    subtitleStyles.preset === 'cinema'
                      ? 'bg-amber-500 text-slate-950 font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Cinema Yellow
                </button>
                <button
                  data-testid="preset-custom-btn"
                  onClick={() => handleApplyPreset('custom')}
                  className={`px-2.5 py-1 rounded text-xs font-semibold transition ${
                    subtitleStyles.preset === 'custom'
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Custom
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              {/* Font Size */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-slate-600">Font Size</label>
                <div className="flex items-center bg-white rounded-lg border border-slate-200 p-0.5">
                  {(['sm', 'base', 'lg', 'xl'] as const).map((sz) => (
                    <button
                      key={sz}
                      onClick={() => onUpdateStyles({ ...subtitleStyles, fontSize: sz, preset: 'custom' })}
                      className={`flex-1 py-1 rounded text-center font-mono uppercase text-[11px] font-medium transition ${
                        subtitleStyles.fontSize === sz
                          ? 'bg-indigo-600 text-white font-bold'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {sz}
                    </button>
                  ))}
                </div>
              </div>

              {/* Text Color */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-slate-600">Text Color</label>
                <div className="flex items-center gap-1.5 pt-0.5">
                  {(
                    [
                      { id: 'white', label: 'White', color: '#ffffff' },
                      { id: 'yellow', label: 'Yellow', color: '#facc15' },
                      { id: 'cyan', label: 'Cyan', color: '#38bdf8' },
                      { id: 'green', label: 'Green', color: '#4ade80' },
                    ] as const
                  ).map((c) => (
                    <button
                      key={c.id}
                      onClick={() => onUpdateStyles({ ...subtitleStyles, textColor: c.id, preset: 'custom' })}
                      className={`flex items-center gap-1 px-2 py-1 rounded-lg border text-[11px] font-medium transition ${
                        subtitleStyles.textColor === c.id
                          ? 'bg-slate-900 text-white border-slate-900 ring-2 ring-indigo-400'
                          : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      <span
                        className="w-2.5 h-2.5 rounded-full border border-slate-300"
                        style={{ backgroundColor: c.color }}
                      />
                      <span>{c.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Screen Position */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-slate-600">Screen Position</label>
                <div className="flex items-center bg-white rounded-lg border border-slate-200 p-0.5">
                  {(
                    [
                      { id: 'bottom', label: 'Bottom' },
                      { id: 'top', label: 'Top' },
                      { id: 'middle', label: 'Center' },
                    ] as const
                  ).map((pos) => (
                    <button
                      key={pos.id}
                      onClick={() => onUpdateStyles({ ...subtitleStyles, position: pos.id, preset: 'custom' })}
                      className={`flex-1 py-1 rounded text-center text-[11px] font-medium transition ${
                        (subtitleStyles.position || 'bottom') === pos.id
                          ? 'bg-indigo-600 text-white font-bold'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {pos.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Background Opacity */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-medium text-slate-600">Background Shading</label>
                <div className="flex items-center bg-white rounded-lg border border-slate-200 p-0.5">
                  {[
                    { val: 0, label: 'None' },
                    { val: 0.5, label: '50%' },
                    { val: 0.85, label: '85%' },
                  ].map((bg) => (
                    <button
                      key={bg.val}
                      onClick={() => onUpdateStyles({ ...subtitleStyles, bgOpacity: bg.val, preset: 'custom' })}
                      className={`flex-1 py-1 rounded text-center text-[11px] font-medium transition ${
                        subtitleStyles.bgOpacity === bg.val
                          ? 'bg-indigo-600 text-white font-bold'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {bg.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Live Sample Caption Preview */}
            <div className="pt-2">
              <div className="text-[11px] text-slate-500 mb-1 flex items-center justify-between">
                <span>Live Caption Overlay Preview:</span>
                <span className="font-mono text-[10px] text-indigo-600 uppercase">
                  {subtitleStyles.preset} Mode
                </span>
              </div>
              <div className="h-16 rounded-xl bg-slate-950 flex items-center justify-center p-3 relative overflow-hidden">
                <div
                  className={`px-4 py-1.5 rounded-lg text-center transition-all ${
                    currentLanguage === 'km' ? 'font-khmer font-medium' : 'font-sans'
                  } ${
                    subtitleStyles.preset === 'cinema'
                      ? 'drop-shadow-[0_2px_4px_rgba(0,0,0,0.95)]'
                      : 'shadow-md'
                  }`}
                  style={{
                    backgroundColor:
                      subtitleStyles.preset === 'cinema'
                        ? 'transparent'
                        : subtitleStyles.bgOpacity === 0
                        ? 'transparent'
                        : `rgba(0,0,0,${subtitleStyles.bgOpacity})`,
                    color:
                      subtitleStyles.preset === 'cinema'
                        ? '#facc15'
                        : subtitleStyles.textColor === 'yellow'
                        ? '#facc15'
                        : subtitleStyles.textColor === 'cyan'
                        ? '#38bdf8'
                        : subtitleStyles.textColor === 'green'
                        ? '#4ade80'
                        : '#ffffff',
                    textShadow:
                      subtitleStyles.preset === 'cinema' || subtitleStyles.shadow
                        ? '2px 2px 4px rgba(0,0,0,0.95), -1px -1px 2px rgba(0,0,0,0.85)'
                        : 'none',
                    fontSize:
                      subtitleStyles.fontSize === 'sm'
                        ? '0.875rem'
                        : subtitleStyles.fontSize === 'lg'
                        ? '1.125rem'
                        : subtitleStyles.fontSize === 'xl'
                        ? '1.25rem'
                        : '1rem',
                  }}
                >
                  {currentLanguage === 'km'
                    ? 'សូមស្វាគមន៍មកកាន់ KhmerDub AI!'
                    : 'Welcome to KhmerDub AI!'}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Status / Error feedback */}
        {statusMessage && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{statusMessage}</span>
          </div>
        )}
        {errorMessage && (
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      {/* Subtitle Search Bar */}
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
        <input
          type="text"
          placeholder="Search subtitles by text or cue number..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full pl-10 pr-4 py-2 bg-white rounded-xl border border-slate-200 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      {/* Subtitle Cue List */}
      <div className="space-y-3">
        {filteredSegments.length === 0 ? (
          <div className="p-12 text-center bg-white rounded-2xl border border-slate-200">
            <Subtitles className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <h3 className="text-sm font-semibold text-slate-700">No Subtitle Cues Found</h3>
            <p className="text-xs text-slate-400 mt-1">
              {searchQuery
                ? 'Try a different search query'
                : `Ensure ${currentLanguage === 'km' ? 'translation' : 'transcription'} is completed.`}
            </p>
          </div>
        ) : (
          filteredSegments.map((seg, idx) => {
            const isEditing = editingOrder === seg.segment_order;
            const duration = Math.max(0.1, seg.end_time - seg.start_time);
            const isSelected = selectedSegmentId === seg.id || selectedSegmentId === seg.segment_order.toString();
            const isActive = activeSegmentId === seg.id || activeSegmentId === seg.segment_order.toString();
            const isLast = idx === filteredSegments.length - 1;

            return (
              <div
                key={seg.id || seg.segment_order}
                id={`sub-seg-${seg.segment_order}`}
                className={`p-4 rounded-xl border bg-white transition shadow-2xs space-y-3 ${
                  isSelected
                    ? 'ring-2 ring-indigo-500 border-indigo-400 bg-indigo-50/30'
                    : isActive
                    ? 'ring-1 ring-indigo-400 border-indigo-300 bg-indigo-50/20'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                {/* Header: Sequence, Timing, Badges & Actions */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100 text-xs">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200 text-xs">
                      #{seg.segment_order}
                    </span>

                    <button
                      onClick={() => onSeekVideo(seg.start_time)}
                      className="font-mono text-slate-600 hover:text-indigo-600 flex items-center gap-1 font-semibold group transition"
                      title="Seek video to cue start timestamp"
                    >
                      <Clock className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600" />
                      <span>{formatSrtTime(seg.start_time)} → {formatSrtTime(seg.end_time)}</span>
                      <span className="text-[10px] text-slate-400 font-normal">
                        ({duration.toFixed(2)}s)
                      </span>
                    </button>

                    {/* Timing Confidence Badge */}
                    {seg.timing_confidence === 'estimated' ? (
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200 flex items-center gap-1"
                        title="Proportionally estimated split timing. Click Edit to fine-tune timestamps."
                      >
                        ⏱️ Estimated
                      </span>
                    ) : seg.timing_confidence === 'manual' ? (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200">
                        ✏️ Manual
                      </span>
                    ) : null}

                    {/* Readability Warnings Badges */}
                    {seg.readability?.has_warnings &&
                      seg.readability.warnings.map((warn, wIdx) => (
                        <span
                          key={wIdx}
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1"
                          title={warn}
                        >
                          ⚠️ {warn}
                        </span>
                      ))}

                    {seg.is_customized ? (
                      <span className="text-[10px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                        Customized
                      </span>
                    ) : (
                      <span className="text-[10px] text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded">
                        Synced
                      </span>
                    )}
                  </div>

                  {/* Actions: Play, Split, Merge, Edit */}
                  <div className="flex items-center gap-1 self-end sm:self-auto">
                    <button
                      onClick={() => onSeekVideo(seg.start_time)}
                      className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition"
                      title="Seek & Play in Video"
                    >
                      <Play className="w-3.5 h-3.5" />
                    </button>

                    {!isEditing && (
                      <>
                        <button
                          data-testid={`split-sub-btn-${seg.segment_order}`}
                          onClick={() => handleManualSplit(seg.segment_order)}
                          disabled={isSplitting}
                          className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 transition"
                          title="Split this cue into two shorter cues"
                        >
                          <Scissors className="w-3 h-3 text-slate-500" />
                          <span>Split</span>
                        </button>

                        {!isLast && (
                          <button
                            data-testid={`merge-sub-btn-${seg.segment_order}`}
                            onClick={() => handleMergeWithNext(seg.segment_order)}
                            disabled={isSplitting}
                            className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 transition"
                            title="Merge this cue with the next cue"
                          >
                            <Link2 className="w-3 h-3 text-slate-500" />
                            <span>Merge</span>
                          </button>
                        )}

                        <button
                          data-testid={`edit-sub-btn-${seg.segment_order}`}
                          onClick={() => handleStartEdit(seg)}
                          className="px-2.5 py-1 rounded bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold flex items-center gap-1 transition border border-indigo-200"
                          title="Edit subtitle text & adjust timing"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                          <span>Edit</span>
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Outdated Warning Banner */}
                {seg.is_source_outdated && (
                  <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-300 text-amber-900 text-xs flex flex-wrap items-center justify-between gap-2 animate-fadeIn">
                    <div className="flex items-center gap-1.5 font-medium">
                      <RefreshCw className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                      <span>Source translation changed since this subtitle was edited.</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleKeepEdits(seg.segment_order)}
                        className="px-2 py-0.5 rounded bg-white hover:bg-amber-100 border border-amber-300 text-[11px] font-semibold text-amber-900 transition"
                        title="Dismiss warning and keep your custom text"
                      >
                        Keep My Edits
                      </button>
                      <button
                        onClick={() => handleResetSingleCue(seg.segment_order)}
                        className="px-2 py-0.5 rounded bg-amber-600 hover:bg-amber-700 text-[11px] font-semibold text-white transition"
                        title="Reset this cue to the latest source text"
                      >
                        Reset to Source
                      </button>
                    </div>
                  </div>
                )}

                {/* Body: Editor or Display */}
                <div>
                  {isEditing ? (
                    <div className="space-y-3 pt-1">
                      <textarea
                        data-testid={`sub-input-${seg.segment_order}`}
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        rows={3}
                        className={`w-full p-2.5 rounded-xl border border-indigo-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white ${
                          currentLanguage === 'km' ? 'font-khmer leading-relaxed' : 'font-sans'
                        }`}
                        placeholder="Enter subtitle text..."
                        autoFocus
                      />

                      {/* Timestamp fine-tuning controls */}
                      <div className="flex flex-wrap items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                        <div className="flex items-center gap-2">
                          <label className="text-[11px] font-semibold text-slate-600">Start (s):</label>
                          <input
                            type="number"
                            step="0.1"
                            min="0"
                            value={editStartTime}
                            onChange={(e) => setEditStartTime(Number(e.target.value))}
                            className="w-24 px-2 py-1 rounded-lg border border-slate-300 font-mono text-xs focus:ring-1 focus:ring-indigo-500"
                          />
                        </div>

                        <div className="flex items-center gap-2">
                          <label className="text-[11px] font-semibold text-slate-600">End (s):</label>
                          <input
                            type="number"
                            step="0.1"
                            min="0"
                            value={editEndTime}
                            onChange={(e) => setEditEndTime(Number(e.target.value))}
                            className="w-24 px-2 py-1 rounded-lg border border-slate-300 font-mono text-xs focus:ring-1 focus:ring-indigo-500"
                          />
                        </div>

                        <span className="text-[11px] font-mono text-indigo-600 font-medium">
                          Duration: {Math.max(0, editEndTime - editStartTime).toFixed(2)}s
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="text-[11px] text-slate-400">
                          {editText.length} characters • {editText.split('\n').length} line(s)
                        </span>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleCancelEdit}
                            disabled={isSaving}
                            className="px-2.5 py-1 rounded-lg text-slate-600 hover:bg-slate-100 text-xs font-medium transition"
                          >
                            Cancel
                          </button>
                          <button
                            data-testid={`save-sub-btn-${seg.segment_order}`}
                            onClick={() => handleSaveEdit(seg.segment_order)}
                            disabled={isSaving}
                            className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1 transition shadow-xs disabled:opacity-50"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>{isSaving ? 'Saving...' : 'Save Subtitle'}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div
                      className={`text-sm text-slate-800 whitespace-pre-line leading-relaxed ${
                        currentLanguage === 'km' ? 'font-khmer' : 'font-sans'
                      }`}
                    >
                      {seg.text}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
