import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ArrowLeft,
  UploadCloud,
  FileVideo,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Clock,
  Music,
  Maximize2,
  FileCheck,
  FileText,
  Edit2,
  Save,
  X,
  Sparkles,
  RotateCcw,
} from 'lucide-react';
import { ProjectDetail, TranscriptSegment } from '../types';
import { api } from '../services/api';

interface ProjectWorkspaceProps {
  projectId: string;
  onBack: () => void;
  onProjectUpdated?: () => void;
}

export const ProjectWorkspace: React.FC<ProjectWorkspaceProps> = ({
  projectId,
  onBack,
  onProjectUpdated,
}) => {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadStatusText, setUploadStatusText] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<boolean>(false);
  const [retryingExtraction, setRetryingExtraction] = useState<boolean>(false);

  // Transcription state
  const [transcriptSegments, setTranscriptSegments] = useState<TranscriptSegment[]>([]);
  const [transcribing, setTranscribing] = useState<boolean>(false);
  const [transcriptionError, setTranscriptionError] = useState<string | null>(null);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState<string>('');
  const [savingSegmentId, setSavingSegmentId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchTranscriptData = useCallback(async () => {
    try {
      const data = await api.getTranscript(projectId);
      setTranscriptSegments(data.segments);
    } catch (err: any) {
      console.error('Failed to load transcript:', err);
    }
  }, [projectId]);

  const fetchProjectData = useCallback(async () => {
    try {
      const data = await api.getProject(projectId);
      setProject(data);
      if (data.status === 'transcribed' || (data.transcript_segments && data.transcript_segments.length > 0)) {
        await fetchTranscriptData();
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load project details');
    } finally {
      setLoading(false);
    }
  }, [projectId, fetchTranscriptData]);

  useEffect(() => {
    fetchProjectData();
  }, [fetchProjectData]);

  // Polling for background audio extraction or transcription jobs
  useEffect(() => {
    if (!project) return;
    const isExtracting =
      project.status === 'uploaded' ||
      project.jobs?.some((j) => j.job_type === 'extract_audio' && (j.status === 'pending' || j.status === 'running'));

    const isSttRunning =
      project.status === 'transcribing' ||
      project.jobs?.some((j) => j.job_type === 'transcribe' && (j.status === 'pending' || j.status === 'running'));

    if (isSttRunning) {
      setTranscribing(true);
    }

    if (!isExtracting && !isSttRunning) return;

    const interval = setInterval(async () => {
      try {
        const data = await api.getProject(projectId);
        setProject(data);

        // Check if transcription just finished
        if (isSttRunning) {
          const transJob = data.jobs?.find((j) => j.job_type === 'transcribe');
          if (transJob?.status === 'completed' || data.status === 'transcribed') {
            setTranscribing(false);
            setTranscriptionError(null);
            await fetchTranscriptData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (transJob?.status === 'failed' || data.status === 'failed') {
            setTranscribing(false);
            setTranscriptionError(transJob?.error_message || 'Transcription failed.');
            if (onProjectUpdated) onProjectUpdated();
          }
        }

        if (isExtracting && (data.status === 'audio_extracted' || data.status === 'failed')) {
          if (onProjectUpdated) onProjectUpdated();
        }
      } catch (err) {
        console.error('Error polling project status:', err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [project, projectId, fetchTranscriptData, onProjectUpdated]);

  const handleFileSelect = async (file: File) => {
    setError(null);

    if (!file.name.toLowerCase().endsWith('.mp4') && !file.name.toLowerCase().endsWith('.mov')) {
      setError('Invalid file format. Please upload an MP4 video file.');
      return;
    }

    const maxBytes = 500 * 1024 * 1024;
    if (file.size > maxBytes) {
      setError(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)} MB). Maximum limit is 500 MB.`);
      return;
    }

    if (file.size === 0) {
      setError('Uploaded file is empty (0 bytes).');
      return;
    }

    try {
      setUploading(true);
      setUploadProgress(0);
      setUploadStatusText('Uploading video to storage...');

      await api.uploadVideo(projectId, file, (pct) => {
        setUploadProgress(pct);
        if (pct >= 100) {
          setUploadStatusText('Inspecting media container with FFprobe...');
        }
      });

      setUploadStatusText('Upload successful! Initializing audio extraction...');
      await fetchProjectData();
      if (onProjectUpdated) onProjectUpdated();
    } catch (err: any) {
      setError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
      setUploadProgress(0);
      setUploadStatusText('');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleRetryExtraction = async () => {
    try {
      setRetryingExtraction(true);
      setError(null);
      await api.triggerAudioExtraction(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setError(err.message || 'Failed to retry extraction');
    } finally {
      setRetryingExtraction(false);
    }
  };

  // Start Speech-to-Text Transcription
  const handleStartTranscription = async () => {
    try {
      setTranscribing(true);
      setTranscriptionError(null);
      await api.startTranscription(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setTranscribing(false);
      setTranscriptionError(err.message || 'Failed to start transcription');
    }
  };

  // Inline editing functions
  const handleStartEdit = (segment: TranscriptSegment) => {
    setEditingSegmentId(segment.id);
    setEditingText(segment.text);
  };

  const handleCancelEdit = () => {
    setEditingSegmentId(null);
    setEditingText('');
  };

  const handleSaveEdit = async (segmentId: string) => {
    if (!editingText.trim()) return;
    try {
      setSavingSegmentId(segmentId);
      const updated = await api.updateTranscriptSegment(projectId, segmentId, editingText.trim());
      setTranscriptSegments((prev) =>
        prev.map((s) => (s.id === segmentId ? { ...s, text: updated.text } : s))
      );
      setEditingSegmentId(null);
      setEditingText('');
    } catch (err: any) {
      alert(`Error saving segment: ${err.message}`);
    } finally {
      setSavingSegmentId(null);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes >= 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  const formatTimestamp = (seconds: number): string => {
    if (seconds < 0) seconds = 0;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-20 text-slate-500 text-sm">
        Loading project workspace...
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-8 text-center">
        <p className="text-rose-600 mb-4">Project not found</p>
        <button
          onClick={onBack}
          className="px-4 py-2 bg-slate-200 text-slate-700 rounded-lg text-sm"
        >
          Back to Projects
        </button>
      </div>
    );
  }

  const latestExtractJob = project.jobs?.find((j) => j.job_type === 'extract_audio');
  const latestSttJob = project.jobs?.find((j) => j.job_type === 'transcribe');

  const isAudioReady = project.status === 'audio_extracted' || !!project.video?.extracted_audio_path;
  const isExtractionFailed = latestExtractJob?.status === 'failed' && !project.video?.extracted_audio_path;
  const isExtracting =
    !isAudioReady &&
    !isExtractionFailed &&
    (project.status === 'uploaded' || latestExtractJob?.status === 'running' || latestExtractJob?.status === 'pending');

  const isTranscribed =
    project.status === 'transcribed' ||
    transcriptSegments.length > 0 ||
    latestSttJob?.status === 'completed';

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Top Navigation & Project Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 transition-colors"
            title="Back to Projects"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-slate-900">{project.title}</h2>
              <span className="text-xs px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-semibold border border-indigo-200 uppercase">
                {project.original_language} → {project.target_language}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">ID: {project.id}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchProjectData}
            className="p-2 rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-100 transition-colors"
            title="Refresh Status"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <span className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider bg-slate-100 text-slate-700 border border-slate-200">
            {project.status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Dubbing Stepper Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div className="grid grid-cols-5 gap-2 text-center text-xs">
          <div
            className={`p-2.5 rounded-lg border font-semibold ${
              isAudioReady
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                : 'bg-indigo-50 border-indigo-300 text-indigo-700'
            }`}
          >
            1. Video & Audio {isAudioReady && '✓'}
          </div>
          <div
            className={`p-2.5 rounded-lg border font-semibold ${
              isTranscribed
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                : isAudioReady
                ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            2. Transcribe {isTranscribed && '✓'}
          </div>
          <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-400">
            3. Translate (P4)
          </div>
          <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-400">
            4. Khmer Voice (P5)
          </div>
          <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-400">
            5. Export Dub (P6)
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block mb-0.5">Operation Error</span>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Section 1: Video Upload & Audio Extraction */}
      {!project.video ? (
        /* Dropzone Upload View */
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-10">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all ${
              dragOver
                ? 'border-indigo-500 bg-indigo-50/50'
                : 'border-slate-300 bg-slate-50/50 hover:bg-slate-50'
            }`}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => e.target.files && e.target.files[0] && handleFileSelect(e.target.files[0])}
              accept="video/mp4,video/quicktime"
              className="hidden"
            />

            <div className="w-16 h-16 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center mx-auto mb-4 shadow-sm">
              <UploadCloud className="w-8 h-8" />
            </div>

            <h3 className="text-base font-bold text-slate-800">
              Drag and drop your English MP4 video here
            </h3>
            <p className="text-xs text-slate-500 mt-1.5 max-w-sm mx-auto">
              Accepts MP4 container with video and audio tracks. Up to 500 MB.
            </p>

            <div className="mt-6">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="px-6 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-semibold transition-colors shadow-sm"
              >
                {uploading ? 'Processing...' : 'Browse Video File'}
              </button>
            </div>

            {uploading && (
              <div className="mt-8 max-w-md mx-auto space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
                  <span>{uploadStatusText}</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-2.5 rounded-full transition-all duration-200"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Video Uploaded: Preview & Metadata & Audio Extraction View */
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left 7 Columns: Video Player Preview */}
            <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileVideo className="w-4 h-4 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-800">Video Preview</h3>
                </div>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 underline"
                >
                  Replace Video
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={(e) => e.target.files && e.target.files[0] && handleFileSelect(e.target.files[0])}
                  accept="video/mp4,video/quicktime"
                  className="hidden"
                />
              </div>

              {/* HTML5 Video Player */}
              <div className="rounded-xl overflow-hidden bg-black aspect-video relative flex items-center justify-center">
                <video
                  src={api.getVideoUrl(projectId)}
                  controls
                  playsInline
                  className="w-full h-full object-contain"
                />
              </div>

              <div className="flex items-center justify-between text-xs text-slate-500 font-mono">
                <span>{project.video.filename}</span>
                <span>{formatFileSize(project.video.file_size_bytes)}</span>
              </div>
            </div>

            {/* Right 5 Columns: Metadata & Extraction Status */}
            <div className="lg:col-span-5 space-y-6">
              {/* Media Metadata Card */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
                <div className="flex items-center gap-2 text-slate-800 font-bold text-sm">
                  <FileCheck className="w-4 h-4 text-emerald-600" />
                  <span>FFprobe Media Metadata</span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-400 block mb-1">Duration</span>
                    <span className="font-semibold text-slate-800 flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      {formatTimestamp(project.video.duration_seconds || 0)} ({project.video.duration_seconds}s)
                    </span>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-400 block mb-1">Resolution</span>
                    <span className="font-semibold text-slate-800 flex items-center gap-1">
                      <Maximize2 className="w-3.5 h-3.5 text-slate-500" />
                      {project.video.width || '?'} × {project.video.height || '?'}
                    </span>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-400 block mb-1">Video Codec</span>
                    <span className="font-mono font-semibold text-slate-800 uppercase">
                      {project.video.video_codec || 'Unknown'}
                    </span>
                  </div>

                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                    <span className="text-slate-400 block mb-1">Audio Codec</span>
                    <span className="font-mono font-semibold text-slate-800 uppercase">
                      {project.video.audio_codec || 'None'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Audio Extraction Status Card */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-slate-800 font-bold text-sm">
                    <Music className="w-4 h-4 text-indigo-600" />
                    <span>FFmpeg Audio Extraction</span>
                  </div>
                  {isAudioReady && (
                    <span className="text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Ready (16kHz WAV)
                    </span>
                  )}
                </div>

                {isAudioReady ? (
                  <div className="space-y-3">
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                      <audio
                        src={api.getAudioUrl(projectId)}
                        controls
                        className="w-full h-10"
                      />
                    </div>
                  </div>
                ) : isExtracting ? (
                  <div className="p-6 rounded-xl bg-indigo-50/50 border border-indigo-200 text-center space-y-3">
                    <RefreshCw className="w-6 h-6 text-indigo-600 animate-spin mx-auto" />
                    <div>
                      <h4 className="text-xs font-bold text-indigo-900">Extracting Audio Track...</h4>
                      <p className="text-xs text-indigo-700 mt-1">
                        Converting audio to 16kHz mono WAV via FFmpeg in the background.
                      </p>
                    </div>
                  </div>
                ) : isExtractionFailed ? (
                  <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 space-y-3">
                    <div className="flex items-start gap-2 text-rose-800 text-xs">
                      <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold block">Audio Extraction Failed</span>
                        <p className="text-rose-700 mt-0.5">
                          {latestExtractJob?.error_message || 'Could not extract audio track.'}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={handleRetryExtraction}
                      disabled={retryingExtraction}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${retryingExtraction ? 'animate-spin' : ''}`} />
                      {retryingExtraction ? 'Retrying...' : 'Retry Audio Extraction'}
                    </button>
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-500">
                    Audio extraction is scheduled.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Section 2: English Automatic Speech Recognition (faster-whisper) */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
            {/* Header & Controls */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-base font-bold text-slate-900 uppercase tracking-wide">
                    English Transcription
                  </h3>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="px-2 py-0.5 rounded bg-slate-100 font-medium text-slate-700 border border-slate-200">
                    Model: faster-whisper base (int8 / CPU)
                  </span>
                  <span>•</span>
                  <span>
                    Status:{' '}
                    <strong className="capitalize text-slate-800">
                      {transcribing
                        ? 'Transcribing...'
                        : isTranscribed
                        ? 'Completed'
                        : latestSttJob?.status || 'Pending'}
                    </strong>
                  </span>
                </div>
              </div>

              {/* Action Button */}
              <div>
                {!isTranscribed ? (
                  <button
                    onClick={handleStartTranscription}
                    disabled={!isAudioReady || transcribing}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs sm:text-sm font-semibold transition-colors shadow-sm"
                  >
                    {transcribing ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Transcribing Speech...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        <span>Start Transcription</span>
                      </>
                    )}
                  </button>
                ) : (
                  <button
                    onClick={handleStartTranscription}
                    disabled={transcribing}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-50 text-slate-700 text-xs font-semibold transition-colors"
                  >
                    <RotateCcw className={`w-3.5 h-3.5 ${transcribing ? 'animate-spin' : ''}`} />
                    <span>{transcribing ? 'Retranscribing...' : 'Retranscribe'}</span>
                  </button>
                )}
              </div>
            </div>

            {/* Error Banner */}
            {transcriptionError && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Transcription Error</span>
                    <span>{transcriptionError}</span>
                  </div>
                </div>
                <button
                  onClick={handleStartTranscription}
                  className="px-3 py-1 rounded bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs shrink-0"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Transcription State Displays */}
            {transcribing ? (
              <div className="p-12 text-center bg-slate-50/60 rounded-xl border border-slate-200 space-y-3">
                <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
                <h4 className="text-sm font-bold text-slate-800">
                  Transcribing English Audio with faster-whisper...
                </h4>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  Running speech recognition inference with voice activity detection (VAD). This typically takes a few seconds.
                </p>
              </div>
            ) : transcriptSegments.length > 0 ? (
              /* Segment List */
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs text-slate-500 pb-2">
                  <span>
                    Total Segments:{' '}
                    <strong className="text-slate-800 font-semibold">
                      {transcriptSegments.length}
                    </strong>
                  </span>
                  <span>Click [Edit] on any segment to correct recognized words</span>
                </div>

                <div className="space-y-3">
                  {transcriptSegments.map((seg) => {
                    const isEditing = editingSegmentId === seg.id;
                    const isSaving = savingSegmentId === seg.id;

                    return (
                      <div
                        key={seg.id}
                        className={`p-4 rounded-xl border transition-all ${
                          isEditing
                            ? 'bg-indigo-50/40 border-indigo-300 ring-2 ring-indigo-500/20'
                            : 'bg-slate-50/50 border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 space-y-2">
                            {/* Segment header: order & timestamp */}
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                                #{seg.segment_order}
                              </span>
                              <span className="text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded border border-indigo-200 flex items-center gap-1">
                                <Clock className="w-3 h-3 text-indigo-500" />
                                {formatTimestamp(seg.start_time)} – {formatTimestamp(seg.end_time)}
                              </span>
                              <span className="text-[11px] text-slate-400 font-mono">
                                ({(seg.end_time - seg.start_time).toFixed(1)}s)
                              </span>
                            </div>

                            {/* Text content or edit textarea */}
                            {isEditing ? (
                              <div className="space-y-2 pt-1">
                                <textarea
                                  value={editingText}
                                  onChange={(e) => setEditingText(e.target.value)}
                                  rows={2}
                                  className="w-full px-3 py-2 text-sm rounded-lg border border-indigo-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 font-sans"
                                  autoFocus
                                />
                                <div className="flex items-center gap-2">
                                  <button
                                    onClick={() => handleSaveEdit(seg.id)}
                                    disabled={isSaving || !editingText.trim()}
                                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm"
                                  >
                                    <Save className="w-3.5 h-3.5" />
                                    {isSaving ? 'Saving...' : 'Save'}
                                  </button>
                                  <button
                                    onClick={handleCancelEdit}
                                    disabled={isSaving}
                                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-600 text-xs font-medium"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <p className="text-sm text-slate-800 leading-relaxed font-normal">
                                {seg.text}
                              </p>
                            )}
                          </div>

                          {!isEditing && (
                            <button
                              onClick={() => handleStartEdit(seg)}
                              className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors shrink-0"
                              title="Edit segment text"
                            >
                              <Edit2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Prompt to start transcription */
              <div className="p-8 text-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <h4 className="text-sm font-semibold text-slate-700">No transcript generated yet</h4>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  Click the <strong>Start Transcription</strong> button above to transcribe the extracted audio with faster-whisper.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
