import React from 'react';
import {
  Download,
  Film,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Subtitles,
  Wand2,
  Sliders,
  Music,
  Volume2,
  Smartphone,
  Monitor,
  Square,
} from 'lucide-react';
import {
  ProjectDetail,
  ExportStatusResponse,
  TimingConflict,
  TranslationSegment,
} from '../../types';
import { ExportOptions } from '../../services/api';

interface ExportTabProps {
  project: ProjectDetail;
  exportStatus: ExportStatusResponse | null;
  timingConflicts: TimingConflict[];
  translationSegments: TranslationSegment[];
  isExporting: boolean;
  onExportVideo: (options?: ExportOptions) => Promise<void>;
  onOpenAIImprove: (segment: TranslationSegment) => void;
  exportError?: string | null;
  onAutoFitConflicts?: () => Promise<void>;
  isAutoFitting?: boolean;
}

export const ExportTab: React.FC<ExportTabProps> = ({
  project,
  exportStatus,
  timingConflicts,
  translationSegments,
  isExporting,
  onExportVideo,
  onOpenAIImprove,
  exportError,
  onAutoFitConflicts,
  isAutoFitting = false,
}) => {
  const [showReviewList, setShowReviewList] = React.useState(false);
  const [fillMode, setFillMode] = React.useState<'natural' | 'stretch'>('natural');
  const [overflowPolicy, setOverflowPolicy] = React.useState<'allow_overlap' | 'truncate_fade' | 'fail'>('allow_overlap');
  const [strictValidation, setStrictValidation] = React.useState<boolean>(false);
  const [preserveBgm, setPreserveBgm] = React.useState<boolean>(false);
  const [duckingPreset, setDuckingPreset] = React.useState<'light' | 'balanced' | 'strong' | 'mute'>('balanced');
  const [bgmVolume, setBgmVolume] = React.useState<number>(0.35);
  const [attenuateCenterVocals, setAttenuateCenterVocals] = React.useState<boolean>(true);
  const [aspectRatio, setAspectRatio] = React.useState<'original' | '9:16' | '1:1' | '16:9'>('original');
  const [reframeMode, setReframeMode] = React.useState<'blur_pillar' | 'center_crop' | 'fit_black'>('blur_pillar');
  const [burnSubtitles, setBurnSubtitles] = React.useState<boolean>(false);
  const [subtitleStyle, setSubtitleStyle] = React.useState<'tiktok_yellow' | 'classic_white' | 'boxed_black' | 'headline_bold'>('tiktok_yellow');
  const [subtitleLanguage, setSubtitleLanguage] = React.useState<'km' | 'en' | 'bilingual'>('km');
  const [subtitleFont, setSubtitleFont] = React.useState<string>('Khmer OS Battambang');

  const handleTriggerExport = () => {
    onExportVideo({
      fillMode,
      overflowPolicy: strictValidation ? 'fail' : overflowPolicy,
      strictValidation,
      preserveBgm,
      duckingPreset,
      bgmVolume,
      attenuateCenterVocals,
      aspectRatio,
      reframeMode,
      burnSubtitles,
      subtitleStyle,
      subtitleLanguage,
      subtitleFont,
    });
  };
  const isV2 = ['v2', 'v2.1', 'v2.2', 'v2.3'].includes(project.pipeline_version || '') || ['v2', 'v2.1', 'v2.2', 'v2.3'].includes(exportStatus?.pipeline_version || '');
  const timingSummary = exportStatus?.timing_summary;

  const isVideoReady = Boolean(project.video?.file_path || project.original_video_path);
  const isAudioExtracted = project.status !== 'uploaded' && project.status !== 'created';
  const isTranscribed = project.transcript_segments && project.transcript_segments.length > 0;
  const isTranslated = translationSegments.length > 0;
  const isVoiceGenerated = project.generated_audios && project.generated_audios.length > 0;
  const hasTimingConflicts = timingConflicts.length > 0;

  const isReadyToExport =
    isVideoReady &&
    isAudioExtracted &&
    isTranscribed &&
    isTranslated &&
    isVoiceGenerated &&
    !hasTimingConflicts;

  const isExportComplete =
    project.status === 'completed' || Boolean(exportStatus?.exported_video_path);

  const downloadUrl = `/api/projects/${project.id}/export/download`;

  const checklist = [
    {
      title: 'Video Uploaded & Validated',
      desc: project.video?.filename || 'Source MP4 container',
      ready: isVideoReady,
    },
    {
      title: '16kHz PCM Audio Extracted',
      desc: 'Clean mono audio track for Whisper',
      ready: isAudioExtracted,
    },
    {
      title: 'English Transcript Completed',
      desc: `${project.transcript_segments?.length || 0} VAD speech segments transcribed`,
      ready: isTranscribed,
    },
    {
      title: 'Khmer Translations Ready',
      desc: `${translationSegments.length} segments translated & reviewed`,
      ready: isTranslated,
    },
    {
      title: 'Khmer Speech Synthesized',
      desc: `${project.generated_audios?.length || 0} audio pieces generated`,
      ready: isVoiceGenerated,
    },
    {
      title: isV2 ? 'Timing Optimization' : 'Timing Conflicts Resolved',
      desc: hasTimingConflicts
        ? `${timingConflicts.length} segment(s) exceed available timing window`
        : isV2 && timingSummary
        ? `${timingSummary.total_segments} segments synchronized (${timingSummary.automatically_optimized} auto-optimized)`
        : 'All segments fit within original video timeline',
      ready: !hasTimingConflicts,
      isWarning: hasTimingConflicts,
    },
  ];

  const formatFileSize = (bytes?: number | null) => {
    if (!bytes) return 'N/A';
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Export Trigger */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Film className="w-5 h-5 text-indigo-600" />
            <h3 className="text-base font-bold text-slate-900">
              Audio Synchronization & Dubbed Video Export
            </h3>
          </div>
          <p className="text-xs text-slate-500 max-w-xl leading-relaxed">
            Muxes synchronized 44.1kHz stereo Khmer speech timeline with original video stream.
            Strict duration preservation ensures exported MP4 matches source video runtime without drift.
          </p>
        </div>

        <div className="shrink-0">
          <button
            onClick={handleTriggerExport}
            disabled={!isReadyToExport || isExporting}
            className={`px-5 py-3 rounded-xl font-bold text-xs sm:text-sm shadow-md transition-all flex items-center gap-2 ${
              isReadyToExport
                ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/30'
                : 'bg-slate-200 text-slate-500 cursor-not-allowed'
            }`}
          >
            {isExporting ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Exporting Dubbed MP4...</span>
              </>
            ) : isExportComplete ? (
              <>
                <RotateCcw className="w-4 h-4" />
                <span>Re-export Dubbed Video</span>
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                <span>Export Dubbed Video</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Export Error Alert */}
      {exportError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="font-semibold block">Export Prevented by Timing Guard</span>
            <p>{exportError}</p>
          </div>
        </div>
      )}

      {/* Timeline Fitting & Speech Pacing Controls */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-indigo-600" />
            <h4 className="text-sm font-bold text-slate-900">
              Sample-Accurate Timeline & Speech Pacing Controls
            </h4>
          </div>
          <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2.5 py-0.5 rounded-full">
            Zero-Drift PCM Engine
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Fill Mode */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <span>Speech Pacing (Fill Mode)</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setFillMode('natural')}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  fillMode === 'natural'
                    ? 'border-indigo-600 bg-indigo-50/60 ring-1 ring-indigo-600/30'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900">Natural Dialogue</div>
                <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  Min 0.75x speed; pads pauses with silence naturally.
                </div>
              </button>

              <button
                type="button"
                onClick={() => setFillMode('stretch')}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  fillMode === 'stretch'
                    ? 'border-indigo-600 bg-indigo-50/60 ring-1 ring-indigo-600/30'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900">Speech Stretch</div>
                <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  Min 0.50x speed; stretches speech to fill the slot.
                </div>
              </button>
            </div>
          </div>

          {/* Timing Guard / Overflow Policy */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <span>Timing Protection & Overflow Policy</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  setStrictValidation(false);
                  setOverflowPolicy('allow_overlap');
                }}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  !strictValidation && overflowPolicy === 'allow_overlap'
                    ? 'border-emerald-600 bg-emerald-50/60 ring-1 ring-emerald-600/30'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900 flex items-center gap-1">
                  <span>Smart Overlap & Fade</span>
                  <span className="text-[9px] bg-emerald-100 text-emerald-800 font-bold px-1.5 py-0.2 rounded">Recommended</span>
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  Allows speech to flow into dialogue pauses without failing export.
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setStrictValidation(true);
                  setOverflowPolicy('fail');
                }}
                className={`p-2.5 rounded-xl border text-left transition-all ${
                  strictValidation
                    ? 'border-amber-600 bg-amber-50/60 ring-1 ring-amber-600/30'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900">Strict Validation</div>
                <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                  Blocks export if speech exceeds available slot window.
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Social Media Video Format & Aspect Ratio */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-pink-50 flex items-center justify-center text-pink-600 shrink-0">
              <Smartphone className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-slate-900">
                  Social Media Format & Aspect Ratio
                </h4>
                <span className="text-[10px] font-bold bg-pink-100 text-pink-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                  TikTok / Shorts / Reels
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Automatically convert landscape videos into vertical 9:16 or square formats for mobile social feeds.
              </p>
            </div>
          </div>
        </div>

        {/* Aspect Ratio Presets */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
            <span>Target Platform & Aspect Ratio</span>
            <span className="text-[11px] text-slate-400 font-normal">Choose target format</span>
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
            {/* Original */}
            <button
              type="button"
              onClick={() => setAspectRatio('original')}
              className={`p-3 rounded-xl border text-left transition-all ${
                aspectRatio === 'original'
                  ? 'border-indigo-600 bg-indigo-50/60 ring-1 ring-indigo-600/30'
                  : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                  <Film className="w-3.5 h-3.5 text-indigo-600" />
                  Original Ratio
                </span>
                <span className="text-[10px] text-slate-400">Native</span>
              </div>
              <div className="text-[11px] text-slate-500 leading-snug">
                Keeps source video dimensions unchanged. Fastest export.
              </div>
            </button>

            {/* 9:16 Vertical */}
            <button
              type="button"
              onClick={() => setAspectRatio('9:16')}
              className={`p-3 rounded-xl border text-left transition-all ${
                aspectRatio === '9:16'
                  ? 'border-pink-600 bg-pink-50/60 ring-1 ring-pink-600/30 shadow-sm'
                  : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                  <Smartphone className="w-3.5 h-3.5 text-pink-600" />
                  9:16 Vertical
                </span>
                <span className="text-[10px] font-bold text-pink-700 bg-pink-100 px-1.5 py-0.5 rounded">
                  TikTok / Shorts
                </span>
              </div>
              <div className="text-[11px] text-slate-500 leading-snug">
                1080 × 1920 vertical format for viral short-form feeds.
              </div>
            </button>

            {/* 1:1 Square */}
            <button
              type="button"
              onClick={() => setAspectRatio('1:1')}
              className={`p-3 rounded-xl border text-left transition-all ${
                aspectRatio === '1:1'
                  ? 'border-indigo-600 bg-indigo-50/60 ring-1 ring-indigo-600/30'
                  : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                  <Square className="w-3.5 h-3.5 text-indigo-600" />
                  1:1 Square
                </span>
                <span className="text-[10px] text-slate-400">Instagram / FB</span>
              </div>
              <div className="text-[11px] text-slate-500 leading-snug">
                1080 × 1080 square format for social carousel & feed posts.
              </div>
            </button>

            {/* 16:9 Widescreen */}
            <button
              type="button"
              onClick={() => setAspectRatio('16:9')}
              className={`p-3 rounded-xl border text-left transition-all ${
                aspectRatio === '16:9'
                  ? 'border-indigo-600 bg-indigo-50/60 ring-1 ring-indigo-600/30'
                  : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                  <Monitor className="w-3.5 h-3.5 text-indigo-600" />
                  16:9 Widescreen
                </span>
                <span className="text-[10px] text-slate-400">YouTube Long</span>
              </div>
              <div className="text-[11px] text-slate-500 leading-snug">
                1920 × 1080 horizontal format for standard desktop & TV players.
              </div>
            </button>
          </div>
        </div>

        {/* Reframing Style (when not original) */}
        {aspectRatio !== 'original' && (
          <div className="pt-2 border-t border-slate-100 space-y-2">
            <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
              <span>Reframing Style</span>
              <span className="text-[11px] text-slate-400 font-normal">How the source fits inside {aspectRatio}</span>
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {/* Blur Pillar */}
              <button
                type="button"
                onClick={() => setReframeMode('blur_pillar')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  reframeMode === 'blur_pillar'
                    ? 'border-pink-600 bg-pink-50/50 ring-1 ring-pink-600/30 shadow-sm'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900 flex items-center justify-between">
                  <span>Cinematic Blurred Pillarbox</span>
                  <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">
                    Popular
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                  Source video centered with matching blurred background on top & bottom. Zero cropped details.
                </div>
              </button>

              {/* Center Crop */}
              <button
                type="button"
                onClick={() => setReframeMode('center_crop')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  reframeMode === 'center_crop'
                    ? 'border-pink-600 bg-pink-50/50 ring-1 ring-pink-600/30 shadow-sm'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900">Center Crop (Fill Screen)</div>
                <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                  Fills the vertical frame edge-to-edge, cropping left/right sides. Best for centered speakers.
                </div>
              </button>

              {/* Fit Black */}
              <button
                type="button"
                onClick={() => setReframeMode('fit_black')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  reframeMode === 'fit_black'
                    ? 'border-pink-600 bg-pink-50/50 ring-1 ring-pink-600/30 shadow-sm'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50/50'
                }`}
              >
                <div className="font-bold text-xs text-slate-900">Black Bars (Fit)</div>
                <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                  Letterbox format with solid black borders on top and bottom.
                </div>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Viral Burn-In Subtitles (Khmer Fonts & Styling) */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-50 flex items-center justify-center text-amber-600 shrink-0">
              <Subtitles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-slate-900">
                  Viral Burn-In Subtitles
                </h4>
                <span className="text-[10px] font-bold bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
                  Khmer Typography
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {burnSubtitles
                  ? 'Burns stylized captions permanently into the exported video canvas with mobile UI safe-zone spacing.'
                  : 'Exports video without burned-in captions. (Separate SRT/VTT subtitles can still be downloaded anytime).'}
              </p>
            </div>
          </div>

          <label className="relative inline-flex items-center cursor-pointer shrink-0">
            <input
              type="checkbox"
              checked={burnSubtitles}
              onChange={(e) => setBurnSubtitles(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
            <span className="ml-2 text-xs font-semibold text-slate-700">
              {burnSubtitles ? 'Burn-In Active' : 'No Subtitles (Default)'}
            </span>
          </label>
        </div>

        {burnSubtitles && (
          <div className="space-y-4 pt-1 animate-fadeIn">
            {/* Subtitle Style Presets */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                <span>Caption Visual Style Preset</span>
                <span className="text-[11px] text-slate-400 font-normal">ASS subtitle styling & contrast</span>
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                {/* TikTok Yellow */}
                <button
                  type="button"
                  onClick={() => setSubtitleStyle('tiktok_yellow')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    subtitleStyle === 'tiktok_yellow'
                      ? 'border-amber-500 bg-amber-50/70 ring-1 ring-amber-500/30 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-full bg-yellow-400 border border-slate-700 inline-block shadow-xs"></span>
                      TikTok Yellow
                    </span>
                    <span className="text-[9px] bg-amber-100 text-amber-800 font-bold px-1.5 py-0.2 rounded">Viral</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Vibrant yellow text with thick black outline. Maximum hook retention for Reels and TikTok.
                  </div>
                </button>

                {/* Classic White */}
                <button
                  type="button"
                  onClick={() => setSubtitleStyle('classic_white')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    subtitleStyle === 'classic_white'
                      ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/30 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-full bg-white border border-slate-400 inline-block"></span>
                      Classic White
                    </span>
                    <span className="text-[10px] text-slate-400">Clean</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Pure white typography with soft drop shadow. Elegant, distraction-free movie style.
                  </div>
                </button>

                {/* Boxed Black */}
                <button
                  type="button"
                  onClick={() => setSubtitleStyle('boxed_black')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    subtitleStyle === 'boxed_black'
                      ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/30 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded bg-slate-900 border border-slate-700 inline-block"></span>
                      Boxed Black
                    </span>
                    <span className="text-[10px] text-slate-400">High Contrast</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Solid translucent black backdrop pill. Guaranteed 100% legibility over bright or noisy video.
                  </div>
                </button>

                {/* Bold Headline */}
                <button
                  type="button"
                  onClick={() => setSubtitleStyle('headline_bold')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    subtitleStyle === 'headline_bold'
                      ? 'border-amber-600 bg-amber-50/70 ring-1 ring-amber-600/30 shadow-sm'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900 flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-full bg-amber-500 inline-block"></span>
                      Bold Headline
                    </span>
                    <span className="text-[10px] text-amber-700 font-bold bg-amber-100 px-1.5 py-0.2 rounded">Muol</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Traditional bold Khmer Muol font with gold accent. Dramatic, high-impact titles.
                  </div>
                </button>
              </div>
            </div>

            {/* Language & Font Selector Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
              {/* Language Selector */}
              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/40 space-y-2">
                <label className="text-xs font-semibold text-slate-700 block">
                  Subtitle Language Mode
                </label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setSubtitleLanguage('km')}
                    className={`py-2 px-2.5 rounded-lg text-xs font-semibold text-center transition-all ${
                      subtitleLanguage === 'km'
                        ? 'bg-amber-500 text-white shadow-xs'
                        : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    Khmer Only
                  </button>
                  <button
                    type="button"
                    onClick={() => setSubtitleLanguage('bilingual')}
                    className={`py-2 px-2.5 rounded-lg text-xs font-semibold text-center transition-all ${
                      subtitleLanguage === 'bilingual'
                        ? 'bg-amber-500 text-white shadow-xs'
                        : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    Bilingual (KM+EN)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSubtitleLanguage('en')}
                    className={`py-2 px-2.5 rounded-lg text-xs font-semibold text-center transition-all ${
                      subtitleLanguage === 'en'
                        ? 'bg-amber-500 text-white shadow-xs'
                        : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    English Only
                  </button>
                </div>
                <div className="text-[11px] text-slate-500">
                  {subtitleLanguage === 'bilingual'
                    ? 'Displays dubbed Khmer as primary caption with English translation below in italic.'
                    : subtitleLanguage === 'km'
                    ? 'Displays synchronized Khmer dubbed dialogue text.'
                    : 'Displays original English transcript text.'}
                </div>
              </div>

              {/* Font Family Selector */}
              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/40 space-y-2">
                <label className="text-xs font-semibold text-slate-700 block">
                  Khmer Font Family
                </label>
                <select
                  value={subtitleFont}
                  onChange={(e) => setSubtitleFont(e.target.value)}
                  className="w-full text-xs font-medium bg-white border border-slate-200 rounded-lg p-2 text-slate-800 focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  <option value="Khmer OS Battambang">Khmer OS Battambang (Standard Clean - Recommended)</option>
                  <option value="Khmer OS Muol">Khmer OS Muol (Bold Ornamental / Headline)</option>
                  <option value="Khmer OS Content">Khmer OS Content (Traditional Book Script)</option>
                  <option value="Khmer OS">Khmer OS (System Sans)</option>
                </select>
                <div className="text-[11px] text-slate-500">
                  Rendered via Linux HarfBuzz / libass Unicode shaping with zero missing glyphs or square boxes.
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Background Music & Audio Ducking Controls */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600 shrink-0">
              <Music className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-slate-900">
                  Background Audio & Music Mixing
                </h4>
                <span className="text-[10px] font-bold bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">
                  Sidechain DSP
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {preserveBgm
                  ? 'Mixes and ducks original video audio underneath Khmer speech. Note: original dialogue may be faintly audible if not isolated.'
                  : 'Replaces original video audio entirely with crystal-clear Khmer dialogue (recommended for cleanest dubbing).'}
              </p>
            </div>
          </div>

          <label className="relative inline-flex items-center cursor-pointer shrink-0">
            <input
              type="checkbox"
              checked={preserveBgm}
              onChange={(e) => setPreserveBgm(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
            <span className="ml-2 text-xs font-semibold text-slate-700">
              {preserveBgm ? 'Preserve BGM (Active)' : 'Clean Dubbing (Default)'}
            </span>
          </label>
        </div>

        {preserveBgm ? (
          <div className="space-y-4 pt-1">
            {/* Ducking Presets */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                <span>Ducking Intensity Preset</span>
                <span className="text-[11px] text-slate-400 font-normal">Sidechain compressor attenuation</span>
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                {/* Light */}
                <button
                  type="button"
                  onClick={() => setDuckingPreset('light')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    duckingPreset === 'light'
                      ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/30'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900">Gentle</span>
                    <span className="text-[10px] font-mono font-semibold text-slate-500 bg-slate-200/70 px-1.5 py-0.5 rounded">-6 dB</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Subtle dip for quiet background tunes, vlogs, and commentary.
                  </div>
                </button>

                {/* Balanced */}
                <button
                  type="button"
                  onClick={() => setDuckingPreset('balanced')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    duckingPreset === 'balanced'
                      ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/30'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-xs text-slate-900">Balanced</span>
                      <span className="text-[9px] bg-indigo-100 text-indigo-700 font-bold px-1.5 py-0.2 rounded">Recommended</span>
                    </div>
                    <span className="text-[10px] font-mono font-semibold text-indigo-700 bg-indigo-100 px-1.5 py-0.5 rounded">-12 dB</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Standard movie mix: dialogue cuts through clearly over SFX.
                  </div>
                </button>

                {/* Strong */}
                <button
                  type="button"
                  onClick={() => setDuckingPreset('strong')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    duckingPreset === 'strong'
                      ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/30'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900">Strong</span>
                    <span className="text-[10px] font-mono font-semibold text-slate-500 bg-slate-200/70 px-1.5 py-0.5 rounded">-18 dB</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Heavy suppression for action movies, loud explosions, or loud EDM.
                  </div>
                </button>

                {/* Mute */}
                <button
                  type="button"
                  onClick={() => setDuckingPreset('mute')}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    duckingPreset === 'mute'
                      ? 'border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/30'
                      : 'border-slate-200 hover:border-slate-300 bg-slate-50/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-slate-900">Full Cut</span>
                    <span className="text-[10px] font-mono font-semibold text-slate-500 bg-slate-200/70 px-1.5 py-0.5 rounded">Mute</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Silences background audio completely whenever Khmer speech occurs.
                  </div>
                </button>
              </div>
            </div>

            {/* Volume slider & Vocal Attenuation grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
              {/* Background Music Volume Slider */}
              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/40 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                    <Volume2 className="w-3.5 h-3.5 text-slate-500" />
                    <span>Background Audio Level</span>
                  </span>
                  <span className="text-xs font-mono font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
                    {Math.round(bgmVolume * 100)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.05"
                  max="0.8"
                  step="0.05"
                  value={bgmVolume}
                  onChange={(e) => setBgmVolume(parseFloat(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>5% (Faint)</span>
                  <span>35% (Recommended)</span>
                  <span>80% (Prominent)</span>
                </div>
              </div>

              {/* Vocal Attenuation Option */}
              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/40 flex items-start gap-3">
                <input
                  type="checkbox"
                  id="attenuate-vocals-checkbox"
                  checked={attenuateCenterVocals}
                  onChange={(e) => setAttenuateCenterVocals(e.target.checked)}
                  className="mt-1 w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500 cursor-pointer"
                />
                <label htmlFor="attenuate-vocals-checkbox" className="space-y-0.5 cursor-pointer">
                  <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                    <span>Attenuate Original Dialogue</span>
                    <span className="text-[10px] bg-slate-200 text-slate-700 font-medium px-1.5 py-0.2 rounded">Center Channel</span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-snug">
                    Reduces center-panned speech on stereo tracks using mid-channel filtering, suppressing original voice bleed-through while keeping stereo music & ambient Foley effects alive.
                  </p>
                </label>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-600 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <span className="font-semibold text-slate-800 block">Clean Khmer Dubbing (Default)</span>
              <span className="text-[11px] text-slate-500">The exported video replaces the original audio track with 100% synchronized Khmer dialogue.</span>
            </div>
            <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-2.5 py-1 rounded-full shrink-0">
              Clean Dialogue
            </span>
          </div>
        )}
      </div>

      {/* V2: Khmer Dubbing Ready Compact Summary (Section 15) */}
      {isV2 && timingSummary && timingSummary.unresolved_conflicts === 0 && (
        <div className="p-6 rounded-2xl bg-emerald-50/70 border border-emerald-200 text-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4 animate-fadeIn">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
              <h3 className="text-base font-bold text-emerald-950">Khmer Dubbing Ready</h3>
            </div>
            <div className="text-xs text-slate-600 space-y-1 pl-7">
              <p className="font-medium text-slate-800">
                <span className="font-semibold text-slate-900">{timingSummary.total_segments}</span> speech segments processed
              </p>
              <p className="text-slate-600">
                <span className="font-semibold text-slate-800">{timingSummary.fitted_without_changes ?? (timingSummary.total_segments - timingSummary.automatically_optimized)}</span> fitted without changes
              </p>
              <p className="text-slate-600">
                <span className="font-semibold text-slate-800">{timingSummary.automatically_optimized}</span> automatically optimized
              </p>
              <p className="text-emerald-700 font-bold">
                0 unresolved timing conflicts
              </p>
            </div>
          </div>

          <div className="shrink-0 flex items-center gap-2">
            {!isExportComplete && (
              <button
                onClick={handleTriggerExport}
                disabled={!isReadyToExport || isExporting}
                className={`px-5 py-2.5 rounded-xl font-bold text-xs shadow-md transition-all flex items-center gap-2 ${
                  isReadyToExport
                    ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-600/30'
                    : 'bg-slate-200 text-slate-500 cursor-not-allowed'
                }`}
              >
                {isExporting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Exporting MP4...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    <span>Export Dubbed Video</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      )}

      {/* V2: Khmer Dubbing — Review Required Compact Summary (Section 15) */}
      {isV2 && timingSummary && timingSummary.unresolved_conflicts > 0 && (
        <div className="p-6 rounded-2xl bg-amber-50/80 border border-amber-300 text-slate-800 shadow-sm space-y-4 animate-fadeIn">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                <h3 className="text-base font-bold text-amber-950">Khmer Dubbing — Review Required</h3>
              </div>
              <div className="text-xs text-slate-600 space-y-1 pl-7">
                <p className="font-medium text-slate-800">
                  <span className="font-semibold text-slate-900">{timingSummary.total_segments}</span> speech segments processed
                </p>
                <p className="text-slate-600">
                  <span className="font-semibold text-slate-800">{timingSummary.synchronized_successfully ?? (timingSummary.total_segments - timingSummary.unresolved_conflicts)}</span> synchronized successfully
                </p>
                <p className="text-amber-900 font-bold">
                  <span>{timingSummary.unresolved_conflicts}</span> require review
                </p>
              </div>
            </div>

            <div className="shrink-0 flex items-center gap-2">
              <button
                onClick={() => setShowReviewList((prev) => !prev)}
                className="px-4 py-2.5 rounded-xl font-bold text-xs bg-amber-600 hover:bg-amber-700 text-white shadow-md transition-all flex items-center gap-1.5"
              >
                <span>{showReviewList ? 'Hide Review List' : `Review ${timingSummary.unresolved_conflicts} Segment${timingSummary.unresolved_conflicts > 1 ? 's' : ''}`}</span>
              </button>
              {onAutoFitConflicts && (
                <button
                  onClick={onAutoFitConflicts}
                  disabled={isAutoFitting || isExporting}
                  className="px-4 py-2.5 rounded-xl font-bold text-xs bg-indigo-600 hover:bg-indigo-700 text-white shadow-md transition-all flex items-center gap-1.5"
                >
                  {isAutoFitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Optimizing...</span>
                    </>
                  ) : (
                    <>
                      <Wand2 className="w-3.5 h-3.5" />
                      <span>Auto-Optimize</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {showReviewList && (
            <div className="pt-3 border-t border-amber-200 space-y-2">
              <p className="text-amber-900 text-xs font-semibold">
                Remaining Unresolved Segments:
              </p>
              {timingConflicts.map((c) => {
                const seg = translationSegments.find((s) => s.segment_order === c.segment_order);
                return (
                  <div
                    key={c.segment_order}
                    className="p-3 bg-white rounded-xl border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-bold text-amber-900">Segment #{c.segment_order}</span>
                        <span className="text-[11px] font-mono text-slate-500">
                          ({c.start_time.toFixed(2)}s → {c.end_time.toFixed(2)}s)
                        </span>
                        <span className="text-[10px] bg-slate-100 text-slate-700 font-medium px-2 py-0.5 rounded-md">
                          Window: {c.available_window.toFixed(2)}s
                        </span>
                        <span className="text-[10px] bg-indigo-50 text-indigo-700 font-medium px-2 py-0.5 rounded-md">
                          Speech: {c.khmer_duration.toFixed(2)}s
                        </span>
                        <span className="text-[10px] bg-amber-50 text-amber-800 font-medium px-2 py-0.5 rounded-md">
                          Speed: {c.tempo_factor.toFixed(2)}x
                        </span>
                        <span className="text-[10px] bg-rose-100 text-rose-800 font-semibold px-2 py-0.5 rounded-full">
                          +{c.overflow_seconds.toFixed(2)}s overflow
                        </span>
                      </div>
                      {seg && (
                        <p className="font-khmer text-xs text-slate-700 font-medium">
                          {seg.khmer_text}
                        </p>
                      )}
                    </div>
                    {seg && (
                      <button
                        onClick={() => onOpenAIImprove(seg)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shrink-0 shadow-sm"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Shorten with AI</span>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* V1 Legacy: Timing Conflicts Details Card (Preserved for existing v1 projects) */}
      {!isV2 && hasTimingConflicts && (
        <div className="p-5 rounded-2xl bg-amber-50/70 border border-amber-300 text-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-amber-900 font-bold text-sm">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>{timingConflicts.length} Speech Timing Conflict(s) Detected</span>
            </div>

            {onAutoFitConflicts && (
              <button
                onClick={onAutoFitConflicts}
                disabled={isAutoFitting || isExporting}
                className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs shadow-md transition-all flex items-center gap-1.5 shrink-0"
                title="Automatically shorten translations and re-synthesize speech to fit original video timing"
              >
                {isAutoFitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Auto-Fitting Timing Conflicts...</span>
                  </>
                ) : (
                  <>
                    <Wand2 className="w-3.5 h-3.5" />
                    <span>Auto-Fit All Timing Conflicts</span>
                  </>
                )}
              </button>
            )}
          </div>

          <p className="text-amber-800 leading-relaxed">
            The following speech segments take longer to pronounce in Khmer than the original English video speech slot.
            Per project architecture, silent truncation is prevented. You can click <strong>Auto-Fit All Timing Conflicts</strong> to automatically optimize phrasing and speech timing, or shorten individual segments below.
          </p>

          <div className="space-y-2 pt-1">
            {timingConflicts.map((c) => {
              const seg = translationSegments.find((s) => s.segment_order === c.segment_order);
              return (
                <div
                  key={c.segment_order}
                  className="p-3 bg-white rounded-xl border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-bold text-amber-900">Segment #{c.segment_order}</span>
                      <span className="text-[11px] font-mono text-slate-500">
                        ({c.start_time.toFixed(2)}s → {c.end_time.toFixed(2)}s)
                      </span>
                      <span className="text-[10px] bg-slate-100 text-slate-700 font-medium px-2 py-0.5 rounded-md">
                        Window: {c.available_window.toFixed(2)}s
                      </span>
                      <span className="text-[10px] bg-indigo-50 text-indigo-700 font-medium px-2 py-0.5 rounded-md">
                        Speech: {c.khmer_duration.toFixed(2)}s
                      </span>
                      <span className="text-[10px] bg-amber-50 text-amber-800 font-medium px-2 py-0.5 rounded-md">
                        Speed: {c.tempo_factor.toFixed(2)}x
                      </span>
                      <span className="text-[10px] bg-rose-100 text-rose-800 font-semibold px-2 py-0.5 rounded-full">
                        +{c.overflow_seconds.toFixed(2)}s overflow
                      </span>
                    </div>
                    {seg && (
                      <p className="font-khmer text-xs text-slate-700 font-medium">
                        {seg.khmer_text}
                      </p>
                    )}
                  </div>

                  {seg && (
                    <button
                      onClick={() => onOpenAIImprove(seg)}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shrink-0 shadow-sm"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Shorten with AI</span>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Readiness Checklist Grid */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <h4 className="text-sm font-bold text-slate-900 pb-2 border-b border-slate-100">
          Dubbing Pipeline Readiness Checklist
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
          {checklist.map((item) => (
            <div
              key={item.title}
              className={`p-3.5 rounded-xl border flex items-start gap-3 ${
                item.ready
                  ? 'bg-emerald-50/40 border-emerald-200'
                  : item.isWarning
                  ? 'bg-amber-50/40 border-amber-300'
                  : 'bg-slate-50 border-slate-200'
              }`}
            >
              <div className="mt-0.5 shrink-0">
                {item.ready ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                )}
              </div>
              <div className="space-y-0.5">
                <span className="font-semibold text-slate-800 block">{item.title}</span>
                <span className="text-[11px] text-slate-500 leading-snug">{item.desc}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Completed Video Player & Download Card */}
      {isExportComplete && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4 animate-fadeIn">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              <div>
                <h4 className="text-sm font-bold text-slate-900">Synchronized Khmer Dubbed Video</h4>
                <p className="text-xs text-slate-500">
                  Ready for preview, download, and distribution
                </p>
              </div>
            </div>

            <a
              href={downloadUrl}
              download={`${project.title.replace(/\s+/g, '_')}_KhmerDub.mp4`}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs rounded-xl shadow-md flex items-center gap-2 transition"
            >
              <Download className="w-4 h-4" />
              <span>Download Dubbed MP4</span>
            </a>
          </div>

          <div className="aspect-video bg-black rounded-xl overflow-hidden shadow-inner max-w-3xl mx-auto">
            <video
              controls
              src={downloadUrl}
              className="w-full h-full object-contain"
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-2">
            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-slate-400 text-[11px] block">Video Duration</span>
              <span className="font-bold text-slate-800">
                {exportStatus?.exported_duration_seconds?.toFixed(2) || project.video?.duration_seconds?.toFixed(2)}s
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-slate-400 text-[11px] block">File Size</span>
              <span className="font-bold text-slate-800">
                {formatFileSize(exportStatus?.exported_file_size_bytes || project.video?.exported_file_size_bytes)}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-slate-400 text-[11px] block">Audio Encoding</span>
              <span className="font-bold text-slate-800">AAC 192kbps (44.1kHz)</span>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-slate-400 text-[11px] block">FastStart Container</span>
              <span className="font-bold text-emerald-600">Enabled (Web Streamable)</span>
            </div>
          </div>
        </div>
      )}

      {/* Subtitles Export Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100">
              <Subtitles className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-900">Subtitle Files (.SRT & .VTT)</h4>
              <p className="text-xs text-slate-500">
                Export synchronized subtitles with full Khmer Unicode support for YouTube, Facebook, or video players
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
          {/* Khmer SRT */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 flex flex-col justify-between gap-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-800">Khmer Subtitles</span>
                <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 text-[10px] font-mono font-bold">SRT</span>
              </div>
              <p className="text-[11px] text-slate-500">Standard SubRip format with Khmer Unicode</p>
            </div>
            <a
              data-testid="export-card-km-srt"
              href={`/api/projects/${project.id}/subtitles/export?language=km&format=srt`}
              download
              className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg flex items-center justify-center gap-1.5 transition shadow-2xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Khmer .SRT</span>
            </a>
          </div>

          {/* Khmer VTT */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 flex flex-col justify-between gap-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-800">Khmer WebVTT</span>
                <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[10px] font-mono font-bold">VTT</span>
              </div>
              <p className="text-[11px] text-slate-500">W3C Web Video Text Track format</p>
            </div>
            <a
              data-testid="export-card-km-vtt"
              href={`/api/projects/${project.id}/subtitles/export?language=km&format=vtt`}
              download
              className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-lg flex items-center justify-center gap-1.5 transition shadow-2xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Khmer .VTT</span>
            </a>
          </div>

          {/* English SRT */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 flex flex-col justify-between gap-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-800">English Subtitles</span>
                <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 text-[10px] font-mono font-bold">SRT</span>
              </div>
              <p className="text-[11px] text-slate-500">SubRip format from transcribed audio</p>
            </div>
            <a
              data-testid="export-card-en-srt"
              href={`/api/projects/${project.id}/subtitles/export?language=en&format=srt`}
              download
              className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg flex items-center justify-center gap-1.5 transition shadow-2xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download English .SRT</span>
            </a>
          </div>

          {/* English VTT */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 flex flex-col justify-between gap-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-800">English WebVTT</span>
                <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[10px] font-mono font-bold">VTT</span>
              </div>
              <p className="text-[11px] text-slate-500">Web video format from transcribed audio</p>
            </div>
            <a
              data-testid="export-card-en-vtt"
              href={`/api/projects/${project.id}/subtitles/export?language=en&format=vtt`}
              download
              className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-lg flex items-center justify-center gap-1.5 transition shadow-2xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download English .VTT</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};
