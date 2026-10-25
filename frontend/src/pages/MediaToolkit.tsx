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
  AlertTriangle,
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
  Volume2,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { api } from '../services/api';
import {
  ProjectSummary,
  ToolkitCapabilities,
  ToolkitTask,
  ToolkitTranscriptSegment,
  TTSVoiceOption,
  ParsedTranscriptCue,
  TimingConflictItem,
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

  // Text-to-Speech Studio State (Phase 13E.3)
  const [ttsText, setTtsText] = useState<string>(
    'សួស្តីបងប្អូនទាំងអស់គ្នា។ សូមស្វាគមន៍មកកាន់ KhmerDub AI។ ថ្ងៃនេះយើងសាកល្បងបង្កើតសំឡេងនិយាយដោយស្វ័យប្រវត្តិ។'
  );
  const [ttsLanguage, setTtsLanguage] = useState<string>('km');
  const [ttsVoices, setTtsVoices] = useState<TTSVoiceOption[]>([]);
  const [ttsSelectedVoice, setTtsSelectedVoice] = useState<string>('km-KH-PisethNeural');
  const [ttsSelectedProvider, setTtsSelectedProvider] = useState<string>('edge');
  const [ttsPauseDuration, setTtsPauseDuration] = useState<number>(0.4);
  const [ttsTargetFormat, setTtsTargetFormat] = useState<string>('mp3');
  const [isTtsPreviewLoading, setIsTtsPreviewLoading] = useState<boolean>(false);
  const [ttsPreviewAudioUrl, setTtsPreviewAudioUrl] = useState<string | null>(null);
  const [isTtsGenerating, setIsTtsGenerating] = useState<boolean>(false);
  const [regeneratingSegmentId, setRegeneratingSegmentId] = useState<string | null>(null);
  const [editingTtsSegmentId, setEditingTtsSegmentId] = useState<string | null>(null);
  const [editingTtsSegmentText, setEditingTtsSegmentText] = useState<string>('');
  const [playingSegmentId, setPlayingSegmentId] = useState<string | null>(null);

  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const segmentAudioRef = useRef<HTMLAudioElement | null>(null);

  // Transcript-to-Audio Studio State (Phase 13E.4)
  const [ttaInputTab, setTtaInputTab] = useState<'upload' | 'paste' | 'import'>('paste');
  const [ttaMode, setTtaMode] = useState<'narration' | 'timed'>('narration');
  const [ttaPastedText, setTtaPastedText] = useState<string>(
    `1\n00:00:01,000 --> 00:00:04,500\nសួស្តីបងប្អូនទាំងអស់គ្នា។\n\n2\n00:00:05,000 --> 00:00:08,200\nសូមស្វាគមន៍មកកាន់ KhmerDub AI។`
  );
  const [ttaSelectedFile, setTtaSelectedFile] = useState<File | null>(null);
  const [ttaImportTaskId, setTtaImportTaskId] = useState<string>('');
  const [ttaParsedCues, setTtaParsedCues] = useState<ParsedTranscriptCue[]>([]);
  const [ttaParsedFormat, setTtaParsedFormat] = useState<string>('');
  const [ttaHasTimestamps, setTtaHasTimestamps] = useState<boolean>(false);
  const [ttaWarnings, setTtaWarnings] = useState<string[]>([]);
  const [ttaIsParsing, setTtaIsParsing] = useState<boolean>(false);
  const [ttaIsGenerating, setTtaIsGenerating] = useState<boolean>(false);
  const [ttaEditingCueIndex, setTtaEditingCueIndex] = useState<number | null>(null);
  const [ttaEditingCueText, setTtaEditingCueText] = useState<string>('');
  const [ttaEditingCueStart, setTtaEditingCueStart] = useState<number>(0);
  const [ttaEditingCueEnd, setTtaEditingCueEnd] = useState<number>(0);
  const [ttaEditingCueVoice, setTtaEditingCueVoice] = useState<string>('');
  const [ttaEditingCueProvider, setTtaEditingCueProvider] = useState<string>('');
  const [ttaSourceFilename, setTtaSourceFilename] = useState<string>('transcript.srt');
  const [ttaSourceTaskId, setTtaSourceTaskId] = useState<string | null>(null);
  const ttaFileInputRef = useRef<HTMLInputElement | null>(null);

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

  // Load TTS voices when language or tool changes (Phase 13E.3)
  const fetchTtsVoices = useCallback(async (lang: string) => {
    try {
      const voices = await api.getToolkitVoices(lang);
      setTtsVoices(voices);
      if (voices.length > 0) {
        const matchingCurrent = voices.find(
          (v) => v.voice === ttsSelectedVoice && v.provider === ttsSelectedProvider
        );
        if (!matchingCurrent) {
          const firstAvailable = voices.find((v) => v.is_available) || voices[0];
          setTtsSelectedVoice(firstAvailable.voice);
          setTtsSelectedProvider(firstAvailable.provider);
        }
      }
    } catch (err: any) {
      console.error('Failed to load TTS voices:', err);
    }
  }, [ttsSelectedVoice, ttsSelectedProvider]);

  useEffect(() => {
    if (selectedTool === 'text_to_speech' || selectedTool === 'transcript_to_audio') {
      fetchTtsVoices(ttsLanguage);
    }
  }, [selectedTool, ttsLanguage, fetchTtsVoices]);

  // Initial parse for Transcript to Audio pasted sample if empty
  useEffect(() => {
    if (selectedTool === 'transcript_to_audio' && ttaParsedCues.length === 0 && ttaPastedText.trim()) {
      api.parseTranscriptToAudio(ttaPastedText, 'pasted.srt')
        .then((res) => {
          setTtaParsedCues(res.segments);
          setTtaParsedFormat(res.format);
          setTtaHasTimestamps(res.has_timestamps);
          setTtaWarnings(res.warnings || []);
        })
        .catch(() => {});
    }
  }, [selectedTool, ttaParsedCues.length, ttaPastedText]);

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
      if (['video_to_audio', 'video_to_transcript', 'video_to_text', 'audio_to_transcript', 'audio_to_text', 'text_to_speech', 'transcript_to_audio'].includes(full.tool_type)) {
        setSelectedTool(full.tool_type);
        if (full.tool_type === 'text_to_speech' && full.full_text) {
          setTtsText(full.full_text);
        }
      }
    } catch (err: any) {
      console.error('Failed to load task details:', err);
      setActiveTask(task);
    }
  };

  // Text-to-Speech Studio Handlers (Phase 13E.3)
  const handleVoiceChange = (compositeVal: string) => {
    const [p, ...rest] = compositeVal.split(':');
    const v = rest.join(':');
    setTtsSelectedProvider(p);
    setTtsSelectedVoice(v);
  };

  const handlePreviewTts = async () => {
    setError(null);
    if (!ttsText.trim()) {
      setError('Please enter some text to preview speech.');
      return;
    }
    try {
      setIsTtsPreviewLoading(true);
      const blob = await api.previewToolkitTTS({
        text: ttsText.slice(0, 200),
        provider: ttsSelectedProvider,
        voice: ttsSelectedVoice,
        language: ttsLanguage,
      });
      const url = URL.createObjectURL(blob);
      setTtsPreviewAudioUrl(url);
      if (previewAudioRef.current) {
        previewAudioRef.current.src = url;
        previewAudioRef.current.play().catch((e) => console.warn('Preview play error:', e));
      }
    } catch (err: any) {
      console.error('TTS preview failed:', err);
      setError(err.message || 'TTS preview failed.');
    } finally {
      setIsTtsPreviewLoading(false);
    }
  };

  const handleGenerateTts = async () => {
    setError(null);
    if (!ttsText.trim()) {
      setError('Please enter text to generate speech narration.');
      return;
    }
    try {
      setIsTtsGenerating(true);
      setStatusMessage('Synthesizing speech segments and assembling narration audio...');
      const task = await api.generateToolkitTTS({
        text: ttsText,
        provider: ttsSelectedProvider,
        voice: ttsSelectedVoice,
        language: ttsLanguage,
        target_format: ttsTargetFormat,
        pause_duration_seconds: ttsPauseDuration,
      });
      setActiveTask(task);
      await fetchTasks();
      setStatusMessage('Speech narration generated and assembled successfully!');
    } catch (err: any) {
      console.error('TTS generation failed:', err);
      setError(err.message || 'Failed to generate speech narration.');
    } finally {
      setIsTtsGenerating(false);
      setTimeout(() => setStatusMessage(''), 3000);
    }
  };

  const handleStartEditTtsSegment = (segId: string, currentText: string) => {
    setEditingTtsSegmentId(segId);
    setEditingTtsSegmentText(currentText);
  };

  const handleCancelEditTtsSegment = () => {
    setEditingTtsSegmentId(null);
    setEditingTtsSegmentText('');
  };

  const handleRegenerateTtsSegment = async (segmentId: string, textToUse?: string) => {
    if (!activeTask) return;
    setError(null);
    try {
      setRegeneratingSegmentId(segmentId);
      const updated = await api.regenerateToolkitTTSSegment(activeTask.id, segmentId, {
        text: textToUse,
        pause_duration_seconds: ttsPauseDuration,
      });
      setActiveTask(updated);
      setEditingTtsSegmentId(null);
      await fetchTasks();
    } catch (err: any) {
      console.error('Segment regeneration failed:', err);
      setError(err.message || 'Failed to regenerate segment.');
    } finally {
      setRegeneratingSegmentId(null);
    }
  };

  const handlePlayTtsSegment = (taskId: string, segmentId: string) => {
    if (playingSegmentId === segmentId) {
      if (segmentAudioRef.current) {
        segmentAudioRef.current.pause();
      }
      setPlayingSegmentId(null);
    } else {
      const url = api.getToolkitTTSSegmentStreamUrl(taskId, segmentId);
      if (segmentAudioRef.current) {
        segmentAudioRef.current.src = url;
        segmentAudioRef.current.play().catch((e) => console.warn('Segment play error:', e));
      }
      setPlayingSegmentId(segmentId);
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

  // -------------------------------------------------------------------------
  // Transcript-to-Audio Studio Handlers (Phase 13E.4)
  // -------------------------------------------------------------------------

  const handleTtaParsePasted = async () => {
    if (!ttaPastedText.trim()) {
      setError('Please paste transcript text or subtitles first.');
      return;
    }
    setError(null);
    setTtaIsParsing(true);
    try {
      const res = await api.parseTranscriptToAudio(ttaPastedText, 'pasted.srt');
      setTtaParsedCues(res.segments);
      setTtaParsedFormat(res.format);
      setTtaHasTimestamps(res.has_timestamps);
      setTtaWarnings(res.warnings || []);
      setTtaSourceFilename('pasted_' + (res.format === 'text' ? 'text.txt' : `${res.format}.srt`));
      setTtaSourceTaskId(null);
      if (!res.has_timestamps) {
        setTtaMode('narration');
      }
      setStatusMessage(`Parsed ${res.segments.length} segment(s) successfully.`);
    } catch (err: any) {
      console.error('Failed to parse transcript:', err);
      setError(err.message || 'Failed to parse transcript.');
    } finally {
      setTtaIsParsing(false);
      setTimeout(() => setStatusMessage(''), 3000);
    }
  };

  const handleTtaFileUpload = (file: File) => {
    setError(null);
    const validExts = ['.srt', '.vtt', '.txt'];
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!validExts.includes(ext)) {
      setError('Unsupported file type. Please upload a .srt, .vtt, or .txt file.');
      return;
    }
    setTtaSelectedFile(file);
    setTtaIsParsing(true);

    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const content = e.target?.result as string;
        const res = await api.parseTranscriptToAudio(content, file.name);
        setTtaParsedCues(res.segments);
        setTtaParsedFormat(res.format);
        setTtaHasTimestamps(res.has_timestamps);
        setTtaWarnings(res.warnings || []);
        setTtaSourceFilename(file.name);
        setTtaSourceTaskId(null);
        if (!res.has_timestamps) {
          setTtaMode('narration');
        }
        setStatusMessage(`Loaded ${res.segments.length} segment(s) from ${file.name}.`);
      } catch (err: any) {
        console.error('Failed to parse uploaded transcript:', err);
        setError(err.message || 'Failed to parse uploaded transcript file.');
      } finally {
        setTtaIsParsing(false);
        setTimeout(() => setStatusMessage(''), 3000);
      }
    };
    reader.onerror = () => {
      setTtaIsParsing(false);
      setError('Failed to read file from disk.');
    };
    reader.readAsText(file);
  };

  const handleTtaImportTask = async () => {
    if (!ttaImportTaskId) {
      setError('Please select a completed transcription task to import.');
      return;
    }
    setError(null);
    setTtaIsParsing(true);
    try {
      const res = await api.importTranscriptFromTask(ttaImportTaskId);
      setTtaParsedCues(res.segments);
      setTtaParsedFormat('imported');
      setTtaHasTimestamps(res.has_timestamps);
      setTtaWarnings(res.warnings || []);
      setTtaSourceFilename(res.source_filename || `imported_${ttaImportTaskId.slice(0, 8)}.srt`);
      setTtaSourceTaskId(res.source_task_id || ttaImportTaskId);
      setStatusMessage(`Imported ${res.segments.length} segment(s) from previous task.`);
    } catch (err: any) {
      console.error('Failed to import transcript task:', err);
      setError(err.message || 'Failed to import transcript.');
    } finally {
      setTtaIsParsing(false);
      setTimeout(() => setStatusMessage(''), 3000);
    }
  };

  const handleTtaGenerate = async () => {
    if (ttaParsedCues.length === 0) {
      setError('No transcript segments to synthesize. Please parse or import a transcript first.');
      return;
    }
    if (ttaMode === 'timed') {
      const missing = ttaParsedCues.some(
        (c) => c.start_time === null || c.start_time === undefined || c.end_time === null || c.end_time === undefined
      );
      if (missing) {
        setError('Timed Mode requires all segments to have start and end times. Please add timestamps or switch to Narration Mode.');
        return;
      }
    }

    setError(null);
    setTtaIsGenerating(true);
    setStatusMessage('Synthesizing speech segments and assembling audio track...');

    try {
      const task = await api.generateTranscriptToAudio({
        segments: ttaParsedCues.map((c, i) => ({
          segment_order: i + 1,
          text: c.text,
          start_time: c.start_time,
          end_time: c.end_time,
          voice: c.voice,
          provider: c.provider,
        })),
        mode: ttaMode,
        provider: ttsSelectedProvider,
        voice: ttsSelectedVoice,
        language: ttsLanguage,
        target_format: ttsTargetFormat,
        pause_duration_seconds: ttsPauseDuration,
        source_task_id: ttaSourceTaskId || undefined,
        filename: ttaSourceFilename,
      });

      setActiveTask(task);
      setStatusMessage('Speech generation completed successfully!');
      await fetchTasks();
    } catch (err: any) {
      console.error('Transcript to audio generation failed:', err);
      setError(err.message || 'Failed to convert transcript to speech.');
    } finally {
      setTtaIsGenerating(false);
      setTimeout(() => setStatusMessage(''), 3000);
    }
  };

  const handleTtaStartEditCue = (index: number) => {
    const cue = ttaParsedCues[index];
    setTtaEditingCueIndex(index);
    setTtaEditingCueText(cue.text);
    setTtaEditingCueStart(cue.start_time ?? 0);
    setTtaEditingCueEnd(cue.end_time ?? 1);
    setTtaEditingCueVoice(cue.voice || '');
    setTtaEditingCueProvider(cue.provider || '');
  };

  const handleTtaSaveEditCue = () => {
    if (ttaEditingCueIndex === null) return;
    const updated = [...ttaParsedCues];
    updated[ttaEditingCueIndex] = {
      ...updated[ttaEditingCueIndex],
      text: ttaEditingCueText.trim(),
      start_time: ttaEditingCueStart,
      end_time: Math.max(ttaEditingCueStart + 0.1, ttaEditingCueEnd),
      voice: ttaEditingCueVoice || null,
      provider: ttaEditingCueProvider || null,
    };
    setTtaParsedCues(updated);
    setTtaEditingCueIndex(null);
  };

  const handleTtaDeleteCue = (index: number) => {
    const updated = ttaParsedCues.filter((_, i) => i !== index).map((c, i) => ({ ...c, segment_order: i + 1 }));
    setTtaParsedCues(updated);
    if (ttaEditingCueIndex === index) {
      setTtaEditingCueIndex(null);
    }
  };

  const handleTtaMoveCue = (index: number, direction: 'up' | 'down') => {
    if ((direction === 'up' && index === 0) || (direction === 'down' && index === ttaParsedCues.length - 1)) {
      return;
    }
    const targetIdx = direction === 'up' ? index - 1 : index + 1;
    const updated = [...ttaParsedCues];
    const temp = updated[index];
    updated[index] = updated[targetIdx];
    updated[targetIdx] = temp;
    setTtaParsedCues(updated.map((c, i) => ({ ...c, segment_order: i + 1 })));
  };

  const handleTtaRegenerateTaskSegment = async (
    segmentId: string,
    textToUse?: string,
    voiceToUse?: string,
    provToUse?: string,
    startToUse?: number,
    endToUse?: number
  ) => {
    if (!activeTask) return;
    setError(null);
    setRegeneratingSegmentId(segmentId);
    try {
      const updated = await api.regenerateTranscriptToAudioSegment(activeTask.id, segmentId, {
        text: textToUse,
        voice: voiceToUse,
        provider: provToUse,
        start_time: startToUse,
        end_time: endToUse,
      });
      setActiveTask(updated);
      setEditingTtsSegmentId(null);
      await fetchTasks();
    } catch (err: any) {
      console.error('Failed to regenerate transcript segment:', err);
      setError(err.message || 'Failed to regenerate segment.');
    } finally {
      setRegeneratingSegmentId(null);
    }
  };

  const handleTtaDeleteTaskSegment = async (segmentId: string) => {
    if (!activeTask) return;
    if (!window.confirm('Delete this segment? The narration timeline will be rebuilt automatically.')) return;
    setError(null);
    try {
      const updated = await api.deleteTranscriptToAudioSegment(activeTask.id, segmentId);
      setActiveTask(updated);
      await fetchTasks();
    } catch (err: any) {
      console.error('Failed to delete segment:', err);
      setError(err.message || 'Failed to delete segment.');
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
      desc: 'Generate natural Khmer & English speech using Google Khmer, Edge Piseth/Sreymom/Aria/Guy, or VoxCPM2 voice cloning.',
      icon: Mic2,
      status: 'available' as const,
      phase: 'Phase 13E.3',
    },
    {
      id: 'transcript_to_audio',
      title: 'Transcript to Audio',
      desc: 'Transform subtitle transcripts into continuous audio narration or synchronized tracks.',
      icon: Radio,
      status: 'available' as const,
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
      ) : selectedTool === 'text_to_speech' ? (
        /* Standalone Text-to-Speech Studio (Phase 13E.3) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          <audio
            ref={previewAudioRef}
            onEnded={() => setTtsPreviewAudioUrl(null)}
          />
          <audio
            ref={segmentAudioRef}
            onEnded={() => setPlayingSegmentId(null)}
            onError={() => setPlayingSegmentId(null)}
          />

          {/* Left Column: Input Configuration */}
          <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  <Mic2 className="w-5 h-5 text-indigo-600" />
                  Text to Speech Studio
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Convert multi-sentence text into segmented speech and assembled narration.
                </p>
              </div>
              <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                Phase 13E.3
              </span>
            </div>

            {/* Language Selection */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700">Language</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTtsLanguage('km')}
                  className={`py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                    ttsLanguage === 'km'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  🇰🇭 Khmer (Default)
                </button>
                <button
                  type="button"
                  onClick={() => setTtsLanguage('en')}
                  className={`py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                    ttsLanguage === 'en'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  🇺🇸 English
                </button>
              </div>
            </div>

            {/* Voice Selection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700">Voice Profile</label>
                <span className="text-[11px] text-slate-400">
                  {ttsVoices.length} voices available
                </span>
              </div>
              <select
                value={`${ttsSelectedProvider}:${ttsSelectedVoice}`}
                onChange={(e) => handleVoiceChange(e.target.value)}
                className="w-full p-2.5 rounded-xl border border-slate-200 bg-white text-slate-800 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
              >
                <optgroup label="Standard System Voices">
                  {ttsVoices
                    .filter((v) => !v.is_custom)
                    .map((v) => (
                      <option
                        key={`${v.provider}:${v.voice}`}
                        value={`${v.provider}:${v.voice}`}
                        disabled={!v.is_available}
                      >
                        {v.label} ({v.gender}, {v.language.toUpperCase()})
                      </option>
                    ))}
                </optgroup>
                {ttsVoices.some((v) => v.is_custom) && (
                  <optgroup label="Authorized Custom Cloned Voices (VoxCPM2 GPU)">
                    {ttsVoices
                      .filter((v) => v.is_custom)
                      .map((v) => (
                        <option
                          key={`${v.provider}:${v.voice}`}
                          value={`${v.provider}:${v.voice}`}
                          disabled={!v.is_available}
                        >
                          {v.label} ({v.gender}) {!v.is_available ? '(Worker Offline)' : '• Ready'}
                        </option>
                      ))}
                  </optgroup>
                )}
              </select>

              {/* Selected Voice Details Card */}
              {(() => {
                const currentVoiceObj = ttsVoices.find(
                  (v) => v.voice === ttsSelectedVoice && v.provider === ttsSelectedProvider
                );
                return (
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-800">
                            {currentVoiceObj?.label || ttsSelectedVoice}
                          </span>
                          {currentVoiceObj?.is_custom ? (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                              Custom Clone
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-200 text-slate-700">
                              {currentVoiceObj?.provider.toUpperCase()}
                            </span>
                          )}
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              currentVoiceObj?.is_available
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}
                          >
                            {currentVoiceObj?.is_available ? 'Online' : 'Offline'}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500">
                          {currentVoiceObj?.description || 'Natural speech synthesis voice'}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={handlePreviewTts}
                        disabled={isTtsPreviewLoading || !currentVoiceObj?.is_available}
                        className="px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold text-xs transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                        title="Preview this voice"
                      >
                        {isTtsPreviewLoading ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Volume2 className="w-3.5 h-3.5" />
                        )}
                        <span>Preview</span>
                      </button>
                    </div>

                    {ttsPreviewAudioUrl && (
                      <div className="pt-2 border-t border-slate-200">
                        <audio controls src={ttsPreviewAudioUrl} className="w-full h-8" autoPlay />
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>

            {/* Input Textarea with Presets */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700">Narration Script</label>
                <span className="text-[11px] text-slate-400">
                  {ttsText.trim().split(/\s+/).filter(Boolean).length} words • {ttsText.length} chars
                </span>
              </div>

              {/* Sample presets */}
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="text-slate-400">Samples:</span>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('km');
                    setTtsText(
                      'សួស្តីបងប្អូនទាំងអស់គ្នា។ សូមស្វាគមន៍មកកាន់ KhmerDub AI។ ថ្ងៃនេះយើងសាកល្បងបង្កើតសំឡេងនិយាយដោយស្វ័យប្រវត្តិ។'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  Khmer Intro
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('km');
                    setTtsText(
                      'កាលពីព្រេងនាយ មានកុមារាម្នាក់រស់នៅតាមជនបទដ៏ស្រស់ស្អាត។ គាត់តែងតែឧស្សាហ៍ព្យាយាមរៀនសូត្ររាល់ថ្ងៃ។ ដោយសារការតស៊ូ គាត់បានក្លាយជាមនុស្សជោគជ័យ។'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  Khmer Story
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('en');
                    setTtsText(
                      'Welcome to KhmerDub AI. Today we are testing standalone speech synthesis with multi-sentence segmentation and pause control. Everything sounds great.'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  English Sample
                </button>
              </div>

              <textarea
                value={ttsText}
                onChange={(e) => setTtsText(e.target.value)}
                placeholder="Enter or paste text to synthesize speech..."
                rows={6}
                className="w-full p-3 rounded-xl border border-slate-200 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-y leading-relaxed"
              />
              <p className="text-[11px] text-slate-400">
                Text is automatically divided into natural sentence segments (respecting Khmer «។», «៕», and punctuation) for clean pacing and individual regeneration.
              </p>
            </div>

            {/* Speech Tuning Controls */}
            <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-100">
              {/* Pause Duration */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700">Pause Interval</label>
                  <span className="text-xs font-mono font-bold text-indigo-600">
                    {ttsPauseDuration.toFixed(2)}s
                  </span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.5"
                  step="0.05"
                  value={ttsPauseDuration}
                  onChange={(e) => setTtsPauseDuration(parseFloat(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
                <span className="text-[10px] text-slate-400 block">Silence between sentences</span>
              </div>

              {/* Output Audio Format */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700">Audio Format</label>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    type="button"
                    onClick={() => setTtsTargetFormat('mp3')}
                    className={`py-1.5 rounded-lg border text-xs font-semibold transition-all cursor-pointer ${
                      ttsTargetFormat === 'mp3'
                        ? 'bg-indigo-600 border-indigo-600 text-white'
                        : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    MP3 (192k)
                  </button>
                  <button
                    type="button"
                    onClick={() => setTtsTargetFormat('wav')}
                    className={`py-1.5 rounded-lg border text-xs font-semibold transition-all cursor-pointer ${
                      ttsTargetFormat === 'wav'
                        ? 'bg-indigo-600 border-indigo-600 text-white'
                        : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    WAV (PCM)
                  </button>
                </div>
                <span className="text-[10px] text-slate-400 block">Both MP3 & WAV are generated</span>
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span className="leading-relaxed">{error}</span>
              </div>
            )}

            {/* Generate Button */}
            <button
              type="button"
              onClick={handleGenerateTts}
              disabled={isTtsGenerating || !ttsText.trim()}
              className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm transition-all shadow-md hover:shadow-indigo-500/25 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isTtsGenerating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Generating Narration...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Generate Speech Narration</span>
                </>
              )}
            </button>
          </div>

          {/* Right Column: Narration Player & Segment Breakdown */}
          <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            {activeTask && activeTask.tool_type === 'text_to_speech' ? (
              <div className="space-y-6">
                {/* Assembled Narration Header */}
                <div className="border-b border-slate-100 pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                      <FileAudio className="w-5 h-5 text-indigo-600" />
                      Synthesized Narration
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Completed {activeTask.tts_segments?.length || 0} sentence segments • Pause: {activeTask.source_media_metadata?.pause_duration_seconds || activeTask.output_media_metadata?.pause_duration_seconds || 0.4}s
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <a
                      href={api.getToolkitTTSExportUrl(activeTask.id, 'mp3')}
                      download={`narration_${activeTask.id.slice(0, 8)}.mp3`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-xs cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download MP3</span>
                    </a>
                    <a
                      href={api.getToolkitTTSExportUrl(activeTask.id, 'wav')}
                      download={`narration_${activeTask.id.slice(0, 8)}.wav`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>WAV (PCM)</span>
                    </a>
                  </div>
                </div>

                {/* Combined Narration Player Banner */}
                <div className="bg-gradient-to-r from-slate-900 to-indigo-950 rounded-2xl p-5 text-white shadow-md space-y-3">
                  <div className="flex items-center justify-between text-xs text-slate-300">
                    <span className="font-semibold flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-indigo-400" />
                      Narration Audio Track
                    </span>
                    <div className="flex items-center gap-2 font-mono text-[11px]">
                      <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        {formatDuration(activeTask.output_duration_seconds)}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                        {formatBytes(activeTask.output_file_size_bytes)}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 pt-1">
                    <button
                      type="button"
                      onClick={() => handleTogglePlay(activeTask.id)}
                      className="w-12 h-12 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center transition-all shadow-md shrink-0 cursor-pointer"
                    >
                      {playingTaskId === activeTask.id ? (
                        <Pause className="w-5 h-5" />
                      ) : (
                        <Play className="w-5 h-5 ml-0.5" />
                      )}
                    </button>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>{playingTaskId === activeTask.id ? 'Playing Narration' : 'Click to Play Full Audio'}</span>
                        <span className="font-mono">{formatDuration(activeTask.output_duration_seconds)}</span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`bg-indigo-500 h-full ${
                            playingTaskId === activeTask.id ? 'animate-pulse w-full' : 'w-0'
                          }`}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Segments Breakdown */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-slate-900 text-sm">
                      Individual Speech Segments ({activeTask.tts_segments?.length || 0})
                    </h4>
                    <span className="text-xs text-slate-400">
                      Edit text & regenerate individual sentences
                    </span>
                  </div>

                  <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                    {(activeTask.tts_segments || []).map((seg) => {
                      const isEditing = editingTtsSegmentId === seg.id;
                      const isRegenerating = regeneratingSegmentId === seg.id;
                      const isPlaying = playingSegmentId === seg.id;

                      return (
                        <div
                          key={seg.id}
                          className="p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all space-y-3 shadow-xs"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded font-mono font-bold bg-slate-100 text-slate-700 text-[11px]">
                                #{seg.segment_order}
                              </span>
                              <span className="font-mono text-slate-400">
                                {seg.duration_seconds ? `${seg.duration_seconds.toFixed(2)}s` : '--'}
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                  seg.status === 'completed'
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                                }`}
                              >
                                {seg.status}
                              </span>
                            </div>

                            <div className="flex items-center gap-1.5">
                              {/* Play individual segment */}
                              <button
                                type="button"
                                onClick={() => handlePlayTtsSegment(activeTask.id, seg.id)}
                                disabled={!seg.audio_file_path}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer disabled:opacity-40"
                                title="Play segment"
                              >
                                {isPlaying ? (
                                  <Pause className="w-3.5 h-3.5 text-indigo-600" />
                                ) : (
                                  <Play className="w-3.5 h-3.5" />
                                )}
                              </button>

                              {/* Edit segment text */}
                              {!isEditing && (
                                <button
                                  type="button"
                                  onClick={() => handleStartEditTtsSegment(seg.id, seg.text)}
                                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                  title="Edit sentence text"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                              )}

                              {/* Download segment audio */}
                              <a
                                href={api.getToolkitTTSSegmentDownloadUrl(activeTask.id, seg.id)}
                                download={`segment_${seg.segment_order}.wav`}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                title="Download segment audio"
                              >
                                <Download className="w-3.5 h-3.5" />
                              </a>
                            </div>
                          </div>

                          {/* Segment Text or Edit Area */}
                          {isEditing ? (
                            <div className="space-y-2">
                              <textarea
                                value={editingTtsSegmentText}
                                onChange={(e) => setEditingTtsSegmentText(e.target.value)}
                                className="w-full p-2.5 rounded-lg border border-indigo-300 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 resize-y"
                                rows={2}
                                autoFocus
                              />
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={handleCancelEditTtsSegment}
                                  className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold cursor-pointer"
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleRegenerateTtsSegment(seg.id, editingTtsSegmentText)}
                                  disabled={isRegenerating || !editingTtsSegmentText.trim()}
                                  className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
                                >
                                  {isRegenerating ? (
                                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <Save className="w-3.5 h-3.5" />
                                  )}
                                  <span>Save & Regenerate</span>
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p className="text-slate-800 text-sm leading-relaxed">{seg.text}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-12 text-center text-slate-400 space-y-4">
                <Mic2 className="w-14 h-14 text-slate-300 mx-auto" />
                <div className="space-y-1">
                  <h4 className="font-semibold text-slate-700 text-base">Text-to-Speech Studio Ready</h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Enter or paste your text on the left, pick from standard Google/Microsoft voices or authorized custom cloned voices, and click "Generate Speech Narration".
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 max-w-sm mx-auto text-left text-[11px] text-slate-500 pt-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Khmer Unicode Safe</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Configurable Pauses</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Per-Segment Editing</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>MP3 & Lossless WAV</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : selectedTool === 'transcript_to_audio' ? (
        /* Transcript-to-Audio Studio (Phase 13E.4) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          <audio
            ref={previewAudioRef}
            onEnded={() => setTtsPreviewAudioUrl(null)}
          />
          <audio
            ref={segmentAudioRef}
            onEnded={() => setPlayingSegmentId(null)}
            onError={() => setPlayingSegmentId(null)}
          />

          {/* Left Column: Input Configuration */}
          <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  <Radio className="w-5 h-5 text-indigo-600" />
                  Transcript to Audio Studio
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Convert timestamped transcripts or plain text into natural continuous speech or timed tracks.
                </p>
              </div>
              <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                Phase 13E.4
              </span>
            </div>

            {/* Input Method Tabs */}
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700">Transcript Input Source</label>
              <div className="grid grid-cols-3 gap-1.5 p-1 bg-slate-100 rounded-xl">
                <button
                  type="button"
                  onClick={() => setTtaInputTab('paste')}
                  className={`py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                    ttaInputTab === 'paste'
                      ? 'bg-white text-indigo-700 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Paste Text
                </button>
                <button
                  type="button"
                  onClick={() => setTtaInputTab('upload')}
                  className={`py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                    ttaInputTab === 'upload'
                      ? 'bg-white text-indigo-700 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Upload File
                </button>
                <button
                  type="button"
                  onClick={() => setTtaInputTab('import')}
                  className={`py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                    ttaInputTab === 'import'
                      ? 'bg-white text-indigo-700 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Import Task
                </button>
              </div>

              {/* Tab 1: Paste Transcript */}
              {ttaInputTab === 'paste' && (
                <div className="space-y-2">
                  <div className="relative">
                    <textarea
                      value={ttaPastedText}
                      onChange={(e) => setTtaPastedText(e.target.value)}
                      placeholder="Paste SRT, WebVTT, or plain text here..."
                      rows={6}
                      className="w-full p-3 rounded-xl border border-slate-200 text-slate-800 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-y leading-relaxed"
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <span>Supports SRT, WebVTT, and plain text</span>
                    <button
                      type="button"
                      onClick={handleTtaParsePasted}
                      disabled={ttaIsParsing || !ttaPastedText.trim()}
                      className="px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50 transition-colors"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${ttaIsParsing ? 'animate-spin' : ''}`} />
                      <span>Parse Transcript</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Tab 2: Upload File */}
              {ttaInputTab === 'upload' && (
                <div className="space-y-2">
                  <input
                    ref={ttaFileInputRef}
                    type="file"
                    accept=".srt,.vtt,.txt"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        handleTtaFileUpload(e.target.files[0]);
                      }
                    }}
                    className="hidden"
                  />
                  <div
                    onClick={() => ttaFileInputRef.current?.click()}
                    className="border-2 border-dashed border-slate-200 hover:border-indigo-400 rounded-xl p-6 text-center cursor-pointer transition-colors bg-slate-50/50 hover:bg-indigo-50/20 space-y-2"
                  >
                    <Upload className="w-8 h-8 text-slate-400 mx-auto" />
                    <div className="text-xs">
                      <span className="font-semibold text-indigo-600">Click to upload</span>
                      <span className="text-slate-500"> or drag and drop</span>
                    </div>
                    <p className="text-[11px] text-slate-400">SRT, VTT, or TXT (UTF-8 encoded)</p>
                    {ttaSelectedFile && (
                      <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-700">
                        <FileCode className="w-3.5 h-3.5 text-indigo-600" />
                        <span>{ttaSelectedFile.name}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Tab 3: Import Existing Task */}
              {ttaInputTab === 'import' && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-500">
                    Directly reuse speech segments from completed Whisper transcription tasks without re-running ASR.
                  </p>
                  <select
                    value={ttaImportTaskId}
                    onChange={(e) => setTtaImportTaskId(e.target.value)}
                    className="w-full p-2.5 rounded-xl border border-slate-200 text-slate-800 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                  >
                    <option value="">-- Select Completed Task --</option>
                    {tasks
                      .filter((t) => t.status === 'completed' && (t.tool_type.includes('transcript') || (t.segments && t.segments.length > 0)))
                      .map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.source_filename} ({getToolTitle(t.tool_type)} - {formatDuration(t.output_duration_seconds)})
                        </option>
                      ))}
                  </select>
                  <button
                    type="button"
                    onClick={handleTtaImportTask}
                    disabled={!ttaImportTaskId || ttaIsParsing}
                    className="w-full py-2 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold text-xs flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Import Task Transcript</span>
                  </button>
                </div>
              )}
            </div>

            {/* Generation Mode Selector */}
            <div className="space-y-2 border-t border-slate-100 pt-4">
              <label className="text-xs font-semibold text-slate-700">Speech Generation Mode</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTtaMode('narration')}
                  className={`p-3 rounded-xl border text-left transition-all cursor-pointer ${
                    ttaMode === 'narration'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-900 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <div className="font-semibold text-xs flex items-center justify-between">
                    <span>Narration Mode</span>
                    {ttaMode === 'narration' && <Check className="w-3.5 h-3.5 text-indigo-600" />}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Natural continuous speech. Gaps and sentence pacing use natural pauses.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    if (ttaHasTimestamps) {
                      setTtaMode('timed');
                    }
                  }}
                  disabled={!ttaHasTimestamps}
                  className={`p-3 rounded-xl border text-left transition-all ${
                    !ttaHasTimestamps
                      ? 'bg-slate-50 border-slate-200/80 text-slate-400 opacity-60 cursor-not-allowed'
                      : ttaMode === 'timed'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-900 ring-1 ring-indigo-500 cursor-pointer'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50 cursor-pointer'
                  }`}
                >
                  <div className="font-semibold text-xs flex items-center justify-between">
                    <span>Timed Mode</span>
                    {ttaMode === 'timed' && <Check className="w-3.5 h-3.5 text-indigo-600" />}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Aligned to timestamps with up to 1.25x tempo and conflict reporting.
                  </p>
                </button>
              </div>

              {!ttaHasTimestamps && (
                <p className="text-[11px] text-amber-600 bg-amber-50 p-2 rounded-lg border border-amber-200 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>Timed Mode requires timestamped input (SRT or VTT). Narration Mode is active.</span>
                </p>
              )}
            </div>

            {/* Pause duration (Narration mode only) */}
            {ttaMode === 'narration' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700">Pause Between Segments</label>
                  <span className="text-xs font-mono font-bold text-indigo-600">{ttsPauseDuration.toFixed(2)}s</span>
                </div>
                <input
                  type="range"
                  min="0.0"
                  max="1.5"
                  step="0.05"
                  value={ttsPauseDuration}
                  onChange={(e) => setTtsPauseDuration(parseFloat(e.target.value))}
                  className="w-full accent-indigo-600 cursor-pointer"
                />
              </div>
            )}

            {/* Language Selection */}
            <div className="space-y-2 border-t border-slate-100 pt-4">
              <label className="text-xs font-semibold text-slate-700">Language</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTtsLanguage('km')}
                  className={`py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                    ttsLanguage === 'km'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  🇰🇭 Khmer (Default)
                </button>
                <button
                  type="button"
                  onClick={() => setTtsLanguage('en')}
                  className={`py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                    ttsLanguage === 'en'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  🇺🇸 English
                </button>
              </div>
            </div>

            {/* Global Voice Selection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700">Global Voice</label>
                <span className="text-[11px] text-slate-400">Can override per segment</span>
              </div>
              <select
                value={`${ttsSelectedProvider}::${ttsSelectedVoice}`}
                onChange={(e) => {
                  const [prov, vName] = e.target.value.split('::');
                  setTtsSelectedProvider(prov);
                  setTtsSelectedVoice(vName);
                }}
                className="w-full p-2.5 rounded-xl border border-slate-200 text-slate-800 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              >
                {ttsVoices.map((v) => (
                  <option
                    key={`${v.provider}-${v.voice}`}
                    value={`${v.provider}::${v.voice}`}
                    disabled={!v.is_available}
                  >
                    {v.label} ({v.provider.toUpperCase()}) {!v.is_available ? '— Offline' : ''}
                  </option>
                ))}
              </select>

              {/* Preview Button */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-[11px] text-slate-400">Test voice pronunciation</span>
                <button
                  type="button"
                  onClick={handlePreviewTts}
                  disabled={isTtsPreviewLoading}
                  className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {isTtsPreviewLoading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                  ) : ttsPreviewAudioUrl ? (
                    <Volume2 className="w-3.5 h-3.5 text-emerald-600" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                  <span>{ttsPreviewAudioUrl ? 'Playing...' : 'Preview Voice'}</span>
                </button>
              </div>
            </div>

            {/* Target Output Format */}
            <div className="space-y-2 border-t border-slate-100 pt-4">
              <label className="text-xs font-semibold text-slate-700">Audio Format</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTtsTargetFormat('mp3')}
                  className={`py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                    ttsTargetFormat === 'mp3'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  MP3 (Standard)
                </button>
                <button
                  type="button"
                  onClick={() => setTtsTargetFormat('wav')}
                  className={`py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                    ttsTargetFormat === 'wav'
                      ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  WAV (Lossless 44.1kHz)
                </button>
              </div>
            </div>

            {/* Generate Action Button */}
            <button
              type="button"
              onClick={handleTtaGenerate}
              disabled={ttaIsGenerating || ttaParsedCues.length === 0}
              className="w-full py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {ttaIsGenerating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Synthesizing Transcript Speech...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>
                    Generate Speech Track ({ttaParsedCues.length}{' '}
                    {ttaParsedCues.length === 1 ? 'Segment' : 'Segments'})
                  </span>
                </>
              )}
            </button>
          </div>

          {/* Right Column: Interactive Editor / Active Workspace */}
          <div className="lg:col-span-7 space-y-6">
            {activeTask && activeTask.tool_type === 'transcript_to_audio' && activeTask.status === 'completed' ? (
              /* Active Generated Studio Workspace */
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {activeTask.output_media_metadata?.mode === 'timed' ? 'Timed Mode' : 'Narration Mode'}
                      </span>
                      <span className="text-xs font-mono text-slate-400">
                        {formatDuration(activeTask.output_duration_seconds)}
                      </span>
                    </div>
                    <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                      <span>{activeTask.source_filename}</span>
                    </h3>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveTask(null);
                      setTtaParsedCues([]);
                    }}
                    className="px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-600 flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>New Transcript</span>
                  </button>
                </div>

                {/* Primary Audio Player & Downloads */}
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                      <Volume2 className="w-4 h-4 text-indigo-600" />
                      Assembled Narration Audio
                    </span>
                    <span className="text-xs font-mono text-slate-500">
                      {formatDuration(activeTask.output_duration_seconds)} • {formatBytes(activeTask.output_file_size_bytes)}
                    </span>
                  </div>

                  <audio
                    controls
                    className="w-full h-10"
                    src={api.getToolkitAudioStreamUrl(activeTask.id)}
                  />

                  <div className="flex items-center justify-end gap-2 pt-1">
                    <a
                      href={api.getToolkitTTSExportUrl(activeTask.id, 'mp3')}
                      download={`narration_${activeTask.id.slice(0, 8)}.mp3`}
                      className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download MP3</span>
                    </a>
                    <a
                      href={api.getToolkitTTSExportUrl(activeTask.id, 'wav')}
                      download={`narration_${activeTask.id.slice(0, 8)}.wav`}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download WAV</span>
                    </a>
                  </div>
                </div>

                {/* Timing Conflicts Alert Banner (if in Timed Mode) */}
                {activeTask.output_media_metadata?.conflicts && activeTask.output_media_metadata.conflicts.length > 0 && (
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 space-y-3">
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                      <div className="space-y-1">
                        <h4 className="font-bold text-amber-900 text-sm">
                          {activeTask.output_media_metadata.conflicts.length} Speech Timing Conflict(s) Detected
                        </h4>
                        <p className="text-xs text-amber-800 leading-relaxed">
                          The following speech segments take longer to pronounce in Khmer than the original transcript window.
                          Per project architecture, silent truncation is prevented. You may shorten the text or switch to Narration Mode.
                        </p>
                      </div>
                    </div>

                    <div className="space-y-2 pt-1">
                      {activeTask.output_media_metadata.conflicts.map((c: TimingConflictItem) => (
                        <div
                          key={c.segment_order}
                          className="p-3 rounded-lg bg-white/80 border border-amber-200/80 text-xs space-y-1.5"
                        >
                          <div className="flex items-center justify-between font-semibold text-slate-800">
                            <span className="font-mono text-indigo-700">Segment #{c.segment_order}</span>
                            <span className="font-mono text-amber-700">
                              {c.start_time.toFixed(2)}s → {c.end_time.toFixed(2)}s (+{c.overflow_seconds.toFixed(2)}s overflow)
                            </span>
                          </div>
                          <p className="text-slate-600 text-[11px]">{c.suggested_action}</p>
                        </div>
                      ))}
                    </div>

                    <div className="flex justify-end pt-1">
                      <button
                        type="button"
                        onClick={() => {
                          setTtaMode('narration');
                          handleTtaGenerate();
                        }}
                        className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold cursor-pointer transition-colors shadow-xs"
                      >
                        Switch to Narration Mode & Re-generate
                      </button>
                    </div>
                  </div>
                )}

                {/* Segments Breakdown */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="font-bold text-slate-900 text-sm">
                      Individual Speech Segments ({activeTask.tts_segments?.length || 0})
                    </h4>
                    <span className="text-xs text-slate-400">
                      Play, edit text/timings, override voices, or regenerate single sentences
                    </span>
                  </div>

                  <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                    {(activeTask.tts_segments || []).map((seg) => {
                      const isEditing = editingTtsSegmentId === seg.id;
                      const isRegenerating = regeneratingSegmentId === seg.id;
                      const isPlaying = playingSegmentId === seg.id;

                      return (
                        <div
                          key={seg.id}
                          className="p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all space-y-3 shadow-xs"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded font-mono font-bold bg-slate-100 text-slate-700 text-[11px]">
                                #{seg.segment_order}
                              </span>
                              {seg.start_time !== null && seg.start_time !== undefined && seg.end_time !== null && seg.end_time !== undefined && (
                                <span className="font-mono text-indigo-700 font-semibold text-[11px]">
                                  {formatTimestamp(seg.start_time)} → {formatTimestamp(seg.end_time)}
                                </span>
                              )}
                              <span className="font-mono text-slate-400">
                                {seg.duration_seconds ? `${seg.duration_seconds.toFixed(2)}s` : '--'}
                              </span>
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                  seg.status === 'completed'
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                                }`}
                              >
                                {seg.status}
                              </span>
                            </div>

                            <div className="flex items-center gap-1.5">
                              {/* Play individual segment */}
                              <button
                                type="button"
                                onClick={() => handlePlayTtsSegment(activeTask.id, seg.id)}
                                disabled={!seg.audio_file_path}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer disabled:opacity-40"
                                title="Play segment"
                              >
                                {isPlaying ? (
                                  <Pause className="w-3.5 h-3.5 text-indigo-600" />
                                ) : (
                                  <Play className="w-3.5 h-3.5" />
                                )}
                              </button>

                              {/* Edit segment text and timing */}
                              {!isEditing && (
                                <button
                                  type="button"
                                  onClick={() => handleStartEditTtsSegment(seg.id, seg.text)}
                                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                  title="Edit segment"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                              )}

                              {/* Download segment audio */}
                              <a
                                href={api.getToolkitTTSSegmentDownloadUrl(activeTask.id, seg.id)}
                                download={`segment_${seg.segment_order}.wav`}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                title="Download segment audio"
                              >
                                <Download className="w-3.5 h-3.5" />
                              </a>

                              {/* Delete segment */}
                              <button
                                type="button"
                                onClick={() => handleTtaDeleteTaskSegment(seg.id)}
                                className="p-1.5 rounded-lg hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                                title="Delete segment"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>

                          {/* Segment Text or Edit Area */}
                          {isEditing ? (
                            <div className="space-y-3">
                              <textarea
                                value={editingTtsSegmentText}
                                onChange={(e) => setEditingTtsSegmentText(e.target.value)}
                                className="w-full p-2.5 rounded-lg border border-indigo-300 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 resize-y"
                                rows={2}
                                autoFocus
                              />
                              <div className="flex items-center justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={handleCancelEditTtsSegment}
                                  className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold cursor-pointer"
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleTtaRegenerateTaskSegment(seg.id, editingTtsSegmentText)}
                                  disabled={isRegenerating || !editingTtsSegmentText.trim()}
                                  className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
                                >
                                  {isRegenerating ? (
                                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    <Save className="w-3.5 h-3.5" />
                                  )}
                                  <span>Save & Regenerate</span>
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p className="text-slate-800 text-sm leading-relaxed">{seg.text}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : ttaParsedCues.length > 0 ? (
              /* Pre-Generation Parsed Transcript Editor */
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
                <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {ttaParsedFormat || 'SRT'} Format
                      </span>
                      <span className="text-xs text-slate-400">
                        {ttaParsedCues.length} {ttaParsedCues.length === 1 ? 'segment' : 'segments'}
                      </span>
                      {ttaHasTimestamps ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Timestamps Validated
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                          Narration Only
                        </span>
                      )}
                    </div>
                    <h3 className="font-bold text-slate-900 text-base">
                      {ttaSourceFilename}
                    </h3>
                  </div>

                  <button
                    type="button"
                    onClick={() => setTtaParsedCues([])}
                    className="px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-600 transition-colors cursor-pointer"
                  >
                    Clear All
                  </button>
                </div>

                {/* Warnings Banner */}
                {ttaWarnings.length > 0 && (
                  <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
                    <div className="flex items-center gap-1.5 font-bold">
                      <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                      <span>Parsing Notices ({ttaWarnings.length})</span>
                    </div>
                    <ul className="list-disc list-inside space-y-0.5 pl-1 text-[11px]">
                      {ttaWarnings.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Interactive Parsed Cues List */}
                <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                  {ttaParsedCues.map((cue, idx) => {
                    const isEditing = ttaEditingCueIndex === idx;

                    return (
                      <div
                        key={idx}
                        className="p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all space-y-3 shadow-xs"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded font-mono font-bold bg-slate-100 text-slate-700 text-[11px]">
                              #{idx + 1}
                            </span>
                            {cue.start_time !== null && cue.start_time !== undefined && cue.end_time !== null && cue.end_time !== undefined && (
                              <span className="font-mono text-indigo-700 font-semibold text-[11px]">
                                {formatTimestamp(cue.start_time)} → {formatTimestamp(cue.end_time)}
                              </span>
                            )}
                            {cue.voice && (
                              <span className="px-2 py-0.5 rounded text-[10px] bg-indigo-50 text-indigo-700 font-semibold">
                                {cue.voice}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-1">
                            {/* Reordering buttons (Narration mode) */}
                            {ttaMode === 'narration' && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => handleTtaMoveCue(idx, 'up')}
                                  disabled={idx === 0}
                                  className="p-1 rounded hover:bg-slate-100 text-slate-500 disabled:opacity-30 cursor-pointer"
                                  title="Move segment up"
                                >
                                  <ArrowUp className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleTtaMoveCue(idx, 'down')}
                                  disabled={idx === ttaParsedCues.length - 1}
                                  className="p-1 rounded hover:bg-slate-100 text-slate-500 disabled:opacity-30 cursor-pointer"
                                  title="Move segment down"
                                >
                                  <ArrowDown className="w-3.5 h-3.5" />
                                </button>
                              </>
                            )}

                            {!isEditing && (
                              <button
                                type="button"
                                onClick={() => handleTtaStartEditCue(idx)}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                title="Edit segment"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => handleTtaDeleteCue(idx)}
                              className="p-1.5 rounded-lg hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                              title="Delete segment"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        {/* Text / Inline Editing */}
                        {isEditing ? (
                          <div className="space-y-3 pt-1">
                            <textarea
                              value={ttaEditingCueText}
                              onChange={(e) => setTtaEditingCueText(e.target.value)}
                              rows={2}
                              className="w-full p-2.5 rounded-lg border border-indigo-300 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                            />

                            {/* Timing inputs if Timed Mode */}
                            {ttaMode === 'timed' && (
                              <div className="grid grid-cols-2 gap-3 text-xs">
                                <div>
                                  <label className="text-[11px] font-semibold text-slate-600">Start Time (s)</label>
                                  <input
                                    type="number"
                                    step="0.1"
                                    min="0"
                                    value={ttaEditingCueStart}
                                    onChange={(e) => setTtaEditingCueStart(parseFloat(e.target.value) || 0)}
                                    className="w-full mt-1 p-1.5 rounded border border-slate-200 text-slate-800"
                                  />
                                </div>
                                <div>
                                  <label className="text-[11px] font-semibold text-slate-600">End Time (s)</label>
                                  <input
                                    type="number"
                                    step="0.1"
                                    min="0"
                                    value={ttaEditingCueEnd}
                                    onChange={(e) => setTtaEditingCueEnd(parseFloat(e.target.value) || 0)}
                                    className="w-full mt-1 p-1.5 rounded border border-slate-200 text-slate-800"
                                  />
                                </div>
                              </div>
                            )}

                            {/* Voice override dropdown */}
                            <div>
                              <label className="text-[11px] font-semibold text-slate-600">Voice Override (Optional)</label>
                              <select
                                value={`${ttaEditingCueProvider}::${ttaEditingCueVoice}`}
                                onChange={(e) => {
                                  if (!e.target.value) {
                                    setTtaEditingCueProvider('');
                                    setTtaEditingCueVoice('');
                                  } else {
                                    const [p, v] = e.target.value.split('::');
                                    setTtaEditingCueProvider(p);
                                    setTtaEditingCueVoice(v);
                                  }
                                }}
                                className="w-full mt-1 p-1.5 rounded border border-slate-200 text-slate-800 text-xs"
                              >
                                <option value="">-- Use Global Voice --</option>
                                {ttsVoices.map((v) => (
                                  <option key={`${v.provider}-${v.voice}`} value={`${v.provider}::${v.voice}`}>
                                    {v.label} ({v.provider.toUpperCase()})
                                  </option>
                                ))}
                              </select>
                            </div>

                            <div className="flex items-center justify-end gap-2 pt-1">
                              <button
                                type="button"
                                onClick={() => setTtaEditingCueIndex(null)}
                                className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold cursor-pointer"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                onClick={handleTtaSaveEditCue}
                                className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                              >
                                <Save className="w-3.5 h-3.5" />
                                <span>Save Changes</span>
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-800 text-sm leading-relaxed">{cue.text}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Empty State */
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-12 text-center text-slate-400 space-y-4">
                <Radio className="w-14 h-14 text-slate-300 mx-auto" />
                <div className="space-y-1">
                  <h4 className="font-semibold text-slate-700 text-base">Transcript-to-Audio Studio Ready</h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Paste an SRT or plain text transcript, upload a subtitle file (.srt, .vtt), or import from a completed transcription task to start synthesizing.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 max-w-sm mx-auto text-left text-[11px] text-slate-500 pt-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Narration & Timed Modes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>SRT / WebVTT / Plain Text</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Per-Segment Voice Override</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Conflict Detection & Tempo</span>
                  </div>
                </div>
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
                            {(task.tool_type === 'video_to_audio' || task.tool_type === 'text_to_speech' || task.tool_type === 'transcript_to_audio') && (
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
