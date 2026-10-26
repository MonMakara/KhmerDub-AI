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
} from 'lucide-react';
import {
  ProjectDetail,
  ExportStatusResponse,
  TimingConflict,
  TranslationSegment,
} from '../../types';

interface ExportTabProps {
  project: ProjectDetail;
  exportStatus: ExportStatusResponse | null;
  timingConflicts: TimingConflict[];
  translationSegments: TranslationSegment[];
  isExporting: boolean;
  onExportVideo: () => Promise<void>;
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
  const isV2 = project.pipeline_version === 'v2' || exportStatus?.pipeline_version === 'v2';
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
            onClick={onExportVideo}
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
                onClick={onExportVideo}
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
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-amber-900">Segment #{c.segment_order}</span>
                        <span className="text-[11px] font-mono text-slate-500">
                          ({c.start_time.toFixed(2)}s → {c.end_time.toFixed(2)}s)
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
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-amber-900">Segment #{c.segment_order}</span>
                      <span className="text-[11px] font-mono text-slate-500">
                        ({c.start_time.toFixed(2)}s → {c.end_time.toFixed(2)}s)
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
