import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Video,
  FileAudio,
  FileText,
  AlignLeft,
  ListMusic,
  FileCode,
  Mic2,
  Radio,
  Upload,
  FolderGit2,
  Play,
  Pause,
  Download,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Clock,
  HardDrive,
  Info,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Copy,
  Check,
  Edit2,
  RotateCcw,
  Save,
  X,
  FileCheck,
} from 'lucide-react';
import { api } from '../services/api';
import {
  ProjectSummary,
  ToolkitCapabilities,
  ToolkitTask,
  ToolkitTranscriptSegment,
} from '../types';

interface MediaToolkitProps {
  projects?: ProjectSummary[];
}

export const MediaToolkit: React.FC<MediaToolkitProps> = ({ projects = [] }) => {
  const [capabilities, setCapabilities] = useState<ToolkitCapabilities | null>(null);
  const [selectedTool, setSelectedTool] = useState<string>('video_to_audio');
  const [showLanguageInfo, setShowLanguageInfo] = useState<boolean>(false);

  // Common Input State
  const [inputMode, setInputMode] = useState<'upload' | 'project'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>('');

  // Video to Audio State
  const [audioTargetFormat, setAudioTargetFormat] = useState<string>('mp3');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingProgress, setProcessingProgress] = useState<number>(0);

  // Transcription State (Phase 13E.2)
  const [transcriptLanguage, setTranscriptLanguage] = useState<string>('en');
  const [reuseExistingTranscripts, setReuseExistingTranscripts] = useState<boolean>(true);
  const [transcriptViewMode, setTranscriptViewMode] = useState<'segments' | 'text'>('segments');

  // Segment Inline Editing State
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editingSegmentText, setEditingSegmentText] = useState<string>('');
  const [isSavingSegment, setIsSavingSegment] = useState<boolean>(false);

  // Copy Feedback State
  const [copiedSegmentId, setCopiedSegmentId] = useState<string | null>(null);
  const [copiedFullText, setCopiedFullText] = useState<boolean>(false);

  // Active Task & History
  const [activeTask, setActiveTask] = useState<ToolkitTask | null>(null);
  const [tasks, setTasks] = useState<ToolkitTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState<boolean>(false);

  // Audio Preview Player
  const [playingTaskId, setPlayingTaskId] = useState<string | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const isTranscriptionTool = [
    'video_to_transcript',
    'video_to_text',
    'audio_to_transcript',
    'audio_to_text',
  ].includes(selectedTool);

  const isAudioInputTool = ['audio_to_transcript', 'audio_to_text'].includes(selectedTool);

  // Synchronize transcript view mode with chosen tool
  useEffect(() => {
    if (selectedTool === 'video_to_text' || selectedTool === 'audio_to_text') {
      setTranscriptViewMode('text');
    } else if (selectedTool === 'video_to_transcript' || selectedTool === 'audio_to_transcript') {
      setTranscriptViewMode('segments');
    }
  }, [selectedTool]);

  // Fetch capabilities & recent tasks on mount
  const fetchCapabilities = useCallback(async () => {
    try {
      const data = await api.getToolkitCapabilities();
      setCapabilities(data);
    } catch (err: any) {
      console.warn('Failed to load toolkit capabilities:', err);
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      setTasksLoading(true);
      const data = await api.listToolkitTasks();
      setTasks(data);
      if (data.length > 0 && !activeTask) {
        const completed = data.find((t) => t.status === 'completed');
        if (completed) {
          // If task has segments or output, fetch full details
          const fullTask = await api.getToolkitTask(completed.id);
          setActiveTask(fullTask);
        }
      }
    } catch (err: any) {
      console.error('Failed to list toolkit tasks:', err);
    } finally {
      setTasksLoading(false);
    }
  }, [activeTask]);

  useEffect(() => {
    fetchCapabilities();
    fetchTasks();
  }, [fetchCapabilities, fetchTasks]);

  // Handle Drag & Drop
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      handleFileSelection(file);
    }
  };

  const handleFileSelection = (file: File) => {
    setError(null);
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    const videoExts = ['.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi', '.3gp'];
    const audioExts = ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg', '.wma'];

    if (isAudioInputTool) {
      if (!audioExts.includes(ext) && !videoExts.includes(ext)) {
        setError(`Unsupported audio format "${ext}". Please upload WAV, MP3, M4A, FLAC, or OGG.`);
        return;
      }
    } else {
      if (!videoExts.includes(ext) && !audioExts.includes(ext)) {
        setError(`Unsupported video format "${ext}". Please upload MP4, MOV, MKV, or WebM.`);
        return;
      }
    }

    if (file.size > 500 * 1024 * 1024) {
      setError('File size exceeds the 500 MB limit.');
      return;
    }
    setSelectedFile(file);
  };

  // Execute extraction (Video to Audio)
  const handleExtractAudio = async () => {
    setError(null);
    if (inputMode === 'upload' && !selectedFile) {
      setError('Please choose or drop a video file to extract audio.');
      return;
    }
    if (inputMode === 'project' && !selectedProjectId) {
      setError('Please select an existing project with a video track.');
      return;
    }

    try {
      setIsProcessing(true);
      setProcessingProgress(20);
      setStatusMessage('Validating video container & audio streams...');

      const formData = new FormData();
      if (inputMode === 'upload' && selectedFile) {
        formData.append('file', selectedFile);
      } else if (inputMode === 'project' && selectedProjectId) {
        formData.append('project_id', selectedProjectId);
      }
      formData.append('target_format', audioTargetFormat);

      setProcessingProgress(50);
      setStatusMessage(`Extracting audio stream into ${audioTargetFormat.toUpperCase()}...`);

      const result = await api.extractAudio(formData);
      setProcessingProgress(100);
      setStatusMessage('Extraction completed successfully!');
      setActiveTask(result);

      await fetchTasks();

      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: any) {
      console.error('Audio extraction failed:', err);
      setError(err.message || 'Failed to extract audio track. Check that video contains audio.');
    } finally {
      setIsProcessing(false);
      setTimeout(() => {
        setProcessingProgress(0);
        setStatusMessage('');
      }, 3000);
    }
  };

  // Execute Transcription (Video/Audio to Transcript or Text)
  const handleTranscribeMedia = async () => {
    setError(null);
    if (inputMode === 'upload' && !selectedFile) {
      setError('Please select or drop a media file to transcribe.');
      return;
    }
    if (inputMode === 'project' && !selectedProjectId) {
      setError('Please select an existing project to transcribe or reuse.');
      return;
    }

    if (transcriptLanguage === 'km') {
      setError(
        'Khmer speech recognition is not supported by the current Whisper checkpoint and requires a verified Khmer ASR engine. Please select English (en).'
      );
      return;
    }

    try {
      setIsProcessing(true);
      setProcessingProgress(15);
      setStatusMessage('Analyzing media container & preparing 16kHz audio stream...');

      const formData = new FormData();
      if (inputMode === 'upload' && selectedFile) {
        formData.append('file', selectedFile);
      } else if (inputMode === 'project' && selectedProjectId) {
        formData.append('project_id', selectedProjectId);
      }

      formData.append('tool_type', selectedTool);
      formData.append('language', transcriptLanguage);
      formData.append('reuse_existing', reuseExistingTranscripts ? 'true' : 'false');

      const defaultFormat = selectedTool.endsWith('_text') ? 'txt' : 'srt';
      formData.append('target_format', defaultFormat);

      setProcessingProgress(45);
      setStatusMessage('Transcribing speech segments with Faster-Whisper ASR...');

      const result = await api.transcribeMedia(formData);

      setProcessingProgress(100);
      setStatusMessage('Transcription completed successfully!');
      setActiveTask(result);

      await fetchTasks();

      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: any) {
      console.error('Transcription failed:', err);
      setError(err.message || 'Transcription failed. Please ensure the media contains clear speech.');
    } finally {
      setIsProcessing(false);
      setTimeout(() => {
        setProcessingProgress(0);
        setStatusMessage('');
      }, 3000);
    }
  };

  // Segment Inline Edit Handlers
  const handleStartEditSegment = (segment: ToolkitTranscriptSegment) => {
    setEditingSegmentId(segment.id);
    setEditingSegmentText(segment.text);
  };

  const handleCancelEditSegment = () => {
    setEditingSegmentId(null);
    setEditingSegmentText('');
  };

  const handleSaveEditSegment = async (segmentId: string) => {
    if (!activeTask) return;
    try {
      setIsSavingSegment(true);
      const updated = await api.updateToolkitSegment(activeTask.id, segmentId, editingSegmentText);
      // Update local state
      const updatedSegments = (activeTask.segments || []).map((s) =>
        s.id === segmentId ? updated : s
      );
      const newFullText = updatedSegments.map((s) => s.text).join('\n\n');
      setActiveTask({
        ...activeTask,
        segments: updatedSegments,
        full_text: newFullText,
      });
      setEditingSegmentId(null);
      setEditingSegmentText('');
    } catch (err: any) {
      console.error('Failed to save segment edit:', err);
      alert(err.message || 'Failed to save segment edit.');
    } finally {
      setIsSavingSegment(false);
    }
  };

  const handleResetSegment = async (segmentId?: string) => {
    if (!activeTask) return;
    const msg = segmentId
      ? 'Reset this segment back to verbatim AI speech recognition?'
      : 'Reset all segment edits back to original verbatim AI speech recognition?';
    if (!window.confirm(msg)) return;

    try {
      const res = await api.resetToolkitEdits(activeTask.id, segmentId);
      const newFullText = res.segments.map((s) => s.text).join('\n\n');
      setActiveTask({
        ...activeTask,
        segments: res.segments,
        full_text: newFullText,
      });
    } catch (err: any) {
      console.error('Failed to reset edits:', err);
      alert(err.message || 'Failed to reset edits.');
    }
  };

  // Copy helpers
  const handleCopyText = (text: string, segmentId?: string) => {
    navigator.clipboard.writeText(text);
    if (segmentId) {
      setCopiedSegmentId(segmentId);
      setTimeout(() => setCopiedSegmentId(null), 2000);
    } else {
      setCopiedFullText(true);
      setTimeout(() => setCopiedFullText(false), 2000);
    }
  };

  // Audio preview playback
  const handleTogglePlay = (taskId: string) => {
    if (!audioPlayerRef.current) return;

    if (playingTaskId === taskId) {
      audioPlayerRef.current.pause();
      setPlayingTaskId(null);
    } else {
      const streamUrl = api.getToolkitAudioStreamUrl(taskId);
      audioPlayerRef.current.src = streamUrl;
      audioPlayerRef.current.play().catch((err) => {
        console.warn('Playback error:', err);
      });
      setPlayingTaskId(taskId);
    }
  };

  // Task selection & deletion
  const handleSelectTask = async (task: ToolkitTask) => {
    try {
      const full = await api.getToolkitTask(task.id);
      setActiveTask(full);
      // Auto-switch selected tool if matching
      if (['video_to_audio', 'video_to_transcript', 'video_to_text', 'audio_to_transcript', 'audio_to_text'].includes(full.tool_type)) {
        setSelectedTool(full.tool_type);
      }
    } catch (err: any) {
      console.error('Failed to load task details:', err);
      setActiveTask(task);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!window.confirm('Delete this toolkit task and all associated transcript files?')) return;
    try {
      if (playingTaskId === taskId && audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        setPlayingTaskId(null);
      }
      await api.deleteToolkitTask(taskId);
      if (activeTask?.id === taskId) {
        setActiveTask(null);
      }
      await fetchTasks();
    } catch (err: any) {
      console.error('Failed to delete task:', err);
      alert(err.message || 'Failed to delete task');
    }
  };

  // Helpers
  const formatBytes = (bytes?: number | null) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  const formatDuration = (seconds?: number | null) => {
    if (!seconds || seconds <= 0) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTimestamp = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = (sec % 60).toFixed(2);
    return `${mins.toString().padStart(2, '0')}:${secs.padStart(5, '0')}`;
  };

  // Tools list for grid
  const toolsList = [
    {
      id: 'video_to_audio',
      title: 'Video to Audio',
      desc: 'Extract pristine audio track into MP3, WAV, or M4A with direct lossless remuxing.',
      icon: Video,
      status: 'available' as const,
      phase: 'Phase 13E.1',
    },
    {
      id: 'video_to_transcript',
      title: 'Video to Transcript',
      desc: 'Generate timestamped segment transcripts from video speeches with Faster-Whisper.',
      icon: FileText,
      status: 'available' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'video_to_text',
      title: 'Video to Text',
      desc: 'Extract plain continuous transcripts without timestamps for articles and summaries.',
      icon: AlignLeft,
      status: 'available' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'audio_to_transcript',
      title: 'Audio to Transcript',
      desc: 'Transcribe voice memos, podcasts, and recordings into structured timestamps.',
      icon: ListMusic,
      status: 'available' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'audio_to_text',
      title: 'Audio to Text',
      desc: 'Fast voice-to-text transcription for notes and document drafting.',
      icon: FileCode,
      status: 'available' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'text_to_speech',
      title: 'Text to Speech Studio',
      desc: 'Generate natural Khmer speech using Google Khmer, Edge Piseth/Sreymom, or VoxCPM2.',
      icon: Mic2,
      status: 'planned' as const,
      phase: 'Phase 13E.3',
    },
    {
      id: 'transcript_to_audio',
      title: 'Transcript to Audio',
      desc: 'Transform subtitle transcripts into continuous audio narration or synchronized tracks.',
      icon: Radio,
      status: 'planned' as const,
      phase: 'Phase 13E.4',
    },
  ];

  const getToolTitle = (toolId: string) => {
    const found = toolsList.find((t) => t.id === toolId);
    return found ? found.title : toolId;
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-12">
      {/* Hidden audio element for preview */}
      <audio
        ref={audioPlayerRef}
        onEnded={() => setPlayingTaskId(null)}
        onError={() => setPlayingTaskId(null)}
      />

      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 text-white shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 bottom-0 w-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                AI Media Toolkit
              </span>
              <span className="text-xs text-slate-400 font-mono">
                {capabilities?.version ? `v${capabilities.version}` : 'Phase 13E.2'}
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              Media Extraction & Transcription Hub
            </h1>
            <p className="text-slate-400 text-sm mt-1 max-w-2xl">
              Extract pristine audio, generate timestamped transcripts, edit speech segments, and export subtitles (SRT, VTT, TXT, CSV, JSON) without altering original project data.
            </p>
          </div>

          <button
            onClick={() => setShowLanguageInfo(!showLanguageInfo)}
            className="self-start md:self-auto inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium bg-slate-800/80 hover:bg-slate-800 text-slate-300 border border-slate-700/60 transition-colors shadow-sm cursor-pointer"
          >
            <Info className="w-4 h-4 text-indigo-400" />
            <span>AI Capabilities & Languages</span>
            {showLanguageInfo ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>

        {/* Expandable Language Capability Matrix */}
        {showLanguageInfo && (
          <div className="mt-6 pt-6 border-t border-slate-800/80 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              <span className="font-semibold text-slate-200 mb-1.5 flex items-center gap-2">
                <FileAudio className="w-4 h-4 text-indigo-400" />
                Audio Extraction (13E.1)
              </span>
              <p className="text-slate-400 leading-relaxed">
                Universal container support (MP4, MOV, MKV, WebM). Direct stream remuxing for AAC/M4A and high-fidelity 192k MP3 & 16-bit WAV PCM encoding.
              </p>
            </div>
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              <span className="font-semibold text-slate-200 mb-1.5 flex items-center gap-2">
                <FileText className="w-4 h-4 text-emerald-400" />
                Speech-to-Text (13E.2)
              </span>
              <p className="text-slate-400 leading-relaxed">
                English speech transcription powered by Faster-Whisper with word/segment timestamps, plain text extraction, inline editing, and multi-format subtitle exports.
              </p>
            </div>
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              <span className="font-semibold text-slate-200 mb-1.5 flex items-center gap-2">
                <Mic2 className="w-4 h-4 text-amber-400" />
                Speech Synthesis (13E.3)
              </span>
              <p className="text-slate-400 leading-relaxed">
                Khmer TTS via Google Khmer, Microsoft Piseth, Microsoft Sreymom, and authorized VoxCPM2 custom voice profiles with prompt cache acceleration.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Tool Cards Selector */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
            Available & Planned Toolkit Modules
          </h2>
          <span className="text-xs text-slate-400">Click a card to activate</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {toolsList.map((tool) => {
            const Icon = tool.icon;
            const isSelected = selectedTool === tool.id;
            const isAvailable = tool.status === 'available';

            return (
              <button
                key={tool.id}
                onClick={() => {
                  if (isAvailable) {
                    setSelectedTool(tool.id);
                    setError(null);
                  }
                }}
                disabled={!isAvailable}
                className={`text-left p-4 rounded-xl border transition-all duration-200 relative flex flex-col justify-between ${
                  isSelected
                    ? 'bg-white border-indigo-500 shadow-md ring-2 ring-indigo-500/20'
                    : isAvailable
                    ? 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-sm cursor-pointer'
                    : 'bg-slate-50/70 border-slate-200/80 opacity-70 cursor-not-allowed'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div
                      className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                        isSelected
                          ? 'bg-indigo-600 text-white'
                          : isAvailable
                          ? 'bg-indigo-50 text-indigo-600'
                          : 'bg-slate-200/70 text-slate-400'
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                    </div>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                        isAvailable
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-slate-100 text-slate-500 border border-slate-200'
                      }`}
                    >
                      {isAvailable ? 'Available Now' : tool.phase}
                    </span>
                  </div>
                  <h3 className="font-semibold text-slate-800 text-sm">{tool.title}</h3>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {tool.desc}
                  </p>
                </div>

                <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                  <span>{isAvailable ? 'Ready to use' : 'Under Development'}</span>
                  {isSelected && <span className="font-medium text-indigo-600">Active</span>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Studio Viewport */}
      {selectedTool === 'video_to_audio' ? (
        /* Video to Audio Studio (Phase 13E.1) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  <Video className="w-5 h-5 text-indigo-600" />
                  Video to Audio Extraction
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Extract full-duration audio into standard formats with intelligent lossless stream copying.
                </p>
              </div>
            </div>

            {error && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold">Error:</span> {error}
                </div>
              </div>
            )}

            {/* Source Selection */}
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                1. Select Video Source
              </label>

              <div className="grid grid-cols-2 gap-2 p-1 bg-slate-100 rounded-xl text-xs font-medium">
                <button
                  type="button"
                  onClick={() => {
                    setInputMode('upload');
                    setError(null);
                  }}
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                    inputMode === 'upload'
                      ? 'bg-white text-slate-900 shadow-sm font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <Upload className="w-3.5 h-3.5" />
                  Upload New Video
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setInputMode('project');
                    setError(null);
                  }}
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                    inputMode === 'project'
                      ? 'bg-white text-slate-900 shadow-sm font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <FolderGit2 className="w-3.5 h-3.5" />
                  Select Project Video
                </button>
              </div>

              {inputMode === 'upload' ? (
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all ${
                    selectedFile
                      ? 'border-indigo-400 bg-indigo-50/40'
                      : 'border-slate-300 hover:border-indigo-400 hover:bg-slate-50/80'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/avi"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        handleFileSelection(e.target.files[0]);
                      }
                    }}
                  />
                  {selectedFile ? (
                    <div className="space-y-1.5">
                      <div className="w-10 h-10 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center mx-auto">
                        <CheckCircle2 className="w-5 h-5" />
                      </div>
                      <p className="font-semibold text-slate-800 text-sm truncate max-w-sm mx-auto">
                        {selectedFile.name}
                      </p>
                      <p className="text-xs text-slate-400">
                        {formatBytes(selectedFile.size)} • Click or drop another to replace
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                        <Upload className="w-5 h-5 text-slate-500" />
                      </div>
                      <p className="text-sm font-medium text-slate-700">
                        Drag and drop a video file here, or{' '}
                        <span className="text-indigo-600 font-semibold underline">browse</span>
                      </p>
                      <p className="text-xs text-slate-400">Supports MP4, MOV, MKV, WebM (up to 500 MB)</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  >
                    <option value="">-- Choose an existing project video --</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title} (Status: {p.status})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-400">
                    Extracts audio directly from the existing uploaded project video without file duplication.
                  </p>
                </div>
              )}
            </div>

            {/* Target Format */}
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                2. Target Audio Format
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  { id: 'mp3', label: 'MP3', tag: 'Universal', desc: '192 kbps high fidelity encoding for universal playback.' },
                  { id: 'wav', label: 'WAV', tag: 'Lossless', desc: 'Uncompressed 16-bit PCM studio audio, ideal for downstream processing.' },
                  { id: 'm4a', label: 'M4A', tag: 'Stream Remux', desc: 'High-efficiency AAC; direct stream copy if video has AAC.' },
                ].map((fmt) => (
                  <button
                    key={fmt.id}
                    type="button"
                    onClick={() => setAudioTargetFormat(fmt.id)}
                    className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer ${
                      audioTargetFormat === fmt.id
                        ? 'border-indigo-600 bg-indigo-50/50 ring-1 ring-indigo-600 text-slate-900'
                        : 'border-slate-200 hover:border-slate-300 text-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-sm">{fmt.label}</span>
                      <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-slate-200/60 text-slate-700">
                        {fmt.tag}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 leading-snug">{fmt.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Progress */}
            {isProcessing && (
              <div className="space-y-2 p-4 rounded-xl bg-slate-50 border border-slate-200">
                <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                    {statusMessage || 'Extracting audio...'}
                  </span>
                  <span>{processingProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${processingProgress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Button */}
            <button
              onClick={handleExtractAudio}
              disabled={isProcessing || (inputMode === 'upload' && !selectedFile) || (inputMode === 'project' && !selectedProjectId)}
              className="w-full py-3 px-4 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white shadow-sm transition-all duration-150 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Extracting Audio Track...
                </>
              ) : (
                <>
                  <FileAudio className="w-4 h-4" />
                  Extract Audio Track ({audioTargetFormat.toUpperCase()})
                </>
              )}
            </button>
          </div>

          {/* Result Panel */}
          <div className="lg:col-span-5 space-y-6">
            {activeTask && activeTask.tool_type === 'video_to_audio' && activeTask.status === 'completed' ? (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                    <h4 className="font-bold text-slate-900 text-sm">Active Extracted Output</h4>
                  </div>
                  <span className="text-xs font-semibold uppercase px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                    {activeTask.target_format}
                  </span>
                </div>

                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-slate-400 font-medium">Output Filename</p>
                    <p className="text-sm font-semibold text-slate-800 truncate" title={activeTask.output_filename || ''}>
                      {activeTask.output_filename}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center gap-2">
                      <Clock className="w-4 h-4 text-indigo-500 shrink-0" />
                      <div>
                        <span className="text-slate-400 text-[10px] block">Duration</span>
                        <span className="font-semibold text-slate-700">{formatDuration(activeTask.output_duration_seconds)}</span>
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center gap-2">
                      <HardDrive className="w-4 h-4 text-emerald-500 shrink-0" />
                      <div>
                        <span className="text-slate-400 text-[10px] block">File Size</span>
                        <span className="font-semibold text-slate-700">{formatBytes(activeTask.output_file_size_bytes)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pt-2 flex flex-col sm:flex-row gap-2.5">
                  <button
                    onClick={() => handleTogglePlay(activeTask.id)}
                    className="flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white flex items-center justify-center gap-2 transition-colors cursor-pointer"
                  >
                    {playingTaskId === activeTask.id ? (
                      <>
                        <Pause className="w-4 h-4" /> Pause Audio
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" /> Play Preview
                      </>
                    )}
                  </button>
                  <a
                    href={api.getToolkitAudioDownloadUrl(activeTask.id)}
                    download
                    className="py-2.5 px-4 rounded-xl text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 flex items-center justify-center gap-2 transition-colors"
                  >
                    <Download className="w-4 h-4" /> Download {activeTask.target_format.toUpperCase()}
                  </a>
                </div>
              </div>
            ) : (
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-8 text-center text-slate-400 space-y-3">
                <FileAudio className="w-12 h-12 text-slate-300 mx-auto" />
                <h4 className="font-semibold text-slate-700 text-sm">No Active Extracted Audio</h4>
                <p className="text-xs text-slate-400 max-w-xs mx-auto">
                  Upload a video file or pick an existing project on the left to extract downloadable audio tracks.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : isTranscriptionTool ? (
        /* Transcription & Subtitles Toolkit (Phase 13E.2) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Main Processing Config */}
          <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  {selectedTool.includes('video') ? (
                    <Video className="w-5 h-5 text-indigo-600" />
                  ) : (
                    <FileAudio className="w-5 h-5 text-indigo-600" />
                  )}
                  {getToolTitle(selectedTool)}
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {isAudioInputTool
                    ? 'Transcribe speech from standalone audio files (WAV, MP3, M4A, FLAC).'
                    : 'Transcribe speech directly from video containers with Whisper ASR.'}
                </p>
              </div>
            </div>

            {error && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold">Error:</span> {error}
                </div>
              </div>
            )}

            {/* Step 1: Input Media Source */}
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                1. Select {isAudioInputTool ? 'Audio' : 'Video'} Source
              </label>

              <div className="grid grid-cols-2 gap-2 p-1 bg-slate-100 rounded-xl text-xs font-medium">
                <button
                  type="button"
                  onClick={() => {
                    setInputMode('upload');
                    setError(null);
                  }}
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                    inputMode === 'upload'
                      ? 'bg-white text-slate-900 shadow-sm font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <Upload className="w-3.5 h-3.5" />
                  Upload Media
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setInputMode('project');
                    setError(null);
                  }}
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                    inputMode === 'project'
                      ? 'bg-white text-slate-900 shadow-sm font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <FolderGit2 className="w-3.5 h-3.5" />
                  Existing Project
                </button>
              </div>

              {inputMode === 'upload' ? (
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all ${
                    selectedFile
                      ? 'border-indigo-400 bg-indigo-50/40'
                      : 'border-slate-300 hover:border-indigo-400 hover:bg-slate-50/80'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={
                      isAudioInputTool
                        ? 'audio/wav,audio/mpeg,audio/mp4,audio/flac,audio/aac,audio/ogg,video/mp4'
                        : 'video/mp4,video/quicktime,video/x-matroska,video/webm,video/avi'
                    }
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        handleFileSelection(e.target.files[0]);
                      }
                    }}
                  />
                  {selectedFile ? (
                    <div className="space-y-1.5">
                      <div className="w-10 h-10 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center mx-auto">
                        <CheckCircle2 className="w-5 h-5" />
                      </div>
                      <p className="font-semibold text-slate-800 text-sm truncate max-w-sm mx-auto">
                        {selectedFile.name}
                      </p>
                      <p className="text-xs text-slate-400">
                        {formatBytes(selectedFile.size)} • Click or drop another to replace
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                        <Upload className="w-5 h-5 text-slate-500" />
                      </div>
                      <p className="text-sm font-medium text-slate-700">
                        Drop {isAudioInputTool ? 'an audio' : 'a video'} file here, or{' '}
                        <span className="text-indigo-600 font-semibold underline">browse</span>
                      </p>
                      <p className="text-xs text-slate-400">
                        {isAudioInputTool
                          ? 'Supports WAV, MP3, M4A, FLAC, OGG'
                          : 'Supports MP4, MOV, MKV, WebM'}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  >
                    <option value="">-- Choose an existing project --</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title} (Status: {p.status})
                      </option>
                    ))}
                  </select>

                  <div className="flex items-center gap-2 pt-1">
                    <input
                      type="checkbox"
                      id="reuseTranscripts"
                      checked={reuseExistingTranscripts}
                      onChange={(e) => setReuseExistingTranscripts(e.target.checked)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <label htmlFor="reuseTranscripts" className="text-xs text-slate-600 cursor-pointer">
                      Reuse existing project transcripts if available (instant 0s processing)
                    </label>
                  </div>
                </div>
              )}
            </div>

            {/* Step 2: Language Capability & Selection */}
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                2. Speech Recognition Language
              </label>

              <div className="space-y-2">
                <select
                  value={transcriptLanguage}
                  onChange={(e) => {
                    setTranscriptLanguage(e.target.value);
                    if (e.target.value === 'km') {
                      setError(
                        'Khmer speech recognition is not supported by the current Whisper checkpoint and requires a verified Khmer ASR engine.'
                      );
                    } else {
                      setError(null);
                    }
                  }}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                >
                  <option value="en">English (en) — Fully Supported & Verified</option>
                  <option value="km">Khmer (km) — Requires Verified Khmer ASR Engine (Unavailable)</option>
                </select>

                {/* Honest Language Capability Notice */}
                <div className="p-3 rounded-xl bg-amber-50/70 border border-amber-200/80 text-xs text-amber-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-800">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>Language Capability Notice</span>
                  </div>
                  <p className="text-[11px] text-amber-700 leading-relaxed">
                    English speech recognition is fully optimized via Faster-Whisper with word/phrase timestamps and punctuation. Khmer speech-to-text requires a specialized fine-tuned Khmer ASR model and is deliberately disabled here to prevent inaccurate transcription.
                  </p>
                </div>
              </div>
            </div>

            {/* Progress Bar */}
            {isProcessing && (
              <div className="space-y-2 p-4 rounded-xl bg-slate-50 border border-slate-200">
                <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                    {statusMessage || 'Transcribing audio speech...'}
                  </span>
                  <span>{processingProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${processingProgress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Transcribe Button */}
            <button
              onClick={handleTranscribeMedia}
              disabled={isProcessing || (inputMode === 'upload' && !selectedFile) || (inputMode === 'project' && !selectedProjectId) || transcriptLanguage === 'km'}
              className="w-full py-3 px-4 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white shadow-sm transition-all duration-150 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Transcribing Speech Segments...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" />
                  {selectedTool.includes('text') ? 'Extract Plain Text' : 'Transcribe Media'}
                </>
              )}
            </button>
          </div>

          {/* Transcript Viewer, Editor, and Export Panel */}
          <div className="lg:col-span-7 space-y-6">
            {activeTask && activeTask.status === 'completed' && activeTask.segments ? (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
                {/* Header Summary & View Mode Switcher */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                      <h4 className="font-bold text-slate-900 text-base">
                        {activeTask.source_filename}
                      </h4>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                      <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-semibold uppercase text-[10px]">
                        Language: EN
                      </span>
                      <span>•</span>
                      <span>{activeTask.segments.length} segments</span>
                      <span>•</span>
                      <span>{formatDuration(activeTask.output_duration_seconds)}</span>
                    </div>
                  </div>

                  {/* Segment vs Plain Text Tabs */}
                  <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-xl text-xs font-medium">
                    <button
                      type="button"
                      onClick={() => setTranscriptViewMode('segments')}
                      className={`py-1.5 px-3 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer ${
                        transcriptViewMode === 'segments'
                          ? 'bg-white text-indigo-700 shadow-sm font-semibold'
                          : 'text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      <ListMusic className="w-3.5 h-3.5" />
                      Timestamped Segments
                    </button>
                    <button
                      type="button"
                      onClick={() => setTranscriptViewMode('text')}
                      className={`py-1.5 px-3 rounded-lg flex items-center gap-1.5 transition-all cursor-pointer ${
                        transcriptViewMode === 'text'
                          ? 'bg-white text-indigo-700 shadow-sm font-semibold'
                          : 'text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      <AlignLeft className="w-3.5 h-3.5" />
                      Continuous Plain Text
                    </button>
                  </div>
                </div>

                {/* Subtitle Export Toolbar */}
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2 font-medium text-slate-700">
                    <Download className="w-4 h-4 text-indigo-600" />
                    <span>Download Transcript / Subtitles:</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {[
                      { fmt: 'srt', label: 'SRT', desc: 'Standard SubRip' },
                      { fmt: 'vtt', label: 'VTT', desc: 'WebVTT' },
                      { fmt: 'txt', label: 'TXT', desc: 'Plain Text' },
                      { fmt: 'csv', label: 'CSV', desc: 'Spreadsheet' },
                      { fmt: 'json', label: 'JSON', desc: 'Structured Data' },
                    ].map((item) => (
                      <a
                        key={item.fmt}
                        href={api.getToolkitExportUrl(activeTask.id, item.fmt)}
                        download
                        className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 hover:border-indigo-400 hover:text-indigo-600 font-semibold text-slate-700 shadow-2xs transition-all flex items-center gap-1 cursor-pointer"
                        title={item.desc}
                      >
                        <span>{item.label}</span>
                      </a>
                    ))}
                  </div>
                </div>

                {/* View Mode: Timestamped Segments */}
                {transcriptViewMode === 'segments' && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Click "Edit" on any segment to correct recognized speech.</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleCopyText(activeTask.full_text || '')}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                        >
                          {copiedFullText ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-emerald-600" />
                              <span className="text-emerald-600 font-semibold">Copied Full Text</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy Full Text</span>
                            </>
                          )}
                        </button>

                        <button
                          onClick={() => handleResetSegment()}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
                          title="Reset all segment edits back to raw AI text"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Reset All Edits</span>
                        </button>
                      </div>
                    </div>

                    {/* Segments List */}
                    <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                      {activeTask.segments.length === 0 ? (
                        <div className="text-center py-10 text-slate-400 text-xs">
                          No speech detected in this media.
                        </div>
                      ) : (
                        activeTask.segments.map((seg) => {
                          const isEditing = editingSegmentId === seg.id;
                          const isCopied = copiedSegmentId === seg.id;

                          return (
                            <div
                              key={seg.id}
                              className={`p-3.5 rounded-xl border transition-all ${
                                isEditing
                                  ? 'border-indigo-400 bg-indigo-50/20 ring-1 ring-indigo-400'
                                  : 'border-slate-200 hover:border-slate-300 bg-white'
                              }`}
                            >
                              <div className="flex items-center justify-between mb-2 text-xs">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-bold text-slate-400">
                                    #{seg.segment_order}
                                  </span>
                                  <span className="px-2 py-0.5 rounded bg-slate-100 font-mono text-[11px] text-slate-600 font-medium">
                                    {formatTimestamp(seg.start_time)} → {formatTimestamp(seg.end_time)}
                                  </span>
                                  <span className="text-[10px] text-slate-400">
                                    ({(seg.end_time - seg.start_time).toFixed(1)}s)
                                  </span>
                                  {seg.is_edited && (
                                    <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px] font-semibold border border-emerald-200">
                                      Edited
                                    </span>
                                  )}
                                </div>

                                <div className="flex items-center gap-1">
                                  {!isEditing ? (
                                    <>
                                      <button
                                        onClick={() => handleCopyText(seg.text, seg.id)}
                                        className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
                                        title="Copy segment text"
                                      >
                                        {isCopied ? (
                                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                                        ) : (
                                          <Copy className="w-3.5 h-3.5" />
                                        )}
                                      </button>
                                      <button
                                        onClick={() => handleStartEditSegment(seg)}
                                        className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-indigo-600 transition-colors cursor-pointer"
                                        title="Edit segment"
                                      >
                                        <Edit2 className="w-3.5 h-3.5" />
                                      </button>
                                      {seg.is_edited && (
                                        <button
                                          onClick={() => handleResetSegment(seg.id)}
                                          className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                                          title="Reset to raw ASR text"
                                        >
                                          <RotateCcw className="w-3.5 h-3.5" />
                                        </button>
                                      )}
                                    </>
                                  ) : (
                                    <div className="flex items-center gap-1.5">
                                      <button
                                        onClick={() => handleSaveEditSegment(seg.id)}
                                        disabled={isSavingSegment}
                                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-[11px] cursor-pointer"
                                      >
                                        <Save className="w-3 h-3" />
                                        Save
                                      </button>
                                      <button
                                        onClick={handleCancelEditSegment}
                                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-200 hover:bg-slate-300 text-slate-700 text-[11px] cursor-pointer"
                                      >
                                        <X className="w-3 h-3" />
                                        Cancel
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {isEditing ? (
                                <textarea
                                  value={editingSegmentText}
                                  onChange={(e) => setEditingSegmentText(e.target.value)}
                                  className="w-full p-2.5 rounded-lg border border-indigo-300 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 resize-y"
                                  rows={2}
                                  autoFocus
                                />
                              ) : (
                                <p className="text-slate-800 text-sm leading-relaxed">{seg.text}</p>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                )}

                {/* View Mode: Continuous Plain Text */}
                {transcriptViewMode === 'text' && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Flowing continuous paragraph text for documentation or articles.</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleCopyText(activeTask.full_text || '')}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-colors shadow-xs cursor-pointer"
                        >
                          {copiedFullText ? (
                            <>
                              <Check className="w-3.5 h-3.5" />
                              <span>Copied to Clipboard!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy Plain Text</span>
                            </>
                          )}
                        </button>

                        <a
                          href={api.getToolkitExportUrl(activeTask.id, 'txt')}
                          download
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold transition-colors cursor-pointer"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>Download .TXT</span>
                        </a>
                      </div>
                    </div>

                    <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 max-h-[460px] overflow-y-auto">
                      <p className="text-slate-800 text-sm leading-relaxed whitespace-pre-wrap font-sans">
                        {activeTask.full_text || 'No text extracted.'}
                      </p>
                    </div>

                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>
                        Words: {activeTask.full_text ? activeTask.full_text.split(/\s+/).filter(Boolean).length : 0} • Characters:{' '}
                        {activeTask.full_text?.length || 0}
                      </span>
                      <button
                        onClick={() => setTranscriptViewMode('segments')}
                        className="text-indigo-600 hover:underline font-medium cursor-pointer"
                      >
                        Switch to Timestamped Segments to edit cues →
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-10 text-center text-slate-400 space-y-3">
                <FileCheck className="w-12 h-12 text-slate-300 mx-auto" />
                <h4 className="font-semibold text-slate-700 text-sm">No Active Transcript</h4>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  Select a media file or project on the left and click "Transcribe Media" to view, edit, and export speech transcripts.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {/* Task Workspace History Section */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-slate-900 text-base">Media Toolkit Workspace History</h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">
              {tasks.length}
            </span>
          </div>

          <button
            onClick={fetchTasks}
            disabled={tasksLoading}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
            title="Refresh history"
          >
            <RefreshCw className={`w-4 h-4 ${tasksLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {tasks.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-xs">
            No media tasks yet. Generated files and transcripts will appear here for review and download.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 font-semibold uppercase tracking-wider">
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Tool Type</th>
                  <th className="py-2.5 px-3">Source Media</th>
                  <th className="py-2.5 px-3">Format</th>
                  <th className="py-2.5 px-3">Duration</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {tasks.map((task) => (
                  <tr
                    key={task.id}
                    onClick={() => handleSelectTask(task)}
                    className={`hover:bg-slate-50/70 transition-colors cursor-pointer ${
                      activeTask?.id === task.id ? 'bg-indigo-50/30' : ''
                    }`}
                  >
                    <td className="py-3 px-3 text-slate-400 whitespace-nowrap">
                      {new Date(task.created_at).toLocaleDateString()}{' '}
                      {new Date(task.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                        {getToolTitle(task.tool_type)}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-medium text-slate-900 max-w-[200px] truncate" title={task.source_filename}>
                      {task.source_filename}
                    </td>
                    <td className="py-3 px-3">
                      <span className="font-semibold uppercase px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-700">
                        {task.target_format}
                      </span>
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      {formatDuration(task.output_duration_seconds)}
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      {task.status === 'completed' && (
                        <span className="inline-flex items-center gap-1 text-emerald-600 font-medium">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Done
                        </span>
                      )}
                      {task.status === 'processing' && (
                        <span className="inline-flex items-center gap-1 text-indigo-600 font-medium">
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Processing
                        </span>
                      )}
                      {task.status === 'failed' && (
                        <span className="inline-flex items-center gap-1 text-rose-600 font-medium" title={task.error_message || ''}>
                          <AlertCircle className="w-3.5 h-3.5" /> Failed
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        {task.status === 'completed' && (
                          <>
                            {task.tool_type === 'video_to_audio' && (
                              <button
                                onClick={() => {
                                  setActiveTask(task);
                                  handleTogglePlay(task.id);
                                }}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                                title="Play/Pause Audio"
                              >
                                {playingTaskId === task.id ? (
                                  <Pause className="w-4 h-4 text-indigo-600" />
                                ) : (
                                  <Play className="w-4 h-4" />
                                )}
                              </button>
                            )}

                            <a
                              href={api.getToolkitAudioDownloadUrl(task.id)}
                              download
                              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                              title="Download Output File"
                            >
                              <Download className="w-4 h-4" />
                            </a>
                          </>
                        )}

                        <button
                          onClick={() => handleDeleteTask(task.id)}
                          className="p-1.5 rounded-lg hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                          title="Delete Task"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default MediaToolkit;
