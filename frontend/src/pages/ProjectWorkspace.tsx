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
  Languages,
  AlertTriangle,
  Volume2,
  Headphones,
  Film,
  Download,
  Play,
  Square,
  Check,
  Layers,
} from 'lucide-react';
import {
  ProjectDetail,
  TranscriptSegment,
  TranslationSegment,
  GeneratedAudio,
  ExportStatusResponse,
  VoiceOption,
  TranslationProviderInfo,
  AlternativesResponse,
  AIImproveResponse,
} from '../types';
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

  // Translation state
  const [translationSegments, setTranslationSegments] = useState<TranslationSegment[]>([]);
  const [translating, setTranslating] = useState<boolean>(false);
  const [translationError, setTranslationError] = useState<string | null>(null);
  const [editingTransId, setEditingTransId] = useState<string | null>(null);
  const [editingTransText, setEditingTransText] = useState<string>('');
  const [savingTransId, setSavingTransId] = useState<string | null>(null);
  const [retranslatingTransId, setRetranslatingTransId] = useState<string | null>(null);

  // Translation Provider & Style state (Phase 9)
  const [translationProviders, setTranslationProviders] = useState<TranslationProviderInfo[]>([]);
  const [selectedTransProvider, setSelectedTransProvider] = useState<string>('nllb');
  const [selectedTransStyle, setSelectedTransStyle] = useState<string>('natural');
  const [updatingTransSettings, setUpdatingTransSettings] = useState<boolean>(false);

  // AI LLM Modal state (Phase 9: Improve & Alternatives)
  const [aiModalSegment, setAiModalSegment] = useState<TranslationSegment | null>(null);
  const [aiModalMode, setAiModalMode] = useState<'improve' | 'alternatives' | null>(null);
  const [improvingSegmentId, setImprovingSegmentId] = useState<string | null>(null);
  const [improvedResult, setImprovedResult] = useState<AIImproveResponse | null>(null);
  const [loadingAlternatives, setLoadingAlternatives] = useState<boolean>(false);
  const [alternativesResult, setAlternativesResult] = useState<AlternativesResponse | null>(null);
  const [applyingSuggestion, setApplyingSuggestion] = useState<boolean>(false);
  const [aiCustomPrompt, setAiCustomPrompt] = useState<string>('');

  // Text-to-Speech (gTTS & Edge TTS) state
  const [availableVoices, setAvailableVoices] = useState<VoiceOption[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<{ provider: string; voice: string }>({
    provider: 'gtts',
    voice: 'default',
  });
  const [updatingVoice, setUpdatingVoice] = useState<boolean>(false);
  const [previewingVoiceKey, setPreviewingVoiceKey] = useState<string | null>(null);
  const [generatedAudios, setGeneratedAudios] = useState<GeneratedAudio[]>([]);
  const [generatingVoice, setGeneratingVoice] = useState<boolean>(false);
  const [ttsError, setTtsError] = useState<string | null>(null);
  const [regeneratingAudioId, setRegeneratingAudioId] = useState<string | null>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);

  // Dubbing & Export state
  const [exportStatus, setExportStatus] = useState<ExportStatusResponse | null>(null);
  const [exporting, setExporting] = useState<boolean>(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchTranscriptData = useCallback(async () => {
    try {
      const data = await api.getTranscript(projectId);
      setTranscriptSegments(data.segments);
    } catch (err: any) {
      console.error('Failed to load transcript:', err);
    }
  }, [projectId]);

  const fetchTranslationData = useCallback(async () => {
    try {
      const data = await api.getTranslations(projectId);
      setTranslationSegments(data.segments);
    } catch (err: any) {
      console.error('Failed to load translations:', err);
    }
  }, [projectId]);

  const fetchAudioData = useCallback(async () => {
    try {
      const data = await api.getGeneratedAudios(projectId);
      setGeneratedAudios(data.audios);
    } catch (err: any) {
      console.error('Failed to load generated audios:', err);
    }
  }, [projectId]);

  const fetchExportData = useCallback(async () => {
    try {
      const data = await api.getExportStatus(projectId);
      setExportStatus(data);
    } catch (err: any) {
      console.error('Failed to load export status:', err);
    }
  }, [projectId]);

  const fetchVoices = useCallback(async () => {
    try {
      const data = await api.getVoices();
      setAvailableVoices(data.voices);
    } catch (err: any) {
      console.error('Failed to load available voices:', err);
    }
  }, []);

  const fetchTranslationProviders = useCallback(async () => {
    try {
      const data = await api.getTranslationProviders();
      setTranslationProviders(data.providers);
    } catch (err: any) {
      console.error('Failed to load translation providers:', err);
    }
  }, []);

  const fetchProjectData = useCallback(async () => {
    try {
      const data = await api.getProject(projectId);
      setProject(data);
      if (data.tts_provider && data.tts_voice) {
        setSelectedVoice({
          provider: data.tts_provider,
          voice: data.tts_voice,
        });
      }
      if (data.translation_provider) {
        setSelectedTransProvider(data.translation_provider);
      }
      if (data.translation_style) {
        setSelectedTransStyle(data.translation_style);
      }
      if (
        data.status === 'transcribed' ||
        data.status === 'translating' ||
        data.status === 'translated' ||
        data.status === 'generating_voice' ||
        data.status === 'voice_generated' ||
        data.status === 'synchronizing' ||
        data.status === 'completed' ||
        (data.transcript_segments && data.transcript_segments.length > 0)
      ) {
        await fetchTranscriptData();
      }
      if (
        data.status === 'translated' ||
        data.status === 'generating_voice' ||
        data.status === 'voice_generated' ||
        data.status === 'synchronizing' ||
        data.status === 'completed' ||
        (data.translation_segments && data.translation_segments.length > 0)
      ) {
        await fetchTranslationData();
      }
      if (
        data.status === 'voice_generated' ||
        data.status === 'generating_voice' ||
        data.status === 'synchronizing' ||
        data.status === 'completed' ||
        (data.generated_audios && data.generated_audios.length > 0)
      ) {
        await fetchAudioData();
      }
      if (
        data.status === 'voice_generated' ||
        data.status === 'synchronizing' ||
        data.status === 'completed' ||
        !!data.video?.exported_video_path
      ) {
        await fetchExportData();
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load project details');
    } finally {
      setLoading(false);
    }
  }, [projectId, fetchTranscriptData, fetchTranslationData, fetchAudioData, fetchExportData]);

  useEffect(() => {
    fetchVoices();
    fetchTranslationProviders();
    fetchProjectData();
    return () => {
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
    };
  }, [fetchVoices, fetchTranslationProviders, fetchProjectData]);

  // Polling for background audio extraction, transcription, translation, TTS, or dubbing jobs
  useEffect(() => {
    if (!project) return;
    const isExtracting =
      project.status === 'uploaded' ||
      project.jobs?.some((j) => j.job_type === 'extract_audio' && (j.status === 'pending' || j.status === 'running'));

    const isSttRunning =
      project.status === 'transcribing' ||
      project.jobs?.some((j) => j.job_type === 'transcribe' && (j.status === 'pending' || j.status === 'running'));

    const isTransRunning =
      project.status === 'translating' ||
      project.jobs?.some((j) => j.job_type === 'translate' && (j.status === 'pending' || j.status === 'running'));

    const isTtsRunning =
      project.status === 'generating_voice' ||
      project.jobs?.some((j) => j.job_type === 'tts' && (j.status === 'pending' || j.status === 'running'));

    const isDubRunning =
      project.status === 'synchronizing' ||
      project.jobs?.some((j) => j.job_type === 'dub' && (j.status === 'pending' || j.status === 'running'));

    if (isSttRunning) {
      setTranscribing(true);
    }
    if (isTransRunning) {
      setTranslating(true);
    }
    if (isTtsRunning) {
      setGeneratingVoice(true);
    }
    if (isDubRunning) {
      setExporting(true);
    }

    if (!isExtracting && !isSttRunning && !isTransRunning && !isTtsRunning && !isDubRunning) return;

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

        // Check if translation just finished
        if (isTransRunning) {
          const translateJob = data.jobs?.find((j) => j.job_type === 'translate');
          if (translateJob?.status === 'completed' || data.status === 'translated') {
            setTranslating(false);
            setTranslationError(null);
            await fetchTranslationData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (translateJob?.status === 'failed' || data.status === 'failed') {
            setTranslating(false);
            setTranslationError(translateJob?.error_message || 'Translation failed.');
            if (onProjectUpdated) onProjectUpdated();
          }
        }

        // Check if TTS just finished
        if (isTtsRunning) {
          const ttsJob = data.jobs?.find((j) => j.job_type === 'tts');
          if (ttsJob?.status === 'completed' || data.status === 'voice_generated') {
            setGeneratingVoice(false);
            setTtsError(null);
            await fetchAudioData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (ttsJob?.status === 'failed' || data.status === 'failed') {
            setGeneratingVoice(false);
            setTtsError(ttsJob?.error_message || 'TTS speech synthesis failed.');
            if (onProjectUpdated) onProjectUpdated();
          }
        }

        // Check if Dubbing export just finished
        if (isDubRunning) {
          const dubJob = data.jobs?.find((j) => j.job_type === 'dub');
          if (dubJob?.status === 'completed' || data.status === 'completed') {
            setExporting(false);
            setExportError(null);
            await fetchExportData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (dubJob?.status === 'failed' || data.status === 'failed') {
            setExporting(false);
            setExportError(dubJob?.error_message || 'Video dubbing export failed.');
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
  }, [project, projectId, fetchTranscriptData, fetchTranslationData, fetchAudioData, fetchExportData, onProjectUpdated]);

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
      // Mark linked translation as outdated in frontend state
      setTranslationSegments((prev) =>
        prev.map((s) => (s.transcript_segment_id === segmentId ? { ...s, is_outdated: true } : s))
      );
      setEditingSegmentId(null);
      setEditingText('');
    } catch (err: any) {
      alert(`Error saving segment: ${err.message}`);
    } finally {
      setSavingSegmentId(null);
    }
  };

  // Translation Handlers
  const handleStartTranslation = async () => {
    try {
      setTranslating(true);
      setTranslationError(null);
      await api.startTranslation(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setTranslating(false);
      setTranslationError(err.message || 'Failed to start translation');
    }
  };

  const handleStartEditTrans = (seg: TranslationSegment) => {
    setEditingTransId(seg.id);
    setEditingTransText(seg.khmer_text);
  };

  const handleCancelEditTrans = () => {
    setEditingTransId(null);
    setEditingTransText('');
  };

  const handleSaveEditTrans = async (segmentId: string) => {
    if (!editingTransText.trim()) return;
    try {
      setSavingTransId(segmentId);
      const updated = await api.updateTranslationSegment(projectId, segmentId, editingTransText.trim());
      setTranslationSegments((prev) =>
        prev.map((s) => (s.id === segmentId ? updated : s))
      );
      setEditingTransId(null);
      setEditingTransText('');
      // Invalidate audio record on frontend to reflect outdated status immediately
      await fetchAudioData();
    } catch (err: any) {
      alert(`Error saving translation: ${err.message}`);
    } finally {
      setSavingTransId(null);
    }
  };

  const handleRetranslateSegment = async (segmentId: string) => {
    try {
      setRetranslatingTransId(segmentId);
      const updated = await api.retranslateSegment(projectId, segmentId);
      setTranslationSegments((prev) =>
        prev.map((s) => (s.id === segmentId ? updated : s))
      );
      // Invalidate audio record on frontend
      await fetchAudioData();
    } catch (err: any) {
      alert(`Error retranslating segment: ${err.message}`);
    } finally {
      setRetranslatingTransId(null);
    }
  };

  const handleUpdateTranslationSettings = async (provider: string, style: string) => {
    try {
      setUpdatingTransSettings(true);
      setSelectedTransProvider(provider);
      setSelectedTransStyle(style);
      const updated = await api.updateProjectTranslationSettings(projectId, {
        translation_provider: provider,
        translation_style: style,
      });
      setProject(updated);
      if (onProjectUpdated) onProjectUpdated();
    } catch (err: any) {
      alert(`Failed to update translation settings: ${err.message}`);
    } finally {
      setUpdatingTransSettings(false);
    }
  };

  const handleOpenAiImprove = async (seg: TranslationSegment) => {
    setAiModalSegment(seg);
    setAiModalMode('improve');
    setImprovedResult(null);
    setAiCustomPrompt('');
    setImprovingSegmentId(seg.id);
    try {
      const res = await api.aiImproveSegment(projectId, seg.id, {
        style: selectedTransStyle,
      });
      setImprovedResult(res);
    } catch (err: any) {
      alert(`AI improvement failed: ${err.message}`);
      setAiModalSegment(null);
      setAiModalMode(null);
    } finally {
      setImprovingSegmentId(null);
    }
  };

  const handleRerunAiImprove = async () => {
    if (!aiModalSegment) return;
    setImprovingSegmentId(aiModalSegment.id);
    try {
      const res = await api.aiImproveSegment(projectId, aiModalSegment.id, {
        style: selectedTransStyle,
        custom_prompt: aiCustomPrompt.trim() || undefined,
      });
      setImprovedResult(res);
    } catch (err: any) {
      alert(`AI improvement failed: ${err.message}`);
    } finally {
      setImprovingSegmentId(null);
    }
  };

  const handleOpenAlternatives = async (seg: TranslationSegment) => {
    setAiModalSegment(seg);
    setAiModalMode('alternatives');
    setAlternativesResult(null);
    setLoadingAlternatives(true);
    try {
      const res = await api.getTranslationAlternatives(projectId, seg.id);
      setAlternativesResult(res);
    } catch (err: any) {
      alert(`Failed to generate alternatives: ${err.message}`);
      setAiModalSegment(null);
      setAiModalMode(null);
    } finally {
      setLoadingAlternatives(false);
    }
  };

  const handleApplySuggestion = async (
    khmerText: string,
    style?: string,
    explanation?: string
  ) => {
    if (!aiModalSegment) return;
    try {
      setApplyingSuggestion(true);
      const updated = await api.applyTranslationSuggestion(projectId, aiModalSegment.id, {
        khmer_text: khmerText,
        style: style || undefined,
        explanation: explanation || undefined,
      });
      setTranslationSegments((prev) =>
        prev.map((s) => (s.id === aiModalSegment.id ? updated : s))
      );
      setAiModalSegment(null);
      setAiModalMode(null);
      setImprovedResult(null);
      setAlternativesResult(null);
      await fetchAudioData();
      await fetchExportData();
    } catch (err: any) {
      alert(`Failed to apply translation suggestion: ${err.message}`);
    } finally {
      setApplyingSuggestion(false);
    }
  };

  // Voice Selection & Preview Handlers
  const handleSelectVoice = async (provider: string, voice: string) => {
    if (selectedVoice.provider === provider && selectedVoice.voice === voice) return;
    try {
      setUpdatingVoice(true);
      setSelectedVoice({ provider, voice });
      const updatedProject = await api.updateProjectVoice(projectId, provider, voice);
      setProject(updatedProject);
      await fetchAudioData();
      await fetchExportData();
      if (onProjectUpdated) onProjectUpdated();
    } catch (err: any) {
      alert(`Failed to update voice: ${err.message}`);
    } finally {
      setUpdatingVoice(false);
    }
  };

  const handlePreviewVoice = async (provider: string, voice: string) => {
    const key = `${provider}:${voice}`;
    try {
      if (previewingVoiceKey === key && previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
        setPreviewingVoiceKey(null);
        return;
      }
      setPreviewingVoiceKey(key);
      const audioBlob = await api.previewVoice(provider, voice);
      const audioUrl = URL.createObjectURL(audioBlob);
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
      }
      const audio = new Audio(audioUrl);
      previewAudioRef.current = audio;
      audio.onended = () => {
        setPreviewingVoiceKey(null);
      };
      audio.onerror = () => {
        setPreviewingVoiceKey(null);
      };
      await audio.play();
    } catch (err: any) {
      alert(`Preview failed: ${err.message}`);
      setPreviewingVoiceKey(null);
    }
  };

  // Text-to-Speech (gTTS & Edge TTS) Handlers
  const handleStartTTS = async () => {
    try {
      setGeneratingVoice(true);
      setTtsError(null);
      await api.startTTS(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setGeneratingVoice(false);
      setTtsError(err.message || 'Failed to start Khmer speech synthesis');
    }
  };

  const handleRegenerateSegmentAudio = async (segmentId: string) => {
    try {
      setRegeneratingAudioId(segmentId);
      setTtsError(null);
      const updatedAudio = await api.regenerateAudioSegment(projectId, segmentId);
      setGeneratedAudios((prev) => {
        const exists = prev.some((a) => a.translation_segment_id === segmentId || a.id === updatedAudio.id);
        if (exists) {
          return prev.map((a) => (a.translation_segment_id === segmentId ? updatedAudio : a));
        }
        return [...prev, updatedAudio];
      });
      await fetchProjectData();
      await fetchExportData();
    } catch (err: any) {
      setTtsError(err.message || 'Failed to regenerate audio segment');
    } finally {
      setRegeneratingAudioId(null);
    }
  };

  // Dubbing & Export Handlers
  const handleStartExport = async () => {
    try {
      setExporting(true);
      setExportError(null);
      await api.startExport(projectId);
      await fetchProjectData();
      await fetchExportData();
    } catch (err: any) {
      setExporting(false);
      setExportError(err.message || 'Failed to start video export');
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
  const latestTransJob = project.jobs?.find((j) => j.job_type === 'translate');
  const latestTtsJob = project.jobs?.find((j) => j.job_type === 'tts');
  const latestDubJob = project.jobs?.find((j) => j.job_type === 'dub');

  const defaultVoices: VoiceOption[] = [
    {
      provider: 'gtts',
      voice: 'default',
      label: 'Google Khmer (Default)',
      gender: 'neutral',
      description: 'Standard Google Translate Khmer online voice (Neutral tone)',
    },
    {
      provider: 'edge',
      voice: 'km-KH-PisethNeural',
      label: 'Microsoft Piseth (Male)',
      gender: 'male',
      description: 'Microsoft Edge Neural Voice (Male, friendly & natural)',
    },
    {
      provider: 'edge',
      voice: 'km-KH-SreymomNeural',
      label: 'Microsoft Sreymom (Female)',
      gender: 'female',
      description: 'Microsoft Edge Neural Voice (Female, expressive & natural)',
    },
  ];

  const activeVoiceList = availableVoices.length > 0 ? availableVoices : defaultVoices;
  const currentVoiceOption =
    activeVoiceList.find(
      (v) => v.provider === selectedVoice.provider && v.voice === selectedVoice.voice
    ) || activeVoiceList[0];

  const isAudioReady = project.status === 'audio_extracted' || !!project.video?.extracted_audio_path;
  const isExtractionFailed = latestExtractJob?.status === 'failed' && !project.video?.extracted_audio_path;
  const isExtracting =
    !isAudioReady &&
    !isExtractionFailed &&
    (project.status === 'uploaded' || latestExtractJob?.status === 'running' || latestExtractJob?.status === 'pending');

  const isTranscribed =
    project.status === 'transcribed' ||
    project.status === 'translating' ||
    project.status === 'translated' ||
    project.status === 'generating_voice' ||
    project.status === 'voice_generated' ||
    project.status === 'synchronizing' ||
    project.status === 'completed' ||
    transcriptSegments.length > 0 ||
    latestSttJob?.status === 'completed';

  const isTranslated =
    project.status === 'translated' ||
    project.status === 'generating_voice' ||
    project.status === 'voice_generated' ||
    project.status === 'synchronizing' ||
    project.status === 'completed' ||
    translationSegments.length > 0 ||
    latestTransJob?.status === 'completed';

  const isVoiceGenerated =
    project.status === 'voice_generated' ||
    project.status === 'synchronizing' ||
    project.status === 'completed' ||
    (generatedAudios.length > 0 && latestTtsJob?.status === 'completed') ||
    (generatedAudios.length > 0 && generatedAudios.length === translationSegments.length);

  const isVoiceReady =
    generatedAudios.length > 0 &&
    generatedAudios.length === translationSegments.length &&
    !generatedAudios.some((a) => a.is_outdated);

  const isExportReady =
    (!!project.video?.exported_video_path || !!exportStatus?.exported_video_path) &&
    (project.status === 'completed' || exportStatus?.is_export_ready === true);

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
          <div
            className={`p-2.5 rounded-lg border font-semibold ${
              isTranslated
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                : isTranscribed
                ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            3. Khmer Translation {isTranslated && '✓'}
          </div>
          <div
            className={`p-2.5 rounded-lg border font-semibold ${
              isVoiceGenerated
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                : isTranslated
                ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            4. Khmer Voice {isVoiceGenerated && '✓'}
          </div>
          <div
            className={`p-2.5 rounded-lg border font-semibold ${
              isExportReady
                ? 'bg-emerald-50 border-emerald-300 text-emerald-800'
                : isVoiceGenerated
                ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            5. Export Dub {isExportReady && '✓'}
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

          {/* Section 3: English-to-Khmer Translation */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
            {/* Header & Controls */}
            <div className="flex flex-col gap-4 pb-4 border-b border-slate-100">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Languages className="w-5 h-5 text-indigo-600" />
                    <h3 className="text-base font-bold text-slate-900 uppercase tracking-wide">
                      Khmer Translation
                    </h3>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="px-2 py-0.5 rounded bg-slate-100 font-medium text-slate-700 border border-slate-200">
                      {selectedTransProvider === 'gemini'
                        ? 'Provider: Google Gemini (AI LLM)'
                        : 'Provider: Meta NLLB-200 (Offline)'}
                    </span>
                    <span>•</span>
                    <span>
                      Status:{' '}
                      <strong className="capitalize text-slate-800">
                        {translating
                          ? 'Translating...'
                          : isTranslated
                          ? 'Completed'
                          : latestTransJob?.status || 'Pending'}
                      </strong>
                    </span>
                  </div>
                </div>

                {/* Action Button */}
                <div>
                  {!isTranslated ? (
                    <button
                      onClick={handleStartTranslation}
                      disabled={!isTranscribed || translating}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs sm:text-sm font-semibold transition-colors shadow-sm"
                    >
                      {translating ? (
                        <>
                          <RefreshCw className="w-4 h-4 animate-spin" />
                          <span>
                            {selectedTransProvider === 'gemini'
                              ? 'Translating with Gemini...'
                              : 'Translating with NLLB...'}
                          </span>
                        </>
                      ) : (
                        <>
                          <Languages className="w-4 h-4" />
                          <span>Translate to Khmer</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <button
                      onClick={handleStartTranslation}
                      disabled={translating}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-50 text-slate-700 text-xs font-semibold transition-colors"
                    >
                      <RotateCcw className={`w-3.5 h-3.5 ${translating ? 'animate-spin' : ''}`} />
                      <span>{translating ? 'Retranslating...' : 'Retranslate All'}</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Translation Provider & Style Configuration Toolbar */}
              <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex flex-wrap items-center gap-3">
                  {/* Provider Selector */}
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-slate-600 text-[11px] uppercase tracking-wide">
                      Provider:
                    </span>
                    <select
                      value={selectedTransProvider}
                      onChange={(e) =>
                        handleUpdateTranslationSettings(e.target.value, selectedTransStyle)
                      }
                      disabled={updatingTransSettings || translating}
                      className="bg-white border border-slate-300 rounded-lg px-2.5 py-1 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="nllb">Meta NLLB-200 (Local Free)</option>
                      <option value="gemini">Google Gemini (AI LLM)</option>
                    </select>
                  </div>

                  {/* Style Selector */}
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-slate-600 text-[11px] uppercase tracking-wide">
                      Style:
                    </span>
                    <select
                      value={selectedTransStyle}
                      onChange={(e) =>
                        handleUpdateTranslationSettings(selectedTransProvider, e.target.value)
                      }
                      disabled={updatingTransSettings || translating}
                      className="bg-white border border-slate-300 rounded-lg px-2.5 py-1 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="natural">Natural Spoken (Default)</option>
                      <option value="short">Short for Video Dubbing</option>
                      <option value="simple">Simple & Clear</option>
                      <option value="formal">Formal / Professional</option>
                      <option value="standard">Standard / Faithful</option>
                    </select>
                  </div>
                </div>

                {/* Gemini configuration status reminder */}
                {selectedTransProvider === 'gemini' && (
                  <div className="flex items-center gap-2 text-[11px]">
                    {translationProviders.find((p) => p.id === 'gemini')?.is_configured ? (
                      <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-medium">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        Gemini Configured
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200 font-medium">
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                        Gemini key not configured (Set in Settings)
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Error Banner */}
            {translationError && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Translation Error</span>
                    <span>{translationError}</span>
                  </div>
                </div>
                <button
                  onClick={handleStartTranslation}
                  className="px-3 py-1 rounded bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs shrink-0"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Translating Spinner View */}
            {translating ? (
              <div className="p-12 text-center bg-slate-50/60 rounded-xl border border-slate-200 space-y-3">
                <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
                <h4 className="text-sm font-bold text-slate-800">
                  Translating English Transcript into Khmer with NLLB-200...
                </h4>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  Running Seq2Seq neural machine translation with beam search. Preserves manually edited translations and aligns timing segments.
                </p>
              </div>
            ) : translationSegments.length > 0 ? (
              /* Comparative Segment List (English vs Khmer) */
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs text-slate-500 pb-2">
                  <span>
                    Total Translated Segments:{' '}
                    <strong className="text-slate-800 font-semibold">
                      {translationSegments.length}
                    </strong>
                  </span>
                  <span>Review English & Khmer side by side. Edit or retranslate individual segments.</span>
                </div>

                <div className="space-y-4">
                  {translationSegments.map((seg) => {
                    const isEditing = editingTransId === seg.id;
                    const isSaving = savingTransId === seg.id;
                    const isRetranslating = retranslatingTransId === seg.id;

                    return (
                      <div
                        key={seg.id}
                        className={`p-4 rounded-xl border transition-all ${
                          isEditing
                            ? 'bg-indigo-50/30 border-indigo-300 ring-2 ring-indigo-500/20'
                            : seg.is_outdated
                            ? 'bg-amber-50/30 border-amber-300'
                            : 'bg-slate-50/50 border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        {/* Segment Top Bar: Order, Timestamps, and Status Badges */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 mb-3 border-b border-slate-200/60">
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                              #{seg.segment_order}
                            </span>
                            {seg.start_time !== undefined && seg.start_time !== null && (
                              <span className="text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded border border-indigo-200 flex items-center gap-1">
                                <Clock className="w-3 h-3 text-indigo-500" />
                                {formatTimestamp(seg.start_time)} – {formatTimestamp(seg.end_time || 0)}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            {seg.is_outdated && (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-200">
                                <AlertTriangle className="w-3 h-3 text-amber-600" />
                                English Changed (Outdated)
                              </span>
                            )}
                            {seg.is_manually_edited && (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-700 bg-indigo-100/70 px-2 py-0.5 rounded-full border border-indigo-200">
                                <CheckCircle2 className="w-3 h-3 text-indigo-600" />
                                Manually Edited
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Dual Column Comparative Layout */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {/* Left: Original English */}
                          <div className="p-3 rounded-lg bg-white border border-slate-200 space-y-1">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                              Original English
                            </span>
                            <p className="text-sm text-slate-700 leading-relaxed font-normal">
                              {seg.english_text || '(No English transcript)'}
                            </p>
                          </div>

                          {/* Right: Khmer Translation */}
                          <div className="p-3 rounded-lg bg-white border border-indigo-100 space-y-2 relative">
                            <div className="flex flex-wrap items-center justify-between gap-1.5">
                              <div className="flex items-center gap-1.5">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600">
                                  Khmer Translation
                                </span>
                                {seg.style && (
                                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100 capitalize">
                                    {seg.style}
                                  </span>
                                )}
                              </div>
                              {!isEditing && (
                                <div className="flex flex-wrap items-center gap-1">
                                  <button
                                    onClick={() => handleOpenAiImprove(seg)}
                                    disabled={improvingSegmentId === seg.id}
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-indigo-700 hover:text-indigo-900 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 transition"
                                    title="Improve phrasing or fit timing with AI"
                                  >
                                    <Sparkles className="w-3 h-3 text-indigo-600" />
                                    <span>AI Improve</span>
                                  </button>
                                  <button
                                    onClick={() => handleOpenAlternatives(seg)}
                                    disabled={loadingAlternatives}
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-slate-700 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 border border-slate-200 transition"
                                    title="View 3 translation style alternatives"
                                  >
                                    <Layers className="w-3 h-3 text-slate-500" />
                                    <span>Alternatives</span>
                                  </button>
                                  <button
                                    onClick={() => handleRetranslateSegment(seg.id)}
                                    disabled={isRetranslating}
                                    className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition-colors"
                                    title="Retranslate this segment"
                                  >
                                    <RotateCcw className={`w-3.5 h-3.5 ${isRetranslating ? 'animate-spin text-indigo-600' : ''}`} />
                                  </button>
                                  <button
                                    onClick={() => handleStartEditTrans(seg)}
                                    className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition-colors"
                                    title="Edit Khmer text"
                                  >
                                    <Edit2 className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              )}
                            </div>

                            {isEditing ? (
                              <div className="space-y-2 pt-1">
                                <textarea
                                  value={editingTransText}
                                  onChange={(e) => setEditingTransText(e.target.value)}
                                  rows={3}
                                  className="w-full px-3 py-2 text-sm rounded-lg border border-indigo-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 font-sans leading-relaxed text-slate-900"
                                  autoFocus
                                />
                                <div className="flex items-center gap-2">
                                  <button
                                    onClick={() => handleSaveEditTrans(seg.id)}
                                    disabled={isSaving || !editingTransText.trim()}
                                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm"
                                  >
                                    <Save className="w-3.5 h-3.5" />
                                    {isSaving ? 'Saving...' : 'Save'}
                                  </button>
                                  <button
                                    onClick={handleCancelEditTrans}
                                    disabled={isSaving}
                                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-600 text-xs font-medium"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <>
                                <p className="text-sm text-slate-900 leading-relaxed font-normal">
                                  {seg.khmer_text}
                                </p>
                                {seg.explanation && (
                                  <div className="mt-1.5 p-2 rounded bg-indigo-50/50 border border-indigo-100 text-[11px] text-indigo-900 flex items-start gap-1.5">
                                    <Sparkles className="w-3 h-3 text-indigo-500 shrink-0 mt-0.5" />
                                    <span>{seg.explanation}</span>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Prompt to start translation */
              <div className="p-8 text-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                <Languages className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <h4 className="text-sm font-semibold text-slate-700">
                  {isTranscribed ? 'Ready for Khmer Translation' : 'Awaiting English Transcription'}
                </h4>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  {isTranscribed
                    ? 'Click the "Translate to Khmer" button above to translate the English transcript into Khmer using Meta NLLB-200.'
                    : 'Complete Step 2 (English Transcription) before translating text.'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Section 4: Khmer Text-to-Speech (Multiple Voices) */}
      {project.video && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {/* Header */}
          <div className="p-6 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-violet-100 text-violet-600 flex items-center justify-center shrink-0">
                <Volume2 className="w-5 h-5" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold text-slate-800">
                    4. Khmer Voice & Speech Synthesis
                  </h3>
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200">
                    Multiple Providers
                  </span>
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                    Khmer (km)
                  </span>
                  <span className="text-[11px] font-medium px-2.5 py-0.5 rounded-full bg-violet-100 text-violet-800 border border-violet-200">
                    Active: {currentVoiceOption.label}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Choose from Google or Microsoft Neural voices and synthesize speech for your Khmer translated segments.
                </p>
              </div>
            </div>

            {/* Action Button */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleStartTTS}
                disabled={generatingVoice || translating || !isTranslated || translationSegments.length === 0}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition-all shadow-violet-200"
              >
                {generatingVoice ? (
                  <>
                    <RotateCcw className="w-4 h-4 animate-spin" />
                    <span>Synthesizing Voice... ({latestTtsJob?.progress_percentage || 0}%)</span>
                  </>
                ) : (
                  <>
                    <Volume2 className="w-4 h-4" />
                    <span>
                      {generatedAudios.length > 0 ? 'Regenerate All Audio' : 'Generate Khmer Audio'}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="p-6 space-y-5">
            {/* Voice Selection Cards */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                  <Volume2 className="w-3.5 h-3.5 text-violet-600" />
                  Select Khmer Voice
                </h4>
                <span className="text-[11px] text-slate-400">
                  Select a voice to apply to speech generation
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {activeVoiceList.map((v) => {
                  const isSelected =
                    selectedVoice.provider === v.provider && selectedVoice.voice === v.voice;
                  const isPreviewing = previewingVoiceKey === `${v.provider}:${v.voice}`;

                  return (
                    <div
                      key={`${v.provider}-${v.voice}`}
                      onClick={() => handleSelectVoice(v.provider, v.voice)}
                      className={`relative p-3.5 rounded-xl border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-violet-50/70 border-violet-500 ring-2 ring-violet-500/20 shadow-sm'
                          : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div>
                          <span className="text-xs font-bold text-slate-800 block">
                            {v.label}
                          </span>
                          <span className="text-[11px] text-slate-500 block mt-0.5">
                            {v.provider === 'edge' ? 'Microsoft Edge Neural' : 'Google Translate gTTS'}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                              v.gender === 'male'
                                ? 'bg-blue-50 text-blue-700 border-blue-200'
                                : v.gender === 'female'
                                ? 'bg-pink-50 text-pink-700 border-pink-200'
                                : 'bg-slate-100 text-slate-700 border-slate-200'
                            }`}
                          >
                            {v.gender.toUpperCase()}
                          </span>
                          {isSelected && (
                            <span className="w-5 h-5 rounded-full bg-violet-600 text-white flex items-center justify-center">
                              <Check className="w-3 h-3" />
                            </span>
                          )}
                        </div>
                      </div>

                      <p className="text-xs text-slate-600 mb-3 min-h-[30px] leading-relaxed">
                        {v.description}
                      </p>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handlePreviewVoice(v.provider, v.voice);
                          }}
                          disabled={generatingVoice || updatingVoice}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-violet-700 hover:bg-violet-100 border border-violet-200 transition-colors"
                          title="Listen to voice sample"
                        >
                          {isPreviewing ? (
                            <>
                              <Square className="w-3 h-3 fill-current text-violet-700" />
                              <span>Stop Preview</span>
                            </>
                          ) : (
                            <>
                              <Play className="w-3 h-3 fill-current text-violet-700" />
                              <span>Preview Voice</span>
                            </>
                          )}
                        </button>

                        <span className="text-[11px] font-medium text-slate-400">
                          {updatingVoice && isSelected ? 'Saving...' : isSelected ? 'Active Voice' : 'Click to select'}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Online notice */}
            <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg border border-slate-200/80 flex items-center gap-2">
              <Headphones className="w-4 h-4 text-violet-500 shrink-0" />
              <span>
                <strong>Online Speech Services:</strong> Google gTTS and Microsoft Edge TTS stream synthesis online over HTTPS. Active internet connectivity is required.
              </span>
            </div>

            {/* Voice mismatch / outdated warning */}
            {generatedAudios.length > 0 &&
              generatedAudios.some(
                (a) => a.provider !== selectedVoice.provider || a.voice !== selectedVoice.voice
              ) && (
                <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                    <span>
                      Voice selection changed to <strong>{currentVoiceOption.label}</strong>. Previously synthesized audio was generated with another voice.
                    </span>
                  </div>
                  <button
                    onClick={handleStartTTS}
                    disabled={generatingVoice}
                    className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-semibold shrink-0"
                  >
                    Regenerate All with {currentVoiceOption.label}
                  </button>
                </div>
              )}

            {/* TTS Error Alert */}
            {ttsError && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold block mb-0.5">Speech Synthesis Error</span>
                  <span>{ttsError}</span>
                </div>
              </div>
            )}

            {/* Active Generation Progress Bar */}
            {generatingVoice && latestTtsJob && (
              <div className="p-4 rounded-xl bg-violet-50/70 border border-violet-200 space-y-2">
                <div className="flex items-center justify-between text-xs text-violet-900 font-semibold">
                  <span className="flex items-center gap-2">
                    <RotateCcw className="w-3.5 h-3.5 animate-spin text-violet-600" />
                    Synthesizing speech segments with {currentVoiceOption.label}...
                  </span>
                  <span>{latestTtsJob.progress_percentage}%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-violet-200 overflow-hidden">
                  <div
                    className="h-full bg-violet-600 transition-all duration-300 rounded-full"
                    style={{ width: `${latestTtsJob.progress_percentage}%` }}
                  />
                </div>
              </div>
            )}

            {/* Audio Segments View */}
            {generatedAudios.length > 0 ? (
              <div className="space-y-4">
                {/* Stats summary */}
                <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
                  <div className="flex items-center gap-4">
                    <span>
                      Generated Segments: <strong className="text-slate-800 font-bold">{generatedAudios.length}</strong> / {translationSegments.length}
                    </span>
                    <span>
                      Total Audio Duration: <strong className="text-slate-800 font-bold">{generatedAudios.reduce((acc, a) => acc + (a.duration_seconds || 0), 0).toFixed(1)}s</strong>
                    </span>
                  </div>
                  {generatedAudios.some((a) => a.is_outdated) && (
                    <span className="inline-flex items-center gap-1.5 text-amber-700 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200 font-medium">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                      Some Khmer texts were edited or voice changed. Marked segments should be regenerated.
                    </span>
                  )}
                </div>

                {/* Segment cards */}
                <div className="space-y-3">
                  {generatedAudios.map((audio, idx) => {
                    const isRegenerating = regeneratingAudioId === (audio.translation_segment_id || audio.id);
                    const voiceLabel =
                      audio.provider === 'edge'
                        ? audio.voice?.includes('Piseth')
                          ? 'Microsoft Piseth (Male)'
                          : 'Microsoft Sreymom (Female)'
                        : 'Google Khmer (Default)';

                    return (
                      <div
                        key={audio.id || idx}
                        className={`p-4 rounded-xl border transition-all ${
                          audio.is_outdated
                            ? 'bg-amber-50/40 border-amber-200'
                            : 'bg-white border-slate-200 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2 pb-2 border-b border-slate-100">
                          <div className="flex items-center gap-2">
                            <span className="w-6 h-6 rounded-md bg-violet-100 text-violet-700 text-xs font-bold flex items-center justify-center">
                              {audio.segment_order || idx + 1}
                            </span>
                            <span className="text-xs font-semibold text-slate-700">
                              Segment #{audio.segment_order || idx + 1}
                            </span>
                            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-violet-50 text-violet-700 border border-violet-200">
                              {voiceLabel}
                            </span>
                            {audio.duration_seconds !== null && audio.duration_seconds !== undefined && (
                              <span className="text-[11px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                                {audio.duration_seconds.toFixed(2)}s
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            {audio.is_outdated ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-200">
                                <AlertTriangle className="w-3 h-3 text-amber-600" />
                                Text Modified (Outdated)
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                                Ready
                              </span>
                            )}
                            <button
                              onClick={() => handleRegenerateSegmentAudio(audio.translation_segment_id || audio.id)}
                              disabled={isRegenerating || generatingVoice}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-medium disabled:opacity-50 transition-colors"
                              title="Regenerate this speech segment"
                            >
                              <RotateCcw className={`w-3 h-3 ${isRegenerating ? 'animate-spin text-violet-600' : ''}`} />
                              <span>{isRegenerating ? 'Regenerating...' : 'Regenerate'}</span>
                            </button>
                          </div>
                        </div>

                        {/* Khmer Text */}
                        <p className="text-sm text-slate-800 font-normal leading-relaxed mb-3">
                          {audio.khmer_text || '(Khmer text)'}
                        </p>

                        {/* HTML Audio Player */}
                        <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200/70">
                          <audio
                            controls
                            className="w-full h-8"
                            src={api.getAudioSegmentUrl(projectId, audio.translation_segment_id || audio.id)}
                            preload="metadata"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Prompt to generate Khmer Voice */
              <div className="p-8 text-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                <Headphones className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <h4 className="text-sm font-semibold text-slate-700">
                  {isTranslated ? 'Ready for Khmer Voice Synthesis' : 'Awaiting Khmer Translation'}
                </h4>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  {isTranslated
                    ? 'Click "Generate Khmer Audio" above to convert all translated Khmer segments into natural speech.'
                    : 'Complete Step 3 (Khmer Translation) before synthesizing voice.'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Section 5: Khmer Dubbed Video Export */}
      {project.video && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {/* Header */}
          <div className="p-6 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-50/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                <Film className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-800">
                    5. Khmer Dubbed Video Export
                  </h3>
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                    MP4 H.264
                  </span>
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                    Audio: AAC Stereo
                  </span>
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                    Timeline: 44.1 kHz
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Synchronizes Khmer speech segments with original timestamps and remuxes into a final downloadable MP4.
                </p>
              </div>
            </div>

            {/* Action Button */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleStartExport}
                disabled={!isVoiceReady || exporting || generatingVoice || translating}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition-all shadow-emerald-200"
              >
                {exporting ? (
                  <>
                    <RotateCcw className="w-4 h-4 animate-spin" />
                    <span>Exporting Dub... ({latestDubJob?.progress_percentage || 0}%)</span>
                  </>
                ) : (
                  <>
                    <Film className="w-4 h-4" />
                    <span>
                      {isExportReady ? 'Regenerate Dubbed Video' : 'Generate Dubbed Video'}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="p-6 space-y-4">
            {/* Prerequisites Checklist */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span className="text-slate-600">Source Video:</span>
                <span className="font-semibold text-emerald-700">Ready</span>
              </div>
              <div className="flex items-center gap-2">
                {isTranscribed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-slate-400 shrink-0" />
                )}
                <span className="text-slate-600">Transcript:</span>
                <span className={`font-semibold ${isTranscribed ? 'text-emerald-700' : 'text-slate-400'}`}>
                  {isTranscribed ? 'Ready' : 'Pending'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {isTranslated ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-slate-400 shrink-0" />
                )}
                <span className="text-slate-600">Translation:</span>
                <span className={`font-semibold ${isTranslated ? 'text-emerald-700' : 'text-slate-400'}`}>
                  {isTranslated ? 'Ready' : 'Pending'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {isVoiceReady ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                )}
                <span className="text-slate-600">Speech Audio:</span>
                <span
                  className={`font-semibold ${
                    isVoiceReady
                      ? 'text-emerald-700'
                      : generatedAudios.some((a) => a.is_outdated)
                      ? 'text-amber-700'
                      : 'text-slate-400'
                  }`}
                >
                  {isVoiceReady
                    ? 'Ready'
                    : generatedAudios.some((a) => a.is_outdated)
                    ? 'Outdated'
                    : 'Pending'}
                </span>
              </div>
            </div>

            {/* Error Alert */}
            {exportError && (
              <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold block mb-0.5">Export Error</span>
                  <span>{exportError}</span>
                </div>
              </div>
            )}

            {/* Outdated Video Warning */}
            {exportStatus?.is_export_outdated && isExportReady && (
              <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold block mb-0.5">Video Export Outdated</span>
                  <span>
                    The Khmer translation or speech audio was updated after this video was generated.
                    Click <strong>"Regenerate Dubbed Video"</strong> to update the final export.
                  </span>
                </div>
              </div>
            )}

            {/* Active Export Progress Bar */}
            {exporting && latestDubJob && (
              <div className="p-4 rounded-xl bg-emerald-50/70 border border-emerald-200 space-y-2">
                <div className="flex items-center justify-between text-xs text-emerald-900 font-semibold">
                  <span className="flex items-center gap-2">
                    <RotateCcw className="w-3.5 h-3.5 animate-spin text-emerald-600" />
                    Synchronizing audio and encoding MP4 video...
                  </span>
                  <span>{latestDubJob.progress_percentage}%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-emerald-200 overflow-hidden">
                  <div
                    className="h-full bg-emerald-600 transition-all duration-300 rounded-full"
                    style={{ width: `${latestDubJob.progress_percentage}%` }}
                  />
                </div>
              </div>
            )}

            {/* Timing Conflicts Panel */}
            {exportStatus?.timing_conflicts && exportStatus.timing_conflicts.length > 0 && (
              <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-amber-900">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                    <span>
                      Timing Conflict Alert: {exportStatus.timing_conflicts.length} segment(s) exceed available timing window
                    </span>
                  </div>
                  <span className="text-[11px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full border border-amber-200">
                    Export Guard Active
                  </span>
                </div>
                <p className="text-xs text-amber-800 leading-relaxed">
                  To prevent speech from being abruptly cut off or extending past the video duration, Khmer speech must fit within the available time slot (maximum safe speedup is {exportStatus.timing_conflicts[0].max_tempo_factor}x). Please shorten the highlighted translation(s) and regenerate their audio.
                </p>
                <div className="space-y-2 pt-1">
                  {exportStatus.timing_conflicts.map((c, i) => (
                    <div key={i} className="p-3 rounded-lg bg-white/80 border border-amber-200/80 text-xs text-slate-800 space-y-1.5 shadow-2xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold text-amber-900">
                          Segment #{c.segment_order} ({c.start_time}s – {c.end_time}s)
                        </span>
                        <div className="flex items-center gap-1.5 text-[11px]">
                          <span className="text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                            Orig: {c.original_duration}s
                          </span>
                          <span className="text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                            Khmer: {c.khmer_duration}s
                          </span>
                          <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded font-semibold border border-rose-200">
                            Overflow: +{c.overflow_seconds}s
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
                        <span>
                          Window: <strong className="text-slate-800">{c.available_window ?? c.original_duration}s raw</strong> ({c.effective_window ?? c.available_window}s effective with {Math.round((c.safety_margin_seconds ?? 0.05) * 1000)}ms safety margin)
                        </span>
                        <span>•</span>
                        <span>Speed needed: <strong className="text-amber-900">{c.required_tempo}x</strong></span>
                        <span>•</span>
                        <span>Max allowed: <strong className="text-slate-800">{c.max_tempo_factor}x</strong></span>
                      </div>

                      <div className="text-[11px] text-amber-900 bg-amber-100/60 p-2 rounded border border-amber-200/50">
                        <strong>Suggested action:</strong> {c.suggested_action}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Completed Video Player & Download Card */}
            {isExportReady ? (
              <div className="space-y-4">
                <div className="rounded-xl overflow-hidden bg-black shadow-md border border-slate-200">
                  <video
                    controls
                    className="w-full max-h-[500px] aspect-video mx-auto"
                    src={api.getExportVideoUrl(projectId)}
                    preload="metadata"
                  />
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs">
                  <div className="flex flex-wrap items-center gap-4 text-slate-700">
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Duration</span>
                      <span className="font-semibold text-sm">
                        {exportStatus?.exported_duration_seconds
                          ? formatTimestamp(exportStatus.exported_duration_seconds)
                          : project.video?.exported_duration_seconds
                          ? formatTimestamp(project.video.exported_duration_seconds)
                          : formatTimestamp(project.video?.duration_seconds || 0)}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">File Size</span>
                      <span className="font-semibold text-sm">
                        {exportStatus?.exported_file_size_bytes
                          ? formatFileSize(exportStatus.exported_file_size_bytes)
                          : project.video?.exported_file_size_bytes
                          ? formatFileSize(project.video.exported_file_size_bytes)
                          : 'MP4 Video'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Audio Track</span>
                      <span className="font-semibold text-sm text-emerald-700">Khmer (Synchronized)</span>
                    </div>
                  </div>

                  <a
                    href={api.getExportDownloadUrl(projectId)}
                    download
                    className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold shadow-sm transition-all shadow-emerald-200 text-xs shrink-0"
                  >
                    <Download className="w-4 h-4" />
                    <span>Download Dubbed Video (MP4)</span>
                  </a>
                </div>
              </div>
            ) : (
              /* Awaiting Dubbing View */
              <div className="p-8 text-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                <Film className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                <h4 className="text-sm font-semibold text-slate-700">
                  {isVoiceReady ? 'Ready for Dubbed Video Export' : 'Awaiting Prior Dubbing Steps'}
                </h4>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  {isVoiceReady
                    ? 'Click "Generate Dubbed Video" above to synchronize all speech segments and create the final MP4.'
                    : 'Complete Steps 1–4 (Video, Transcription, Translation, and Khmer Voice) before exporting.'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI LLM Modal: Improve & Alternatives (Phase 9) */}
      {aiModalSegment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-5">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
                  {aiModalMode === 'improve' ? <Sparkles className="w-5 h-5" /> : <Layers className="w-5 h-5" />}
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    {aiModalMode === 'improve' ? 'AI Translation Improvement' : 'Translation Alternatives'}
                  </h3>
                  <p className="text-xs text-slate-500">
                    Segment #{aiModalSegment.segment_order} • Timing:{' '}
                    {formatTimestamp(aiModalSegment.start_time || 0)} – {formatTimestamp(aiModalSegment.end_time || 0)}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setAiModalSegment(null);
                  setAiModalMode(null);
                }}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Context Box: English vs Current Khmer */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
                <span className="text-[10px] uppercase font-bold text-slate-400">Original English</span>
                <p className="text-slate-800 leading-relaxed">{aiModalSegment.english_text || '(No text)'}</p>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
                <span className="text-[10px] uppercase font-bold text-slate-400">Current Translation</span>
                <p className="text-slate-800 leading-relaxed font-sans">{aiModalSegment.khmer_text}</p>
              </div>
            </div>

            {/* AI Improve Content */}
            {aiModalMode === 'improve' && (
              <div className="space-y-4">
                {improvingSegmentId === aiModalSegment.id ? (
                  <div className="p-8 text-center bg-indigo-50/40 rounded-xl border border-indigo-100 space-y-3">
                    <RefreshCw className="w-7 h-7 text-indigo-600 animate-spin mx-auto" />
                    <h4 className="text-sm font-semibold text-slate-800">
                      Analyzing with Google Gemini...
                    </h4>
                    <p className="text-xs text-slate-500">
                      Evaluating natural phrasing, terminology glossary, and speech timing slot.
                    </p>
                  </div>
                ) : improvedResult ? (
                  <div className="space-y-4">
                    <div className="p-4 rounded-xl bg-indigo-50/50 border border-indigo-200 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-900 uppercase tracking-wide flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                          AI-Improved Translation ({improvedResult.style})
                        </span>
                        <span className="text-[11px] font-mono text-indigo-700 bg-white px-2 py-0.5 rounded border border-indigo-200">
                          {improvedResult.model}
                        </span>
                      </div>
                      <div className="p-3 bg-white rounded-lg border border-indigo-100">
                        <p className="text-base text-slate-900 font-medium leading-relaxed">
                          {improvedResult.improved_khmer_text}
                        </p>
                      </div>
                      {improvedResult.explanation && (
                        <div className="text-xs text-indigo-800 bg-white/80 p-2.5 rounded-lg border border-indigo-100/60 leading-relaxed">
                          <strong className="font-semibold">Reasoning: </strong>
                          {improvedResult.explanation}
                        </div>
                      )}
                    </div>

                    {/* Fine-tuning input */}
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-slate-700">
                        Optional Prompt / Instructions to Refine:
                      </label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="e.g. Make it even shorter to fit 2 seconds, or use simpler words..."
                          value={aiCustomPrompt}
                          onChange={(e) => setAiCustomPrompt(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleRerunAiImprove()}
                          className="flex-1 text-xs px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                        <button
                          onClick={handleRerunAiImprove}
                          disabled={improvingSegmentId === aiModalSegment.id}
                          className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition"
                        >
                          Re-improve
                        </button>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                      <button
                        onClick={() => {
                          setAiModalSegment(null);
                          setAiModalMode(null);
                        }}
                        className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() =>
                          handleApplySuggestion(
                            improvedResult.improved_khmer_text,
                            improvedResult.style,
                            improvedResult.explanation
                          )
                        }
                        disabled={applyingSuggestion}
                        className="inline-flex items-center gap-1.5 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm transition"
                      >
                        <Check className="w-4 h-4" />
                        {applyingSuggestion ? 'Applying...' : 'Apply This Translation'}
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            )}

            {/* Alternatives Content */}
            {aiModalMode === 'alternatives' && (
              <div className="space-y-4">
                {loadingAlternatives ? (
                  <div className="p-8 text-center bg-indigo-50/40 rounded-xl border border-indigo-100 space-y-3">
                    <RefreshCw className="w-7 h-7 text-indigo-600 animate-spin mx-auto" />
                    <h4 className="text-sm font-semibold text-slate-800">
                      Generating Translation Alternatives...
                    </h4>
                    <p className="text-xs text-slate-500">
                      Creating Natural Spoken, Simple Words, and Short (Dubbing Tempo) options with Gemini.
                    </p>
                  </div>
                ) : alternativesResult ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      {alternativesResult.alternatives.map((alt) => (
                        <div
                          key={alt.style}
                          className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 flex flex-col justify-between space-y-3 hover:border-indigo-300 transition"
                        >
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                                {alt.label}
                              </span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 font-medium capitalize">
                                {alt.style}
                              </span>
                            </div>
                            <div className="p-3 bg-white rounded-lg border border-slate-200 min-h-[70px]">
                              <p className="text-sm text-slate-900 font-medium leading-relaxed">
                                {alt.khmer_text}
                              </p>
                            </div>
                            {alt.explanation && (
                              <p className="text-[11px] text-slate-500 leading-snug">
                                {alt.explanation}
                              </p>
                            )}
                          </div>

                          <button
                            onClick={() =>
                              handleApplySuggestion(alt.khmer_text, alt.style, alt.explanation || undefined)
                            }
                            disabled={applyingSuggestion}
                            className="w-full inline-flex items-center justify-center gap-1.5 py-2 px-3 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm transition"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Apply {alt.label}
                          </button>
                        </div>
                      ))}
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                      <button
                        onClick={() => {
                          setAiModalSegment(null);
                          setAiModalMode(null);
                        }}
                        className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition"
                      >
                        Close
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
