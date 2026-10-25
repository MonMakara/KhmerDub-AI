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
} from 'lucide-react';
import { api } from '../services/api';
import {
  ProjectSummary,
  ToolkitCapabilities,
  ToolkitTask,
  ToolkitTargetFormat,
} from '../types';

interface MediaToolkitProps {
  projects?: ProjectSummary[];
}

export const MediaToolkit: React.FC<MediaToolkitProps> = ({ projects = [] }) => {
  const [capabilities, setCapabilities] = useState<ToolkitCapabilities | null>(null);
  const [selectedTool, setSelectedTool] = useState<string>('video_to_audio');
  const [showLanguageInfo, setShowLanguageInfo] = useState<boolean>(false);

  // Video to Audio State
  const [inputMode, setInputMode] = useState<'upload' | 'project'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [targetFormat, setTargetFormat] = useState<ToolkitTargetFormat>('mp3');
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [extractionProgress, setExtractionProgress] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [activeTask, setActiveTask] = useState<ToolkitTask | null>(null);

  // History tasks
  const [tasks, setTasks] = useState<ToolkitTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState<boolean>(false);

  // Audio Preview Player
  const [playingTaskId, setPlayingTaskId] = useState<string | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
        // Show most recent task in preview if not already set
        const completed = data.find((t) => t.status === 'completed');
        if (completed) {
          setActiveTask(completed);
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
    const validExtensions = ['.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi', '.3gp'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!validExtensions.includes(ext)) {
      setError(`Unsupported video format "${ext}". Please upload MP4, MOV, MKV, or WebM.`);
      return;
    }
    if (file.size > 500 * 1024 * 1024) {
      setError('File size exceeds the 500 MB limit.');
      return;
    }
    setSelectedFile(file);
  };

  // Execute extraction
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
      setIsExtracting(true);
      setExtractionProgress(20);
      setStatusMessage('Validating video container & audio streams...');

      const formData = new FormData();
      if (inputMode === 'upload' && selectedFile) {
        formData.append('file', selectedFile);
      } else if (inputMode === 'project' && selectedProjectId) {
        formData.append('project_id', selectedProjectId);
      }
      formData.append('target_format', targetFormat);

      setExtractionProgress(50);
      setStatusMessage(`Extracting audio stream into ${targetFormat.toUpperCase()}...`);

      const result = await api.extractAudio(formData);
      setExtractionProgress(100);
      setStatusMessage('Extraction completed successfully!');
      setActiveTask(result);

      // Refresh task list
      await fetchTasks();

      // Reset file input
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: any) {
      console.error('Audio extraction failed:', err);
      setError(err.message || 'Failed to extract audio track. Check that video contains audio.');
    } finally {
      setIsExtracting(false);
      setTimeout(() => {
        setExtractionProgress(0);
        setStatusMessage('');
      }, 3000);
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

  // Task deletion
  const handleDeleteTask = async (taskId: string) => {
    if (!window.confirm('Delete this extraction task and its generated files?')) return;
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

  // Format bytes helper
  const formatBytes = (bytes?: number | null) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  // Format seconds helper
  const formatDuration = (seconds?: number | null) => {
    if (!seconds || seconds <= 0) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
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
      status: 'planned' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'video_to_text',
      title: 'Video to Text',
      desc: 'Extract plain continuous transcripts without timestamps for articles and summaries.',
      icon: AlignLeft,
      status: 'planned' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'audio_to_transcript',
      title: 'Audio to Transcript',
      desc: 'Transcribe voice memos, podcasts, and recordings into structured timestamps.',
      icon: ListMusic,
      status: 'planned' as const,
      phase: 'Phase 13E.2',
    },
    {
      id: 'audio_to_text',
      title: 'Audio to Text',
      desc: 'Fast voice-to-text transcription for notes and document drafting.',
      icon: FileCode,
      status: 'planned' as const,
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
                {capabilities?.version ? `v${capabilities.version}` : 'Phase 13E.1'}
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
              Media Extraction & Conversion Hub
            </h1>
            <p className="text-slate-400 text-sm mt-1 max-w-2xl">
              Modular media tools for extracting pristine audio, transcripts, subtitles, and synthesized speech without altering original project data.
            </p>
          </div>

          <button
            onClick={() => setShowLanguageInfo(!showLanguageInfo)}
            className="self-start md:self-auto inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium bg-slate-800/80 hover:bg-slate-800 text-slate-300 border border-slate-700/60 transition-colors shadow-sm"
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
              <span className="font-semibold text-slate-200 block mb-1.5 flex items-center gap-2">
                <FileAudio className="w-4 h-4 text-indigo-400" />
                Audio Extraction (13E.1)
              </span>
              <p className="text-slate-400 leading-relaxed">
                Universal container support (MP4, MOV, MKV, WebM). Direct stream remuxing for AAC/M4A and high-fidelity 192k MP3 & 16-bit WAV PCM encoding.
              </p>
            </div>
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              <span className="font-semibold text-slate-200 block mb-1.5 flex items-center gap-2">
                <FileText className="w-4 h-4 text-amber-400" />
                Speech-to-Text (13E.2)
              </span>
              <p className="text-slate-400 leading-relaxed">
                English speech transcription powered by Faster-Whisper with word/segment timestamps. Khmer ASR planned upon verification.
              </p>
            </div>
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              <span className="font-semibold text-slate-200 block mb-1.5 flex items-center gap-2">
                <Mic2 className="w-4 h-4 text-emerald-400" />
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

      {/* Active Tool: Video to Audio Studio */}
      {selectedTool === 'video_to_audio' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Main Processing Panel */}
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

            {/* Error Banner */}
            {error && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold">Error:</span> {error}
                </div>
              </div>
            )}

            {/* Input Selection Tabs */}
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
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all ${
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
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all ${
                    inputMode === 'project'
                      ? 'bg-white text-slate-900 shadow-sm font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <FolderGit2 className="w-3.5 h-3.5" />
                  Select Project Video
                </button>
              </div>

              {/* Upload Dropzone */}
              {inputMode === 'upload' && (
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
                      <p className="text-xs text-slate-400">
                        Supports MP4, MOV, MKV, WebM (up to 500 MB)
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Existing Project Selector */}
              {inputMode === 'project' && (
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

            {/* Target Audio Format Selector */}
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                2. Target Audio Format
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <button
                  type="button"
                  onClick={() => setTargetFormat('mp3')}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    targetFormat === 'mp3'
                      ? 'border-indigo-600 bg-indigo-50/50 ring-1 ring-indigo-600 text-slate-900'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-sm">MP3</span>
                    <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-slate-200/60 text-slate-700">
                      Universal
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-snug">
                    192 kbps high fidelity CBR/VBR encoding for universal playback.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setTargetFormat('wav')}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    targetFormat === 'wav'
                      ? 'border-indigo-600 bg-indigo-50/50 ring-1 ring-indigo-600 text-slate-900'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-sm">WAV</span>
                    <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">
                      Lossless
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-snug">
                    Uncompressed 16-bit PCM studio audio, ideal for downstream processing.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setTargetFormat('m4a')}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    targetFormat === 'm4a'
                      ? 'border-indigo-600 bg-indigo-50/50 ring-1 ring-indigo-600 text-slate-900'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-sm">M4A</span>
                    <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                      Stream Remux
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-snug">
                    High-efficiency AAC; uses direct stream copy if video has AAC.
                  </p>
                </button>
              </div>
            </div>

            {/* Progress Bar (Visible while extracting) */}
            {isExtracting && (
              <div className="space-y-2 p-4 rounded-xl bg-slate-50 border border-slate-200">
                <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                    {statusMessage || 'Extracting audio...'}
                  </span>
                  <span>{extractionProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${extractionProgress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Action Button */}
            <button
              onClick={handleExtractAudio}
              disabled={isExtracting || (inputMode === 'upload' && !selectedFile) || (inputMode === 'project' && !selectedProjectId)}
              className="w-full py-3 px-4 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white shadow-sm transition-all duration-150 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {isExtracting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Extracting Audio Track...
                </>
              ) : (
                <>
                  <FileAudio className="w-4 h-4" />
                  Extract Audio Track ({targetFormat.toUpperCase()})
                </>
              )}
            </button>
          </div>

          {/* Result & Preview Panel */}
          <div className="lg:col-span-5 space-y-6">
            {activeTask && activeTask.status === 'completed' ? (
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

                  {/* Metadata Chips */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center gap-2">
                      <Clock className="w-4 h-4 text-indigo-500 shrink-0" />
                      <div>
                        <span className="text-slate-400 text-[10px] block">Duration</span>
                        <span className="font-semibold text-slate-700">
                          {formatDuration(activeTask.output_duration_seconds)}
                        </span>
                      </div>
                    </div>

                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center gap-2">
                      <HardDrive className="w-4 h-4 text-emerald-500 shrink-0" />
                      <div>
                        <span className="text-slate-400 text-[10px] block">File Size</span>
                        <span className="font-semibold text-slate-700">
                          {formatBytes(activeTask.output_file_size_bytes)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Audio Specs Table */}
                  {activeTask.output_media_metadata && (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs text-slate-600 space-y-1">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Audio Codec:</span>
                        <span className="font-mono font-medium text-slate-800">
                          {activeTask.output_media_metadata.codec_name}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Sample Rate:</span>
                        <span className="font-medium text-slate-800">
                          {activeTask.output_media_metadata.sample_rate} Hz
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Channels:</span>
                        <span className="font-medium text-slate-800">
                          {activeTask.output_media_metadata.channels === 1 ? 'Mono (1 ch)' : 'Stereo (2 ch)'}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Player & Download Actions */}
                <div className="pt-2 flex flex-col sm:flex-row gap-2.5">
                  <button
                    onClick={() => handleTogglePlay(activeTask.id)}
                    className="flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-white flex items-center justify-center gap-2 transition-colors cursor-pointer"
                  >
                    {playingTaskId === activeTask.id ? (
                      <>
                        <Pause className="w-4 h-4" />
                        Pause Audio
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        Play Preview
                      </>
                    )}
                  </button>

                  <a
                    href={api.getToolkitAudioDownloadUrl(activeTask.id)}
                    download
                    className="py-2.5 px-4 rounded-xl text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 flex items-center justify-center gap-2 transition-colors"
                  >
                    <Download className="w-4 h-4" />
                    Download {activeTask.target_format.toUpperCase()}
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

            {/* Quick Tips Box */}
            <div className="p-4 rounded-xl bg-slate-100/70 border border-slate-200 text-xs text-slate-600 space-y-2">
              <span className="font-bold text-slate-700 flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-indigo-600" />
                Audio Extraction Best Practices
              </span>
              <ul className="space-y-1 list-disc list-inside text-slate-500">
                <li>Choose <strong>WAV</strong> if you plan to transcribe audio with custom models.</li>
                <li>Choose <strong>MP3</strong> for general listening, podcast distribution, and smaller file size.</li>
                <li>Choose <strong>M4A</strong> for fastest extraction when the video source already has AAC audio.</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Task History Section */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-slate-900 text-base">Extraction Workspace History</h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">
              {tasks.length}
            </span>
          </div>

          <button
            onClick={fetchTasks}
            disabled={tasksLoading}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
            title="Refresh history"
          >
            <RefreshCw className={`w-4 h-4 ${tasksLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {tasks.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-xs">
            No extraction tasks yet. Extracted files will appear here for playback and download.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 font-semibold uppercase tracking-wider">
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Source Video</th>
                  <th className="py-2.5 px-3">Format</th>
                  <th className="py-2.5 px-3">Duration</th>
                  <th className="py-2.5 px-3">Size</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {tasks.map((task) => (
                  <tr key={task.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="py-3 px-3 text-slate-400 whitespace-nowrap">
                      {new Date(task.created_at).toLocaleDateString()} {new Date(task.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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
                    <td className="py-3 px-3 whitespace-nowrap text-slate-500">
                      {formatBytes(task.output_file_size_bytes)}
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
                    <td className="py-3 px-3 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        {task.status === 'completed' && (
                          <>
                            <button
                              onClick={() => {
                                setActiveTask(task);
                                handleTogglePlay(task.id);
                              }}
                              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-slate-900 transition-colors"
                              title="Play/Pause Audio"
                            >
                              {playingTaskId === task.id ? (
                                <Pause className="w-4 h-4 text-indigo-600" />
                              ) : (
                                <Play className="w-4 h-4" />
                              )}
                            </button>

                            <a
                              href={api.getToolkitAudioDownloadUrl(task.id)}
                              download
                              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors"
                              title="Download Extracted File"
                            >
                              <Download className="w-4 h-4" />
                            </a>
                          </>
                        )}

                        <button
                          onClick={() => handleDeleteTask(task.id)}
                          className="p-1.5 rounded-lg hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors"
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
