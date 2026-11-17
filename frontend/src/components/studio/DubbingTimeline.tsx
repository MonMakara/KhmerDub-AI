import React, { useState, useRef, useMemo, useEffect, useCallback } from 'react';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  ChevronDown,
  ChevronUp,
  Clock,
  AlertTriangle,
  CheckCircle2,
  RotateCcw,
  Sparkles,
  ArrowRight,
  Volume2,
  Film,
  Languages,
  Sliders,
  Subtitles,
} from 'lucide-react';
import {
  TranscriptSegment,
  TranslationSegment,
  GeneratedAudio,
  TimingConflict,
  ScheduledSpeechUnit,
} from '../../types';

export interface DubbingTimelineProps {
  duration: number;
  currentTime: number;
  transcriptSegments: TranscriptSegment[];
  translationSegments: TranslationSegment[];
  generatedAudios: GeneratedAudio[];
  timingConflicts: TimingConflict[];
  scheduledUnits?: ScheduledSpeechUnit[];
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  onSeek: (timeInSeconds: number) => void;
  onNavigateToTranslation?: (segmentId: string) => void;
  onNavigateToSubtitles?: (segmentId: string) => void;
  onOpenAIImprove?: (segment: TranslationSegment) => void;
  isPlaying?: boolean;
}

export type TimelineSegmentStatus =
  | 'fit'
  | 'speed_adjusted'
  | 'conflict'
  | 'outdated'
  | 'no_audio';

export interface TimelineSegmentItem {
  id: string;
  order: number;
  start: number;
  end: number;
  transcriptText: string;
  khmerText?: string;
  audio?: GeneratedAudio;
  conflict?: TimingConflict;
  status: TimelineSegmentStatus;
  speechDuration: number;
  tempoFactor: number;
  overflowSeconds: number;
  translationSegment?: TranslationSegment;
  alignmentNote?: string;
  speakerLabel?: string | null;
}

