import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Scissors,
  Play,
  Pause,
  RotateCcw,
  Download,
  Film,
  Layers,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Clock,
  HardDrive,
  FileVideo,
  Upload,
  FolderGit2,
  X,
  Zap,
  Sliders,
  Check,
} from 'lucide-react';
import { api } from '../../services/api';
import { formatTimestamp, parseTimestamp, formatShortDuration, clamp } from '../../utils/time';
import {
  ToolkitTask,
  ProjectSummary,
  TrimmerMediaInfo,
} from '../../types';

interface VideoTrimmerProps {
  tasks: ToolkitTask[];
  projects: ProjectSummary[];
  onTaskCompleted: (task: ToolkitTask) => void;
  onNavigateToTool: (toolId: string) => void;
  initialSourceTaskId?: string | null;
}

export const VideoTrimmer: React.FC<VideoTrimmerProps> = ({
  tasks,
  projects,
  onTaskCompleted,
  onNavigateToTool,
  initialSourceTaskId,
}) => {
  // Source Selection
  const [sourceMode, setSourceMode] = useState<'upload' | 'task' | 'project'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string>(initialSourceTaskId || '');
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  
  // Media Inspection & Info
  const [mediaInfo, setMediaInfo] = useState<TrimmerMediaInfo | null>(null);
  const [mediaSourceUrl, setMediaSourceUrl] = useState<string | null>(null);
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [inspectError, setInspectError] = useState<string | null>(null);
  const [thumbnails, setThumbnails] = useState<string[]>([]);

  // Player & Timeline State
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(0);

  // Selection Range
  const [startTime, setStartTime] = useState<number>(0);
  const [endTime, setEndTime] = useState<number>(0);
  const [startInputText, setStartInputText] = useState<string>('00:00:00.000');
  const [endInputText, setEndInputText] = useState<string>('00:00:00.000');
  const [isPreviewingSelection, setIsPreviewingSelection] = useState<boolean>(false);
  const isPreviewingRef = useRef<boolean>(false);

  // Dragging State: 'start' | 'end' | 'playhead' | null
  const [draggingHandle, setDraggingHandle] = useState<'start' | 'end' | 'playhead' | null>(null);

  // Trimming Settings
  const [trimMode, setTrimMode] = useState<'precise' | 'fast'>('precise');
  const [isTrimming, setIsTrimming] = useState<boolean>(false);
  const [trimError, setTrimError] = useState<string | null>(null);
  const [activeTrimmingTaskId, setActiveTrimmingTaskId] = useState<string | null>(null);
  const [completedTask, setCompletedTask] = useState<ToolkitTask | null>(null);

  // Handoff & Import state
  const [isImportingDubbing, setIsImportingDubbing] = useState<boolean>(false);
  const [dubbingTitle, setDubbingTitle] = useState<string>('');
  const [showDubbingModal, setShowDubbingModal] = useState<boolean>(false);
  const [dubbingSuccessProject, setDubbingSuccessProject] = useState<{ id: string; title: string } | null>(null);
  const [handoffLoading, setHandoffLoading] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Filter tasks that have video media
  const videoTasks = tasks.filter((t) => {
    if (t.status !== 'completed') return false;
    if (t.tool_type === 'video_downloader') {
      try {
        const meta = typeof t.output_media_metadata === 'string'
          ? JSON.parse(t.output_media_metadata)
          : (t.output_media_metadata || {});
        if (meta.output_type === 'audio') return false;
      } catch {}
      return true;
    }
    return t.tool_type === 'video_trimmer' || t.output_filename?.endsWith('.mp4');
  });

  // Load initial source task if supplied
  const initialSourceAppliedRef = useRef(false);
  useEffect(() => {
    if (!initialSourceAppliedRef.current && initialSourceTaskId) {
      initialSourceAppliedRef.current = true;
      setSourceMode('task');
      setSelectedTaskId(initialSourceTaskId);
    }
  }, [initialSourceTaskId]);

  // Inspect source when selection changes
  const handleInspect = useCallback(
    async (
      file: File | null,
      taskId: string | null,
      projId: string | null
    ) => {
      if (!file && !taskId && !projId) {
        setMediaInfo(null);
        setMediaSourceUrl(null);
        setDuration(0);
        return;
      }

      setIsInspecting(true);
      setInspectError(null);
      setThumbnails([]);
      setCompletedTask(null);
      setTrimError(null);

      try {
        const info = await api.inspectTrimmerMedia(file, taskId, projId);
        if (!info.has_video) {
          throw new Error('Selected media has no video track. Please select a video file or use Audio Trimmer.');
        }

        setMediaInfo(info);
        const dur = info.duration_seconds || 0;
        setDuration(dur);
        setStartTime(0);
        setEndTime(dur);
        setStartInputText('00:00:00.000');
        setEndInputText(formatTimestamp(dur));

        // Determine playback source URL
        if (file) {
          const objectUrl = URL.createObjectURL(file);
          setMediaSourceUrl(objectUrl);
        } else if (taskId) {
          setMediaSourceUrl(api.getToolkitAudioStreamUrl(taskId));
        } else if (projId) {
          setMediaSourceUrl(`/api/projects/${projId}/video`);
        }

        // Fetch thumbnails for timeline
        if (taskId || projId) {
          api
            .getTrimmerThumbnails({
              source_task_id: taskId || undefined,
              source_project_id: projId || undefined,
              count: 8,
            })
            .then((thumbs) => setThumbnails(thumbs))
            .catch(() => {});
        }
      } catch (err: any) {
        setInspectError(err.message || 'Failed to inspect video.');
        setMediaInfo(null);
        setMediaSourceUrl(null);
      } finally {
        setIsInspecting(false);
      }
    },
    []
  );

  // Trigger inspection on source changes
  useEffect(() => {
    if (sourceMode === 'upload' && selectedFile) {
      handleInspect(selectedFile, null, null);
    } else if (sourceMode === 'task' && selectedTaskId) {
      handleInspect(null, selectedTaskId, null);
    } else if (sourceMode === 'project' && selectedProjectId) {
      handleInspect(null, null, selectedProjectId);
    }
  }, [sourceMode, selectedFile, selectedTaskId, selectedProjectId, handleInspect]);

  // Clean up Object URL on unmount or file change
  useEffect(() => {
    return () => {
      if (mediaSourceUrl && mediaSourceUrl.startsWith('blob:')) {
        URL.revokeObjectURL(mediaSourceUrl);
      }
    };
  }, [mediaSourceUrl]);

  // Video playback time updates
  const handleTimeUpdate = () => {
    if (!videoRef.current) return;
    const time = videoRef.current.currentTime;
    setCurrentTime(time);

    // If previewing selection and reached end of selection, pause
    if (isPreviewingRef.current && time >= endTime) {
      videoRef.current.pause();
      setIsPlaying(false);
      setIsPreviewingSelection(false);
      isPreviewingRef.current = false;
    }
  };

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
      setIsPreviewingSelection(false);
      isPreviewingRef.current = false;
    } else {
      videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  // Preview only the selected range
  const handlePreviewSelection = () => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = startTime;
    setIsPreviewingSelection(true);
    isPreviewingRef.current = true;
    videoRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
  };

  // Reset selection to full range
  const handleResetSelection = () => {
    setStartTime(0);
    setEndTime(duration);
    setStartInputText('00:00:00.000');
    setEndInputText(formatTimestamp(duration));
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      setCurrentTime(0);
    }
  };

  // Timestamp input blur / change handlers
  const handleStartInputBlur = (e?: React.FocusEvent<HTMLInputElement>) => {
    const val = e ? e.target.value : startInputText;
    const parsed = parseTimestamp(val);
    if (isNaN(parsed) || parsed < 0) {
      setStartInputText(formatTimestamp(startTime));
      return;
    }
    const clamped = clamp(parsed, 0, Math.max(0, endTime - 0.05));
    setStartTime(clamped);
    setStartInputText(formatTimestamp(clamped));
    if (videoRef.current) {
      videoRef.current.currentTime = clamped;
    }
  };

  const handleEndInputBlur = (e?: React.FocusEvent<HTMLInputElement>) => {
    const val = e ? e.target.value : endInputText;
    const parsed = parseTimestamp(val);
    if (isNaN(parsed) || parsed <= 0) {
      setEndInputText(formatTimestamp(endTime));
      return;
    }
    const clamped = clamp(parsed, startTime + 0.05, duration);
    setEndTime(clamped);
    setEndInputText(formatTimestamp(clamped));
    if (videoRef.current) {
      videoRef.current.currentTime = clamped;
    }
  };

  const setStartToCurrent = () => {
    const clamped = clamp(currentTime, 0, Math.max(0, endTime - 0.05));
    setStartTime(clamped);
    setStartInputText(formatTimestamp(clamped));
  };

  const setEndToCurrent = () => {
    const clamped = clamp(currentTime, startTime + 0.05, duration);
    setEndTime(clamped);
    setEndInputText(formatTimestamp(clamped));
  };

  // Timeline Drag & Scrub Handling
  const calculateTimeFromEvent = (e: MouseEvent | TouchEvent | React.MouseEvent | React.TouchEvent): number => {
    if (!timelineRef.current || duration <= 0) return 0;
    const rect = timelineRef.current.getBoundingClientRect();
    const clientX = 'touches' in e ? e.touches[0].clientX : (e as MouseEvent).clientX;
    const fraction = clamp((clientX - rect.left) / rect.width, 0, 1);
    return Math.round(fraction * duration * 1000) / 1000;
  };

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (draggingHandle) return;
    const time = calculateTimeFromEvent(e);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  // Dragging event listeners on window
  useEffect(() => {
    if (!draggingHandle) return;

    const handleMove = (e: MouseEvent | TouchEvent) => {
      const time = calculateTimeFromEvent(e);
      if (draggingHandle === 'start') {
        const clamped = clamp(time, 0, Math.max(0, endTime - 0.1));
        setStartTime(clamped);
        setStartInputText(formatTimestamp(clamped));
        if (videoRef.current) {
          videoRef.current.currentTime = clamped;
        }
      } else if (draggingHandle === 'end') {
        const clamped = clamp(time, startTime + 0.1, duration);
        setEndTime(clamped);
        setEndInputText(formatTimestamp(clamped));
        if (videoRef.current) {
          videoRef.current.currentTime = clamped;
        }
      } else if (draggingHandle === 'playhead') {
        if (videoRef.current) {
          videoRef.current.currentTime = time;
          setCurrentTime(time);
        }
      }
    };

    const handleUp = () => {
      setDraggingHandle(null);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    window.addEventListener('touchmove', handleMove);
    window.addEventListener('touchend', handleUp);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
      window.removeEventListener('touchmove', handleMove);
      window.removeEventListener('touchend', handleUp);
    };
  }, [draggingHandle, startTime, endTime, duration]);

  // Execute Trim
  const handleExecuteTrim = async () => {
    if (!mediaInfo || duration <= 0) return;
    if (endTime <= startTime) {
      setTrimError('End time must be greater than start time.');
      return;
    }

    setIsTrimming(true);
    setTrimError(null);
    setCompletedTask(null);

    try {
      const task = await api.executeTrim({
        tool_type: 'video_trimmer',
        start_time: formatTimestamp(startTime),
        end_time: formatTimestamp(endTime),
        trim_mode: trimMode,
        target_format: 'mp4',
        cached_upload_path: mediaInfo.cached_upload_path || undefined,
        source_task_id: selectedTaskId || mediaInfo.source_task_id || undefined,
        source_project_id: selectedProjectId || mediaInfo.source_project_id || undefined,
        file: sourceMode === 'upload' && !mediaInfo.cached_upload_path ? (selectedFile || undefined) : undefined,
      });

      setActiveTrimmingTaskId(task.id);
      setCompletedTask(task);
      onTaskCompleted(task);
    } catch (err: any) {
      console.error('[VideoTrimmer] executeTrim caught error:', err);
      setTrimError(err.message || 'Trimming failed.');
    } finally {
      setIsTrimming(false);
      setActiveTrimmingTaskId(null);
    }
  };

  // Cancel Trim
  const handleCancelTrim = async () => {
    if (!activeTrimmingTaskId) return;
    try {
      await api.cancelTrimmerTask(activeTrimmingTaskId);
      setIsTrimming(false);
      setActiveTrimmingTaskId(null);
      setTrimError('Trimming was cancelled.');
    } catch {}
  };

  // Import to Dubbing Studio
  const handleImportDubbing = async () => {
    if (!completedTask) return;
    setIsImportingDubbing(true);
    try {
      const res = await api.importTrimmerToDubbing(completedTask.id, {
        title: dubbingTitle.trim() || undefined,
      });
      setDubbingSuccessProject({ id: res.project_id, title: res.title });
      setShowDubbingModal(false);
    } catch (err: any) {
      alert(`Dubbing import failed: ${err.message}`);
    } finally {
      setIsImportingDubbing(false);
    }
  };

  // Media Handoff
  const handleHandoff = async (targetTool: string) => {
    if (!completedTask) return;
    setHandoffLoading(targetTool);
    try {
      const newTask = await api.handoffTrimmerTask(completedTask.id, targetTool);
      onTaskCompleted(newTask);
      onNavigateToTool(targetTool);
    } catch (err: any) {
      alert(`Failed to transfer to ${targetTool}: ${err.message}`);
    } finally {
      setHandoffLoading(null);
    }
  };

  // Percent calculations for visual handles
  const startPercent = duration > 0 ? (startTime / duration) * 100 : 0;
  const endPercent = duration > 0 ? (endTime / duration) * 100 : 100;
  const currentPercent = duration > 0 ? (currentTime / duration) * 100 : 0;
  const selectionDuration = Math.max(0, endTime - startTime);

  return (
    <div className="space-y-6">
      {/* Workspace Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Scissors className="w-5 h-5 text-indigo-600" />
            <span>Video Trimmer</span>
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Trim videos to keep only the sections you need with exact frame precision.
          </p>
        </div>

        {/* Source Mode Tabs */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl text-xs font-semibold">
          <button
            onClick={() => setSourceMode('upload')}
            className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1.5 ${
              sourceMode === 'upload'
                ? 'bg-white text-indigo-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Upload File</span>
          </button>
          <button
            onClick={() => setSourceMode('task')}
            className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1.5 ${
              sourceMode === 'task'
                ? 'bg-white text-indigo-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Toolkit Tasks</span>
          </button>
          <button
            onClick={() => setSourceMode('project')}
            className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1.5 ${
              sourceMode === 'project'
                ? 'bg-white text-indigo-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FolderGit2 className="w-3.5 h-3.5" />
            <span>Projects</span>
          </button>
        </div>
      </div>

      {/* Input Selector Section */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 sm:p-5">
        {sourceMode === 'upload' && (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime,video/x-msvideo,.mp4,.webm,.mov,.avi,.mkv"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setSelectedFile(e.target.files[0]);
                }
              }}
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-300 hover:border-indigo-400 rounded-xl p-6 text-center cursor-pointer transition-colors bg-white group"
            >
              <FileVideo className="w-10 h-10 text-slate-400 group-hover:text-indigo-600 mx-auto transition-colors" />
              <p className="mt-2 text-sm font-semibold text-slate-700">
                {selectedFile ? selectedFile.name : 'Click or drop video to upload'}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Supports MP4, WebM, MOV, and common video formats (up to 500 MB)
              </p>
            </div>
          </div>
        )}

        {sourceMode === 'task' && (
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700 block">
              Select Completed Toolkit Video Task:
            </label>
            <select
              value={selectedTaskId}
              onChange={(e) => setSelectedTaskId(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">-- Choose a completed task --</option>
              {videoTasks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.source_filename || t.output_filename || t.id.slice(0, 8)} ({t.tool_type}) -{' '}
                  {formatShortDuration(t.output_duration_seconds)}
                </option>
              ))}
            </select>
            {videoTasks.length === 0 && (
              <p className="text-xs text-slate-500">
                No completed video tasks found. Download or trim a video first, or switch to Upload tab.
              </p>
            )}
          </div>
        )}

        {sourceMode === 'project' && (
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-700 block">
              Select Video from Existing Project:
            </label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">-- Choose a project --</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title} ({p.original_language} → {p.target_language})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Inspection Loading or Error */}
        {isInspecting && (
          <div className="mt-4 p-3 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center gap-2 text-xs text-indigo-700 font-medium">
            <div className="w-4 h-4 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            <span>Analyzing media stream and extracting timeline information...</span>
          </div>
        )}

        {inspectError && (
          <div className="mt-4 p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-2 text-xs text-rose-700">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
            <span>{inspectError}</span>
          </div>
        )}
      </div>

      {/* Interactive Trimmer Workspace (Rendered when mediaInfo is loaded) */}
      {mediaInfo && mediaSourceUrl && (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-6">
          {/* Media Info Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-slate-50 p-3 rounded-xl border border-slate-100">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-800">{mediaInfo.source_filename}</span>
              {mediaInfo.width && mediaInfo.height && (
                <span className="px-2 py-0.5 rounded-md bg-slate-200 text-slate-700 font-mono text-[11px]">
                  {mediaInfo.width}x{mediaInfo.height}
                </span>
              )}
              {mediaInfo.video_codec && (
                <span className="px-2 py-0.5 rounded-md bg-slate-200 text-slate-700 font-mono text-[11px]">
                  {mediaInfo.video_codec}
                </span>
              )}
            </div>

            <div className="flex items-center gap-4 text-slate-500">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>Total: {formatTimestamp(duration)}</span>
              </span>
              <span className="flex items-center gap-1">
                <HardDrive className="w-3.5 h-3.5 text-slate-400" />
                <span>{(mediaInfo.size_bytes / (1024 * 1024)).toFixed(2)} MB</span>
              </span>
            </div>
          </div>

          {/* Video Player Display */}
          <div className="relative rounded-2xl overflow-hidden bg-black aspect-video max-h-[460px] mx-auto flex items-center justify-center shadow-inner group">
            <video
              ref={videoRef}
              src={mediaSourceUrl}
              className="w-full h-full object-contain cursor-pointer"
              onClick={togglePlay}
              onTimeUpdate={handleTimeUpdate}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
            />

            {/* Big Center Play/Pause button on hover */}
            <button
              onClick={togglePlay}
              className="absolute inset-0 m-auto w-14 h-14 rounded-full bg-black/60 hover:bg-black/80 text-white flex items-center justify-center transition-opacity opacity-0 group-hover:opacity-100 cursor-pointer shadow-lg"
            >
              {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
            </button>

            {/* Bottom Floating Time Pill */}
            <div className="absolute bottom-3 right-3 px-2.5 py-1 rounded-lg bg-black/75 backdrop-blur-xs text-white text-[11px] font-mono tracking-wider pointer-events-none">
              {formatTimestamp(currentTime)} / {formatTimestamp(duration)}
            </div>
          </div>

          {/* Visual Timeline Bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
              <span>Timeline</span>
              <span className="font-mono text-indigo-600 font-semibold">
                Selection: {formatTimestamp(startTime)} → {formatTimestamp(endTime)} (
                {formatShortDuration(selectionDuration)})
              </span>
            </div>

            <div
              ref={timelineRef}
              onClick={handleTimelineClick}
              className="relative h-16 bg-slate-900 rounded-xl overflow-hidden cursor-pointer select-none shadow-inner border border-slate-700"
            >
              {/* Optional Thumbnails Row */}
              {thumbnails.length > 0 && (
                <div className="absolute inset-0 flex opacity-60 pointer-events-none">
                  {thumbnails.map((thumb, idx) => (
                    <img
                      key={idx}
                      src={thumb}
                      alt=""
                      className="h-full flex-1 object-cover border-r border-slate-800 last:border-r-0"
                    />
                  ))}
                </div>
              )}

              {/* Dimmed Region Left of Selection */}
              <div
                className="absolute top-0 bottom-0 left-0 bg-black/60 pointer-events-none z-10"
                style={{ width: `${startPercent}%` }}
              />

              {/* Selected Highlight Window */}
              <div
                className="absolute top-0 bottom-0 bg-indigo-500/25 border-y-2 border-indigo-400 pointer-events-none z-10 shadow-sm"
                style={{
                  left: `${startPercent}%`,
                  width: `${Math.max(0, endPercent - startPercent)}%`,
                }}
              />

              {/* Dimmed Region Right of Selection */}
              <div
                className="absolute top-0 bottom-0 right-0 bg-black/60 pointer-events-none z-10"
                style={{ width: `${100 - endPercent}%` }}
              />

              {/* Start Handle */}
              <div
                onMouseDown={(e) => {
                  e.stopPropagation();
                  setDraggingHandle('start');
                }}
                onTouchStart={(e) => {
                  e.stopPropagation();
                  setDraggingHandle('start');
                }}
                style={{ left: `${startPercent}%` }}
                className="absolute top-0 bottom-0 -ml-2.5 w-5 bg-indigo-600 hover:bg-indigo-500 z-30 cursor-ew-resize flex items-center justify-center rounded-l-md shadow-md transition-colors"
                title="Drag Start Handle"
              >
                <div className="w-1 h-6 bg-white/80 rounded-full" />
              </div>

              {/* End Handle */}
              <div
                onMouseDown={(e) => {
                  e.stopPropagation();
                  setDraggingHandle('end');
                }}
                onTouchStart={(e) => {
                  e.stopPropagation();
                  setDraggingHandle('end');
                }}
                style={{ left: `${endPercent}%` }}
                className="absolute top-0 bottom-0 -mr-2.5 w-5 bg-indigo-600 hover:bg-indigo-500 z-30 cursor-ew-resize flex items-center justify-center rounded-r-md shadow-md transition-colors"
                title="Drag End Handle"
              >
                <div className="w-1 h-6 bg-white/80 rounded-full" />
              </div>

              {/* Current Playhead Line */}
              <div
                onMouseDown={(e) => {
                  e.stopPropagation();
                  setDraggingHandle('playhead');
                }}
                onTouchStart={(e) => {
                  e.stopPropagation();
                  setDraggingHandle('playhead');
                }}
                style={{ left: `${currentPercent}%` }}
                className="absolute top-0 bottom-0 w-0.5 bg-rose-500 z-40 cursor-pointer pointer-events-auto"
              >
                <div className="w-3 h-3 bg-rose-500 rounded-full -ml-[5px] -mt-1 shadow-xs" />
              </div>
            </div>
          </div>

          {/* Exact Timestamp Controls & Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200">
            {/* Start Timestamp Input */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                <span>Start Time</span>
                <button
                  type="button"
                  onClick={setStartToCurrent}
                  className="text-[11px] text-indigo-600 hover:text-indigo-800 font-normal cursor-pointer"
                  title="Use current playback position"
                >
                  Set to Current
                </button>
              </label>
              <input
                type="text"
                data-testid="video-trim-start-input"
                value={startInputText}
                onChange={(e) => setStartInputText(e.target.value)}
                onBlur={handleStartInputBlur}
                className="w-full px-3 py-1.5 text-sm font-mono bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                placeholder="00:00:00.000"
              />
            </div>

            {/* End Timestamp Input */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                <span>End Time</span>
                <button
                  type="button"
                  onClick={setEndToCurrent}
                  className="text-[11px] text-indigo-600 hover:text-indigo-800 font-normal cursor-pointer"
                  title="Use current playback position"
                >
                  Set to Current
                </button>
              </label>
              <input
                type="text"
                data-testid="video-trim-end-input"
                value={endInputText}
                onChange={(e) => setEndInputText(e.target.value)}
                onBlur={handleEndInputBlur}
                className="w-full px-3 py-1.5 text-sm font-mono bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                placeholder="00:00:00.000"
              />
            </div>

            {/* Selected Duration Badge */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">
                Selected Duration
              </label>
              <div className="px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-900 font-mono text-sm font-bold flex items-center justify-between">
                <span>{formatTimestamp(selectionDuration)}</span>
                <span className="text-[11px] text-indigo-600 font-medium">
                  {formatShortDuration(selectionDuration)}
                </span>
              </div>
            </div>

            {/* Preview & Reset Selection Buttons */}
            <div className="flex items-end gap-2">
              <button
                type="button"
                onClick={handlePreviewSelection}
                className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                  isPreviewingSelection
                    ? 'bg-amber-500 text-white'
                    : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-100 shadow-xs'
                }`}
              >
                <Play className="w-3.5 h-3.5" />
                <span>{isPreviewingSelection ? 'Playing...' : 'Preview Selection'}</span>
              </button>

              <button
                type="button"
                onClick={handleResetSelection}
                className="py-1.5 px-3 rounded-lg bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold flex items-center justify-center gap-1 transition-all cursor-pointer shadow-xs"
                title="Reset to full video"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset</span>
              </button>
            </div>
          </div>

          {/* Export Mode & Action */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2 border-t border-slate-200">
            {/* Fast vs Precise Toggle */}
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-slate-700">Trimming Engine:</span>
              <div className="inline-flex rounded-lg bg-slate-100 p-0.5 text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setTrimMode('precise')}
                  className={`px-3 py-1 rounded-md transition-all cursor-pointer flex items-center gap-1.5 ${
                    trimMode === 'precise'
                      ? 'bg-white text-indigo-600 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  <span>Precise (Re-encode)</span>
                </button>
                <button
                  type="button"
                  onClick={() => setTrimMode('fast')}
                  className={`px-3 py-1 rounded-md transition-all cursor-pointer flex items-center gap-1.5 ${
                    trimMode === 'fast'
                      ? 'bg-white text-indigo-600 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5 text-amber-500" />
                  <span>Fast (Stream Copy)</span>
                </button>
              </div>
            </div>

            {/* Execute Button */}
            <div className="flex items-center gap-2 w-full sm:w-auto">
              {isTrimming && (
                <button
                  type="button"
                  onClick={handleCancelTrim}
                  className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              )}

              <button
                type="button"
                data-testid="video-trim-submit-btn"
                onClick={handleExecuteTrim}
                disabled={isTrimming || selectionDuration <= 0}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-sm font-semibold flex items-center justify-center gap-2 shadow-xs transition-all cursor-pointer disabled:cursor-not-allowed"
              >
                {isTrimming ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Trimming Video...</span>
                  </>
                ) : (
                  <>
                    <Scissors className="w-4 h-4" />
                    <span>Trim Video ({formatShortDuration(selectionDuration)})</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {trimError && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-2 text-xs text-rose-700">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
              <span>{trimError}</span>
            </div>
          )}
        </div>
      )}

      {/* Trimmed Result Card */}
      {completedTask && (
        <div className="bg-white border-2 border-emerald-400 rounded-2xl p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2 text-emerald-700">
              <CheckCircle2 className="w-5 h-5" />
              <span className="font-bold text-sm">Trim Complete!</span>
              <span className="text-xs text-slate-500">({completedTask.output_filename})</span>
            </div>

            <div className="flex items-center gap-2">
              <a
                href={api.getToolkitAudioDownloadUrl(completedTask.id)}
                download={completedTask.output_filename || 'trimmed_video.mp4'}
                className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download MP4</span>
              </a>

              <button
                type="button"
                onClick={() => setShowDubbingModal(true)}
                className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
              >
                <Film className="w-3.5 h-3.5" />
                <span>Import to Dubbing</span>
              </button>
            </div>
          </div>

          {/* Result Video Preview */}
          <div className="rounded-xl overflow-hidden bg-black aspect-video max-h-[360px] mx-auto flex items-center justify-center">
            <video
              controls
              src={api.getToolkitAudioStreamUrl(completedTask.id)}
              className="w-full h-full object-contain"
            />
          </div>

          {/* Result Output Metadata */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center text-xs">
            <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] text-slate-400 uppercase font-semibold block">Duration</span>
              <span className="font-bold text-slate-800">
                {formatShortDuration(completedTask.output_duration_seconds)}
              </span>
            </div>
            <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] text-slate-400 uppercase font-semibold block">File Size</span>
              <span className="font-bold text-slate-800">
                {((completedTask.output_file_size_bytes || 0) / (1024 * 1024)).toFixed(2)} MB
              </span>
            </div>
            <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] text-slate-400 uppercase font-semibold block">Format</span>
              <span className="font-bold text-slate-800 uppercase">
                {completedTask.target_format || 'MP4'}
              </span>
            </div>
            <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-[10px] text-slate-400 uppercase font-semibold block">Status</span>
              <span className="font-bold text-emerald-600 uppercase">Completed</span>
            </div>
          </div>

          {/* Send to Other Media Toolkit Studios */}
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
            <span className="text-xs font-semibold text-slate-700 block">
              Send Trimmed Video to Other Tools:
            </span>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleHandoff('video_to_audio')}
                disabled={handoffLoading !== null}
                className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-400 hover:text-indigo-600 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <span>Extract Audio</span>
                <ArrowRight className="w-3 h-3" />
              </button>
              <button
                type="button"
                onClick={() => handleHandoff('video_to_transcript')}
                disabled={handoffLoading !== null}
                className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-400 hover:text-indigo-600 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <span>Video to Transcript</span>
                <ArrowRight className="w-3 h-3" />
              </button>
              <button
                type="button"
                onClick={() => handleHandoff('video_to_text')}
                disabled={handoffLoading !== null}
                className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:border-indigo-400 hover:text-indigo-600 text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <span>Video to Text</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dubbing Import Modal */}
      {showDubbingModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-900 flex items-center gap-2">
                <Film className="w-5 h-5 text-indigo-600" />
                <span>Import to Video Dubbing</span>
              </h3>
              <button
                onClick={() => setShowDubbingModal(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Create a new KhmerDub AI dubbing project using this trimmed video segment as the source media.
            </p>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">Project Title</label>
              <input
                type="text"
                value={dubbingTitle}
                onChange={(e) => setDubbingTitle(e.target.value)}
                placeholder="Trimmed Video Project"
                className="w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowDubbingModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleImportDubbing}
                disabled={isImportingDubbing}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 cursor-pointer disabled:bg-slate-300"
              >
                {isImportingDubbing ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Importing...</span>
                  </>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>Create Project</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dubbing Success Banner */}
      {dubbingSuccessProject && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-between text-xs text-emerald-800">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>
              Project <strong>{dubbingSuccessProject.title}</strong> created successfully!
            </span>
          </div>
          <a
            href={`#projects`}
            className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold cursor-pointer transition-colors"
          >
            Go to Projects
          </a>
        </div>
      )}
    </div>
  );
};
