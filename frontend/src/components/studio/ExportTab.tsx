import React from 'react';
import {
  Download,
  Film,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
  Sparkles,
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
}) => {
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
      title: 'Timing Conflicts Resolved',
      desc: hasTimingConflicts
        ? `${timingConflicts.length} segment(s) exceed available timing window`
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

      {/* Timing Conflicts Details Card (if any) */}
      {hasTimingConflicts && (
        <div className="p-5 rounded-2xl bg-amber-50/70 border border-amber-300 text-xs space-y-3">
          <div className="flex items-center gap-2 text-amber-900 font-bold text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>{timingConflicts.length} Speech Timing Conflict(s) Detected</span>
          </div>

          <p className="text-amber-800 leading-relaxed">
            The following speech segments take longer to pronounce in Khmer than the original English video speech slot.
            Per project architecture, silent truncation is prevented. Please shorten the Khmer translation or apply an AI Shorten suggestion.
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
    </div>
  );
};