export const DubbingTimeline: React.FC<DubbingTimelineProps> = ({
  duration,
  currentTime,
  transcriptSegments,
  translationSegments,
  generatedAudios,
  timingConflicts,
  scheduledUnits,
  selectedSegmentId,
  onSelectSegment,
  onSeek,
  onNavigateToTranslation,
  onNavigateToSubtitles,
  onOpenAIImprove,
  isPlaying = false,
}) => {
  // Container & Scroll references
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Layout & Zoom state
  const [containerWidth, setContainerWidth] = useState<number>(1000);
  const [zoomFactor, setZoomFactor] = useState<number>(1.0); // 1.0 = Fit Video
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [isScrubbing, setIsScrubbing] = useState<boolean>(false);
  const [hoverTime, setHoverTime] = useState<number | null>(null);

  // ResizeObserver to calculate container width responsive to viewport
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 100) {
          setContainerWidth(entry.contentRect.width);
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Compute total duration (from video duration or max segment end timestamp)
  const totalDuration = useMemo(() => {
    const maxEnd = transcriptSegments.reduce((max, s) => Math.max(max, s.end_time), 0);
    return Math.max(1, duration || maxEnd || 10);
  }, [duration, transcriptSegments]);

  // Base pixels per second when fitting the entire video in container
  // Reserve ~110px for the left track-labels header column
  const trackLabelWidth = 96;
  const availableWidth = Math.max(200, containerWidth - trackLabelWidth);
  const fitPxPerSec = availableWidth / totalDuration;

  // Actual active scaling
  const pxPerSec = Math.max(2, fitPxPerSec * zoomFactor);
  const contentWidth = Math.max(availableWidth, totalDuration * pxPerSec);

  // Build audio map by translation_segment_id
  const audioMap = useMemo(() => {
    const map = new Map<string, GeneratedAudio>();
    for (const a of generatedAudios) {
      if (a.translation_segment_id) {
        map.set(a.translation_segment_id, a);
      }
    }
    return map;
  }, [generatedAudios]);

  // Build translation map by segment_order or id
  const translationMap = useMemo(() => {
    const map = new Map<number, TranslationSegment>();
    for (const t of translationSegments) {
      map.set(t.segment_order, t);
    }
    return map;
  }, [translationSegments]);

  // Build conflict map by transcript_segment_id or segment_order
  const conflictMap = useMemo(() => {
    const map = new Map<number, TimingConflict>();
    for (const c of timingConflicts) {
      map.set(c.segment_order, c);
    }
    return map;
  }, [timingConflicts]);

  // Merge transcript + translation + audio + conflict into structured timeline items
  const timelineItems: TimelineSegmentItem[] = useMemo(() => {
    return transcriptSegments.map((tSeg) => {
      const transSeg = translationMap.get(tSeg.segment_order);
      const audio = transSeg ? audioMap.get(transSeg.id) : undefined;
      const conflict = conflictMap.get(tSeg.segment_order);

      const start = Math.max(0, tSeg.start_time);
      const end = Math.max(start + 0.1, tSeg.end_time);
      const origDur = Math.max(0.1, end - start);

      let status: TimelineSegmentStatus = 'no_audio';
      let speechDuration = origDur;
      let tempoFactor = 1.0;
      let overflowSeconds = 0;

      if (conflict) {
        status = 'conflict';
        speechDuration = conflict.khmer_duration || (audio?.duration_seconds ?? origDur);
        tempoFactor = conflict.required_tempo || (speechDuration / origDur);
        overflowSeconds = conflict.overflow_seconds || Math.max(0, speechDuration - origDur);
      } else if (!audio) {
        status = 'no_audio';
        speechDuration = origDur;
      } else if (audio.is_outdated) {
        status = 'outdated';
        speechDuration = audio.duration_seconds || origDur;
      } else {
        speechDuration = audio.duration_seconds || origDur;
        if (speechDuration > origDur + 0.05) {
          status = 'speed_adjusted';
          tempoFactor = speechDuration / origDur;
        } else {
          status = 'fit';
        }
      }

      return {
        id: tSeg.id,
        order: tSeg.segment_order,
        start,
        end,
        transcriptText: tSeg.text,
        khmerText: transSeg?.khmer_text,
        audio,
        conflict,
        status,
        speechDuration,
        tempoFactor,
        overflowSeconds,
        translationSegment: transSeg,
        speakerLabel: tSeg.speaker_label,
      };
    });
  }, [transcriptSegments, translationMap, audioMap, conflictMap]);

  // Speech units have independent source mappings and measured backend timing.
  const speechItems: TimelineSegmentItem[] = useMemo(() => {
    if (!scheduledUnits) return timelineItems;
    return translationSegments.map((unit) => {
      const scheduled = scheduledUnits.find((s) => s.translation_segment_id === unit.id);
      const source = transcriptSegments.find((s) => s.id === unit.transcript_segment_id)
        || transcriptSegments.find((s) => unit.source_segment_ids?.includes(s.id));
      const audio = audioMap.get(unit.id);
      const conflict = conflictMap.get(unit.segment_order);
      const start = scheduled?.scheduled_start ?? unit.start_time ?? source?.start_time ?? 0;
      const end = scheduled?.scheduled_end ?? unit.end_time ?? source?.end_time ?? start;
      const state: TimelineSegmentStatus = !audio ? 'no_audio'
        : audio.is_outdated || unit.is_outdated ? 'outdated'
        : scheduled?.status === 'needs_optimization' ? 'conflict'
        : (scheduled?.tempo_factor ?? 1) > 1 ? 'speed_adjusted' : 'fit';
      return {
        id: source?.id ?? unit.id, order: unit.segment_order, start, end,
        transcriptText: unit.source_text ?? source?.text ?? '', khmerText: unit.khmer_text,
        audio, conflict, status: state,
        speechDuration: scheduled?.processed_duration ?? audio?.duration_seconds ?? Math.max(0, end - start),
        tempoFactor: scheduled?.tempo_factor ?? 1,
        overflowSeconds: scheduled?.overflow_seconds ?? 0,
        translationSegment: unit,
        speakerLabel: unit.speaker_label ?? source?.speaker_label,
        alignmentNote: scheduled && (scheduled.local_overflow_seconds > 0.05 || Math.abs(scheduled.alignment_delay_seconds) > 0.5)
          ? `Alignment review: start offset ${scheduled.alignment_delay_seconds.toFixed(2)}s; neighboring space used ${scheduled.local_overflow_seconds.toFixed(2)}s.` : undefined,
      };
    });
  }, [scheduledUnits, timelineItems, translationSegments, transcriptSegments, audioMap, conflictMap]);

  // Currently selected item
  const selectedItem = useMemo(() => {
    if (!selectedSegmentId) return null;
    return speechItems.find((item) => item.id === selectedSegmentId) || timelineItems.find((item) => item.id === selectedSegmentId) || null;
  }, [speechItems, timelineItems, selectedSegmentId]);

  // Format seconds to mm:ss or mm:ss.s
  const formatTime = (seconds: number, includeTenths = false): string => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    if (includeTenths) {
      const tenths = Math.floor((seconds % 1) * 10);
      return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${tenths}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Determine dynamic ruler tick intervals based on pixelsPerSecond scale
  const rulerTicks = useMemo(() => {
    let step = 10;
    let minorStep = 2;
    if (pxPerSec >= 50) {
      step = 1;
      minorStep = 0.2;
    } else if (pxPerSec >= 25) {
      step = 2;
      minorStep = 0.5;
    } else if (pxPerSec >= 12) {
      step = 5;
      minorStep = 1;
    } else if (pxPerSec >= 6) {
      step = 10;
      minorStep = 2;
    } else if (pxPerSec >= 2) {
      step = 30;
      minorStep = 5;
    } else {
      step = 60;
      minorStep = 10;
    }

    const ticks: { time: number; isMajor: boolean; label?: string }[] = [];
    const count = Math.ceil(totalDuration / minorStep);

    for (let i = 0; i <= count; i++) {
      const t = i * minorStep;
      if (t > totalDuration + 0.1) break;
      const isMajor = Math.abs(t % step) < 0.001 || Math.abs(t % step - step) < 0.001;
      ticks.push({
        time: t,
        isMajor,
        label: isMajor ? formatTime(t) : undefined,
      });
    }
    return ticks;
  }, [totalDuration, pxPerSec]);

  // Click & scrub handler on ruler/timeline
  const handleSeekFromClientX = useCallback(
    (clientX: number) => {
      if (!scrollRef.current) return;
      const rect = scrollRef.current.getBoundingClientRect();
      const clickX = clientX - rect.left + scrollRef.current.scrollLeft;
      const targetTime = Math.max(0, Math.min(totalDuration, clickX / pxPerSec));
      onSeek(targetTime);
    },
    [totalDuration, pxPerSec, onSeek]
  );

  const handleMouseDown = (e: React.MouseEvent) => {
    // Left mouse button only
    if (e.button !== 0) return;
    setIsScrubbing(true);
    handleSeekFromClientX(e.clientX);
  };

  useEffect(() => {
    if (!isScrubbing) return;

    const handleMouseMove = (e: MouseEvent) => {
      handleSeekFromClientX(e.clientX);
    };

    const handleMouseUp = () => {
      setIsScrubbing(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isScrubbing, handleSeekFromClientX]);

  // Hover indicator tracking
  const handleMouseMoveRuler = (e: React.MouseEvent) => {
    if (!scrollRef.current) return;
    const rect = scrollRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left + scrollRef.current.scrollLeft;
    const t = Math.max(0, Math.min(totalDuration, x / pxPerSec));
    setHoverTime(t);
  };

  const handleMouseLeaveRuler = () => {
    setHoverTime(null);
  };

  // Zoom handlers
  const handleZoomIn = () => {
    setZoomFactor((prev) => Math.min(5.0, Number((prev * 1.35).toFixed(2))));
  };

  const handleZoomOut = () => {
    setZoomFactor((prev) => Math.max(1.0, Number((prev / 1.35).toFixed(2))));
  };

  const handleZoomFit = () => {
    setZoomFactor(1.0);
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = 0;
    }
  };

  // Auto-scroll playhead into view during playback when zoomed in
  useEffect(() => {
    if (!isPlaying || zoomFactor <= 1.0 || !scrollRef.current) return;
    const playheadPx = currentTime * pxPerSec;
    const scrollLeft = scrollRef.current.scrollLeft;
    const viewWidth = scrollRef.current.clientWidth;

    if (playheadPx > scrollLeft + viewWidth - 50) {
      scrollRef.current.scrollLeft = playheadPx - 80;
    } else if (playheadPx < scrollLeft) {
      scrollRef.current.scrollLeft = Math.max(0, playheadPx - 80);
    }
  }, [currentTime, isPlaying, zoomFactor, pxPerSec]);

  // Current playhead pixel position
  const playheadX = Math.max(0, Math.min(contentWidth, currentTime * pxPerSec));
  const hoverX = hoverTime !== null ? Math.max(0, Math.min(contentWidth, hoverTime * pxPerSec)) : null;

  // Conflicts count for quick badge
  const conflictsCount = timingConflicts.length;

  return (
    <div
      ref={containerRef}
      data-testid="dubbing-timeline"
      className="bg-slate-950 rounded-2xl border border-slate-800 shadow-xl overflow-hidden text-slate-200 select-none transition-all"
    >
      {/* Top Header Bar: Title, Duration, Legend, Zoom Controls, Collapse */}
      <div className="px-4 py-2.5 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Left: Title & Milestones */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-indigo-400" />
            <span className="font-semibold text-white tracking-wide">Dubbing Timeline</span>
          </div>

          <div className="flex items-center gap-1.5 font-mono text-[11px] bg-slate-800 px-2.5 py-0.5 rounded-full border border-slate-700 text-slate-300">
            <Clock className="w-3 h-3 text-slate-400" />
            <span>{formatTime(currentTime, true)}</span>
            <span className="text-slate-500">/</span>
            <span>{formatTime(totalDuration, true)}</span>
          </div>

          {conflictsCount > 0 ? (
            <button
              onClick={() => {
                const firstConflict = speechItems.find((i) => i.status === 'conflict');
                if (firstConflict) {
                  onSeek(firstConflict.start);
                  onSelectSegment(firstConflict.id);
                }
              }}
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 font-semibold text-[11px] hover:bg-rose-500/30 transition"
              title="Click to jump to first conflict"
            >
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              <span>{conflictsCount} Timing Conflict{conflictsCount > 1 ? 's' : ''}</span>
            </button>
          ) : (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 text-[11px] font-medium">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span>Timing Synchronized</span>
            </span>
          )}
        </div>

        {/* Middle: Color Legend */}
        <div className="hidden md:flex items-center gap-3 text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Fits Natural</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span>Speed Adjusted (0.85-1.15x)</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span>Exceeds Limit</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-slate-500" />
            <span>Missing / Outdated</span>
          </span>
        </div>

        {/* Right: Zoom controls and collapse toggle */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div className="flex items-center bg-slate-800 rounded-lg border border-slate-700 p-0.5">
            <button
              onClick={handleZoomOut}
              disabled={zoomFactor <= 1.0}
              className="p-1 rounded text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none transition"
              title="Zoom Out (-)"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>

            <span className="px-2 text-[10px] font-mono text-slate-300 min-w-10 text-center font-medium">
              {zoomFactor === 1.0 ? 'Fit' : `${zoomFactor.toFixed(1)}x`}
            </span>

            <button
              onClick={handleZoomIn}
              disabled={zoomFactor >= 5.0}
              className="p-1 rounded text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-30 disabled:pointer-events-none transition"
              title="Zoom In (+)"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={handleZoomFit}
            className={`p-1.5 rounded-lg border text-xs flex items-center gap-1 transition ${
              zoomFactor === 1.0
                ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
            }`}
            title="Fit Entire Video in View"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline text-[11px]">Fit Video</span>
          </button>

          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-400 hover:text-white transition"
            title={isCollapsed ? 'Expand Timeline' : 'Collapse Timeline'}
          >
            {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Collapsed Compact Preview Bar */}
      {isCollapsed && (
        <div className="px-4 py-2.5 bg-slate-950 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="text-slate-300 font-medium">Timeline Minimized:</span>
            <span>{transcriptSegments.length} Segments</span>
            <span>•</span>
            <span className="font-mono">{formatTime(currentTime, true)}</span>
          </div>
          <button
            onClick={() => setIsCollapsed(false)}
            className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
          >
            Show Tracks & Ruler
          </button>
        </div>
      )}

      {/* Main Expanded Multi-Track Timeline Content */}
      {!isCollapsed && (
        <div className="flex flex-col">
          {/* Timeline Multi-track Container with Fixed Track Headers on Left & Scrollable Tracks on Right */}
          <div className="flex border-b border-slate-800 relative bg-slate-950">
            {/* Left Column: Static Track Labels */}
            <div
              style={{ width: `${trackLabelWidth}px` }}
              className="shrink-0 border-r border-slate-800/80 bg-slate-900/90 flex flex-col z-20"
            >
              {/* Ruler header */}
              <div className="h-6 px-2.5 flex items-center border-b border-slate-800 text-[10px] font-mono text-slate-400 font-semibold">
                Time
              </div>

              {/* Video track header */}
              <div className="h-5 px-2.5 flex items-center gap-1.5 border-b border-slate-800/80 text-[10px] text-slate-400">
                <Film className="w-3 h-3 text-slate-400" />
                <span className="font-medium truncate">Video</span>
              </div>

              {/* English Transcript track header */}
              <div className="h-10 px-2.5 flex items-center gap-1.5 border-b border-slate-800/80 text-[11px] text-slate-300">
                <span className="w-4 h-4 rounded bg-indigo-500/20 text-indigo-300 font-bold text-[9px] flex items-center justify-center border border-indigo-500/30">
                  EN
                </span>
                <span className="font-medium truncate">English</span>
              </div>

              {/* Khmer Speech track header */}
              <div className="h-12 px-2.5 flex items-center gap-1.5 text-[11px] text-slate-300">
                <span className="w-4 h-4 rounded bg-emerald-500/20 text-emerald-300 font-bold text-[9px] flex items-center justify-center border border-emerald-500/30">
                  KM
                </span>
                <div className="flex flex-col leading-tight min-w-0">
                  <span className="font-medium truncate">Khmer</span>
                  <span className="text-[9px] text-slate-500">Audio TTS</span>
                </div>
              </div>
            </div>

            {/* Right Column: Scrollable Tracks & Time Ruler Area */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-x-auto relative scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900"
              style={{ maxHeight: '280px' }}
            >
              {/* Timeline Canvas Board */}
              <div
                style={{ width: `${contentWidth}px` }}
                className="relative cursor-pointer select-none"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMoveRuler}
                onMouseLeave={handleMouseLeaveRuler}
              >
                {/* 1. Time Ruler */}
                <div className="h-6 border-b border-slate-800 relative bg-slate-900/60 overflow-hidden">
                  {rulerTicks.map((tick, idx) => {
                    const tickLeft = tick.time * pxPerSec;
                    return (
                      <div
                        key={idx}
                        style={{ left: `${tickLeft}px` }}
                        className="absolute top-0 bottom-0 pointer-events-none flex flex-col justify-between"
                      >
                        <div
                          className={`w-px ${
                            tick.isMajor ? 'h-3 bg-slate-500' : 'h-1.5 bg-slate-700'
                          }`}
                        />
                        {tick.label && (
                          <span className="text-[9px] font-mono text-slate-400 pl-1 leading-none pb-0.5">
                            {tick.label}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* 2. Video Duration Track */}
                <div className="h-5 border-b border-slate-800/80 relative bg-slate-900/30 flex items-center px-1">
                  <div
                    style={{ width: `${Math.min(contentWidth, totalDuration * pxPerSec)}px` }}
                    className="h-2 rounded bg-gradient-to-r from-slate-700 to-slate-600 border border-slate-600 flex items-center px-2"
                  >
                    <span className="text-[9px] font-mono text-slate-300">
                      Total: {formatTime(totalDuration)}
                    </span>
                  </div>
                </div>

                {/* 3. English Transcript Track */}
                <div className="h-10 border-b border-slate-800/80 relative bg-slate-950/80 p-0.5">
                  {timelineItems.map((item) => {
                    const left = item.start * pxPerSec;
                    const width = Math.max(16, (item.end - item.start) * pxPerSec);
                    const isSelected = selectedSegmentId === item.id;
                    const isActive = currentTime >= item.start && currentTime <= item.end;

                    return (
                      <div
                        key={item.id}
                        data-testid={`en-segment-${item.order}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSeek(item.start);
                          onSelectSegment(item.id);
                        }}
                        style={{
                          left: `${left}px`,
                          width: `${width}px`,
                        }}
                        className={`absolute top-1 bottom-1 rounded-md px-1.5 text-[10px] flex items-center gap-1 cursor-pointer transition overflow-hidden border shadow-xs ${
                          isSelected
                            ? 'bg-indigo-600 text-white border-indigo-300 ring-2 ring-indigo-400/80 z-10'
                            : isActive
                            ? 'bg-indigo-900/80 text-indigo-100 border-indigo-500 ring-1 ring-indigo-500'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
                        }`}
                        title={`#${item.order} [${formatTime(item.start, true)} - ${formatTime(item.end, true)}]: ${item.transcriptText}`}
                      >
                        <span className="font-mono font-bold shrink-0 opacity-80">#{item.order}</span>
                        {item.speakerLabel && (
                          <span className="font-mono text-[9px] px-1 py-0.2 rounded bg-white/20 text-white font-semibold shrink-0">
                            {item.speakerLabel.replace('SPEAKER_', 'S')}
                          </span>
                        )}
                        <span className="truncate">{item.transcriptText}</span>
                      </div>
                    );
                  })}
                </div>

                {/* 4. Khmer Speech Track */}
                <div className="h-12 relative bg-slate-950/60 p-0.5">
                  {speechItems.map((item) => {
                    const left = item.start * pxPerSec;
                    const width = Math.max(18, item.speechDuration * pxPerSec);
                    const isSelected = selectedSegmentId === item.id;
                    const isActive = currentTime >= item.start && currentTime <= item.start + item.speechDuration;

                    // Choose styling based on backend timing state
                    let trackStyle = '';
                    let statusIcon = null;
                    let badgeText = '';

                    switch (item.status) {
                      case 'conflict':
                        trackStyle = 'bg-rose-500/85 text-white border-rose-400 hover:bg-rose-500';
                        statusIcon = <AlertTriangle className="w-3 h-3 text-rose-100 shrink-0" />;
                        badgeText = `+${item.overflowSeconds.toFixed(1)}s`;
                        break;
                      case 'speed_adjusted':
                        trackStyle = 'bg-amber-500/80 text-amber-950 border-amber-300 hover:bg-amber-500';
                        statusIcon = <Clock className="w-3 h-3 text-amber-950 shrink-0" />;
                        badgeText = `${item.tempoFactor.toFixed(2)}x`;
                        break;
                      case 'fit':
                        trackStyle = 'bg-emerald-600/80 text-white border-emerald-400 hover:bg-emerald-600';
                        statusIcon = <CheckCircle2 className="w-3 h-3 text-emerald-200 shrink-0" />;
                        badgeText = `${item.speechDuration.toFixed(1)}s`;
                        break;
                      case 'outdated':
                        trackStyle = 'bg-slate-700 text-slate-300 border-dashed border-slate-500';
                        statusIcon = <RotateCcw className="w-3 h-3 text-slate-400 shrink-0" />;
                        badgeText = 'Outdated';
                        break;
                      case 'no_audio':
                      default:
                        trackStyle = 'bg-slate-800/60 text-slate-400 border-dashed border-slate-700';
                        badgeText = 'No Audio';
                        break;
                    }

                    return (
                      <div
                        key={item.id}
                        data-testid={`km-segment-${item.order}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSeek(item.start);
                          onSelectSegment(item.id);
                        }}
                        style={{
                          left: `${left}px`,
                          width: `${width}px`,
                        }}
                        className={`absolute top-1 bottom-1 rounded-md px-1.5 text-[10px] flex items-center justify-between gap-1 cursor-pointer transition overflow-hidden border shadow-xs ${trackStyle} ${
                          isSelected ? 'ring-2 ring-white z-10 font-semibold' : isActive ? 'ring-1 ring-white/60' : ''
                        }`}
                        title={`Khmer #${item.order} (${item.status.toUpperCase()}) Duration: ${item.speechDuration.toFixed(2)}s. ${item.alignmentNote ?? ''} Click to inspect.`}
                      >
                        <div className="flex items-center gap-1 min-w-0">
                          {statusIcon}
                          <span className="font-mono font-bold shrink-0">#{item.order}</span>
                          {item.speakerLabel && (
                            <span className="font-mono text-[9px] px-1 py-0.2 rounded bg-black/25 font-semibold shrink-0">
                              {item.speakerLabel.replace('SPEAKER_', 'S')}
                            </span>
                          )}
                          {item.khmerText && (
                            <span className="font-khmer truncate text-[11px] opacity-90 hidden sm:inline">
                              {item.khmerText}
                            </span>
                          )}
                        </div>

                        <span className="font-mono text-[9px] px-1 py-0.2 rounded bg-black/30 shrink-0">
                          {badgeText}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Vertical Playhead Needle Indicator */}
                <div
                  data-testid="timeline-playhead"
                  style={{
                    left: `${playheadX}px`,
                    transform: 'translateX(-50%)',
                  }}
                  className="absolute top-0 bottom-0 pointer-events-none z-30 flex flex-col items-center"
                >
                  {/* Top needle head bubble */}
                  <div className="px-1.5 py-0.5 rounded bg-indigo-500 text-white font-mono text-[9px] font-bold shadow-md whitespace-nowrap -mt-1 leading-none">
                    {formatTime(currentTime, true)}
                  </div>
                  {/* Vertical line through all tracks */}
                  <div className="w-0.5 flex-1 bg-indigo-400 shadow-sm" />
                </div>

                {/* Mouse Hover Position Indicator */}
                {hoverX !== null && !isScrubbing && (
                  <div
                    style={{
                      left: `${hoverX}px`,
                      transform: 'translateX(-50%)',
                    }}
                    className="absolute top-0 bottom-0 pointer-events-none z-20 flex flex-col items-center opacity-60"
                  >
                    <div className="px-1 py-0.2 rounded bg-slate-700 text-slate-200 font-mono text-[8px] -mt-0.5">
                      {formatTime(hoverTime || 0, true)}
                    </div>
                    <div className="w-px flex-1 bg-slate-400 border-dashed" />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Bottom Contextual Inspection Banner (When a segment is selected) */}
          {selectedItem && (
            <div
              data-testid="timeline-inspection-bar"
              className="px-4 py-2.5 bg-slate-900 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs animate-fadeIn"
            >
              {/* Left: Selected Segment Details */}
              <div className="flex flex-wrap items-center gap-2.5 min-w-0">
                <span className="font-mono font-bold text-white bg-indigo-600/30 border border-indigo-500/40 px-2 py-0.5 rounded">
                  Segment #{selectedItem.order}
                </span>

                <span className="font-mono text-slate-300 text-[11px]">
                  [{formatTime(selectedItem.start, true)} - {formatTime(selectedItem.end, true)}]
                </span>

                {/* Status Capsule */}
                {selectedItem.status === 'conflict' && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[11px] font-semibold">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span>Overflow by {selectedItem.overflowSeconds.toFixed(2)}s (Exceeds available window)</span>
                  </span>
                )}
                {selectedItem.status === 'speed_adjusted' && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[11px] font-medium">
                    <Clock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>Speed Adjusted ({selectedItem.tempoFactor.toFixed(2)}x tempo)</span>
                  </span>
                )}
                {selectedItem.status === 'fit' && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[11px] font-medium">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <span>Fits speech window naturally ({selectedItem.speechDuration.toFixed(2)}s)</span>
                  </span>
                )}
                {selectedItem.status === 'outdated' && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[11px]">
                    <RotateCcw className="w-3.5 h-3.5 shrink-0" />
                    <span>Audio Outdated (needs regeneration)</span>
                  </span>
                )}
                {selectedItem.status === 'no_audio' && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[11px]">
                    <Volume2 className="w-3.5 h-3.5 shrink-0" />
                    <span>No Audio Generated Yet</span>
                  </span>
                )}
              </div>

              {/* Right: Quick Actions */}
              <div className="flex items-center gap-2 shrink-0">
                {/* AI Shorten Action (if conflict) */}
                {selectedItem.status === 'conflict' && selectedItem.translationSegment && onOpenAIImprove && (
                  <button
                    data-testid="timeline-ai-shorten-btn"
                    onClick={() => onOpenAIImprove(selectedItem.translationSegment!)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs transition shadow-xs"
                    title="Open AI shortening assistant to trim excess words"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                    <span>AI Shorten</span>
                  </button>
                )}

                {/* Edit in Translation Tab Action */}
                {onNavigateToTranslation && (
                  <button
                    data-testid="timeline-edit-translation-btn"
                    onClick={() => onNavigateToTranslation(selectedItem.id)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-slate-700 font-medium text-xs transition"
                    title="Navigate to Translation Tab to edit text"
                  >
                    <Languages className="w-3.5 h-3.5" />
                    <span>Edit Translation</span>
                    <ArrowRight className="w-3 h-3 text-slate-400 ml-0.5" />
                  </button>
                )}

                {/* Edit in Subtitle Tab Action */}
                {onNavigateToSubtitles && (
                  <button
                    data-testid="timeline-edit-subtitles-btn"
                    onClick={() => onNavigateToSubtitles(selectedItem.id)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 font-medium text-xs transition"
                    title="Navigate to Subtitles Tab to format captions & line breaks"
                  >
                    <Subtitles className="w-3.5 h-3.5" />
                    <span>Edit Subtitles</span>
                  </button>
                )}

                {/* Close selection */}
                <button
                  onClick={() => onSelectSegment('')}
                  className="px-2 py-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 text-xs"
                  title="Deselect segment"
                >
                  ✕
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
