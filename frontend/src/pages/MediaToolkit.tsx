import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Video,
  FileAudio,
  FileText,
  AlignLeft,
  ListMusic,
  FileCode,
  Mic2,
  Radio,
  Languages,
  Layers,
  Archive,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  ChevronRight,
  Search,
  History,
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
  ShieldCheck,
  Film,
  Scissors,
  Zap,
} from 'lucide-react';
import { api } from '../services/api';
import { DeleteToolkitTaskModal } from '../components/common/DeleteToolkitTaskModal';
import { VideoTrimmer } from '../components/toolkit/VideoTrimmer';
import { AudioTrimmer } from '../components/toolkit/AudioTrimmer';
import { AudioCleaning } from '../components/toolkit/AudioCleaning';
import { TranscriptToText } from '../components/toolkit/TranscriptToText';
import { formatCambodiaDateTime } from '../utils/date';
import {
  ProjectSummary,
  ToolkitTask,
  ToolkitTranscriptSegment,
  TTSVoiceOption,
  EmotionStyleOption,
  ParsedTranscriptCue,
  TimingConflictItem,
  TranslationLanguagePair,
  SubtitleConvertResponse,
  TranslationProviderInfo,
  VideoDownloaderMetadata,
} from '../types';

export type ToolkitViewMode = 'overview' | 'workspace' | 'history';

export const SLUG_TO_TOOL_ID: Record<string, string> = {
  'audio-cleaning': 'audio_cleaning',
  'audio_cleaning': 'audio_cleaning',
  'video-to-audio': 'video_to_audio',
  'video_to_audio': 'video_to_audio',
  'video-to-transcript': 'video_to_transcript',
  'video_to_transcript': 'video_to_transcript',
  'video-to-text': 'video_to_text',
  'video_to_text': 'video_to_text',
  'audio-to-transcript': 'audio_to_transcript',
  'audio_to_transcript': 'audio_to_transcript',
  'audio-to-text': 'audio_to_text',
  'audio_to_text': 'audio_to_text',
  'text-to-speech': 'text_to_speech',
  'text_to_speech': 'text_to_speech',
  'transcript-to-audio': 'transcript_to_audio',
  'transcript_to_audio': 'transcript_to_audio',
  'translation': 'text_translation',
  'text-translation': 'text_translation',
  'text_translation': 'text_translation',
  'subtitle-converter': 'subtitle_conversion',
  'subtitle-conversion': 'subtitle_conversion',
  'subtitle_conversion': 'subtitle_conversion',
  'transcript-to-text': 'transcript_to_text',
  'transcript_to_text': 'transcript_to_text',
  'video-downloader': 'video_downloader',
  'video_downloader': 'video_downloader',
  'video-trimmer': 'video_trimmer',
  'video_trimmer': 'video_trimmer',
  'audio-trimmer': 'audio_trimmer',
  'audio_trimmer': 'audio_trimmer',
};

export const TOOL_ID_TO_SLUG: Record<string, string> = {
  'audio_cleaning': 'audio-cleaning',
  'video_to_audio': 'video-to-audio',
  'video_to_transcript': 'video-to-transcript',
  'video_to_text': 'video-to-text',
  'audio_to_transcript': 'audio-to-transcript',
  'audio_to_text': 'audio-to-text',
  'text_to_speech': 'text-to-speech',
  'transcript_to_audio': 'transcript-to-audio',
  'text_translation': 'translation',
  'translation': 'translation',
  'subtitle_conversion': 'subtitle-converter',
  'transcript_to_text': 'transcript-to-text',
  'video_downloader': 'video-downloader',
  'video_trimmer': 'video-trimmer',
  'audio_trimmer': 'audio-trimmer',
};

export const parseToolkitRoute = (hash: string): { mode: ToolkitViewMode; toolId?: string } => {
  const clean = hash.replace(/^#\/?/, '').trim();
  if (!clean.startsWith('toolkit')) {
    return { mode: 'overview' };
  }
  const sub = clean.replace(/^toolkit\/?/, '').trim();
  if (!sub || sub === 'overview') {
    return { mode: 'overview' };
  }
  if (sub === 'history') {
    return { mode: 'history' };
  }
  const toolId = SLUG_TO_TOOL_ID[sub];
  if (toolId) {
    return { mode: 'workspace', toolId };
  }
  return { mode: 'overview' };
};

interface MediaToolkitProps {
  projects?: ProjectSummary[];
}

export const MediaToolkit: React.FC<MediaToolkitProps> = ({ projects = [] }) => {
  const initialRoute = parseToolkitRoute(typeof window !== 'undefined' ? window.location.hash : '');
  const [viewMode, setViewMode] = useState<ToolkitViewMode>(initialRoute.mode);
  const [selectedTool, setSelectedTool] = useState<string>(initialRoute.toolId || 'video_to_audio');
  const [showLanguageInfo, setShowLanguageInfo] = useState<boolean>(false);
  const [overviewCategory, setOverviewCategory] = useState<'all' | 'audio_asr' | 'speech' | 'translation'>('all');

  // History search, filter, and sort state
  const [historySearch, setHistorySearch] = useState<string>('');
  const [historyToolFilter, setHistoryToolFilter] = useState<string>('all');
  const [historyStatusFilter, setHistoryStatusFilter] = useState<string>('all');
  const [historySortOrder, setHistorySortOrder] = useState<'desc' | 'asc'>('desc');

  // Common Input State
  const [inputMode, setInputMode] = useState<'upload' | 'project'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>('');

  // Video to Audio State
  const [audioTargetFormat, setAudioTargetFormat] = useState<string>('mp3');
  const [isExtractingAudio, setIsExtractingAudio] = useState<boolean>(false);
  const [extractProgress, setExtractProgress] = useState<number>(0);
  const [extractStatusMsg, setExtractStatusMsg] = useState<string>('');

  // Transcription State (Phase 13E.2)
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);
  const [transcribeProgress, setTranscribeProgress] = useState<number>(0);
  const [transcribeStatusMsg, setTranscribeStatusMsg] = useState<string>('');

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
  const [ttsEmotionStyle, setTtsEmotionStyle] = useState<string>('calm');
  const [emotionStyles, setEmotionStyles] = useState<EmotionStyleOption[]>([]);
  const [ttsPauseDuration, setTtsPauseDuration] = useState<number>(0.4);
  const [ttsTargetFormat, setTtsTargetFormat] = useState<string>('mp3');
  const [isTtsPreviewLoading, setIsTtsPreviewLoading] = useState<boolean>(false);
  const [ttsPreviewAudioUrl, setTtsPreviewAudioUrl] = useState<string | null>(null);
  const [isTtsGenerating, setIsTtsGenerating] = useState<boolean>(false);
  const [regeneratingSegmentId, setRegeneratingSegmentId] = useState<string | null>(null);
  const [editingTtsSegmentId, setEditingTtsSegmentId] = useState<string | null>(null);
  const [editingTtsSegmentText, setEditingTtsSegmentText] = useState<string>('');
  const [editingTtsSegmentEmotion, setEditingTtsSegmentEmotion] = useState<string>('calm');
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
  const [ttaEditingCueEmotion, setTtaEditingCueEmotion] = useState<string>('');
  const [ttaSourceFilename, setTtaSourceFilename] = useState<string>('transcript.srt');
  const [ttaSourceTaskId, setTtaSourceTaskId] = useState<string | null>(null);
  const [acknowledgedConflictsTaskId, setAcknowledgedConflictsTaskId] = useState<string | null>(null);
  const ttaFileInputRef = useRef<HTMLInputElement | null>(null);

  // Timed Fitting Controls (Phase 13E.5)
  const [ttaFitToTimestamps, setTtaFitToTimestamps] = useState<boolean>(true);
  const [ttaMinSpeed, setTtaMinSpeed] = useState<number>(0.75);
  const [ttaMaxSpeed, setTtaMaxSpeed] = useState<number>(1.25);
  const [ttaFitTolerance] = useState<number>(0.05);
  const [ttaAllowSlowDown, setTtaAllowSlowDown] = useState<boolean>(true);
  const [ttaOverflowPolicy, setTtaOverflowPolicy] = useState<'allow_overlap' | 'truncate_fade' | 'fail'>('allow_overlap');
  const [ttaFillMode, setTtaFillMode] = useState<'natural' | 'stretch'>('natural');

  // Translation Studio State (Phase 13E.5)
  const [transMode, setTransMode] = useState<'text' | 'transcript'>('text');
  const [transInputTab, setTransInputTab] = useState<'paste' | 'upload' | 'import'>('paste');
  const [transText, setTransText] = useState<string>(
    'Hello everyone, welcome to KhmerDub AI. Today we are testing high-quality automated translation.'
  );
  const [transSourceLang, setTransSourceLang] = useState<string>('en');
  const [transTargetLang, setTransTargetLang] = useState<string>('km');
  const [transProvider, setTransProvider] = useState<string>('nllb');
  const [transProviders, setTransProviders] = useState<TranslationProviderInfo[]>([]);
  const [transLanguagePairs, setTransLanguagePairs] = useState<TranslationLanguagePair[]>([]);
  const [transImportTaskId, setTransImportTaskId] = useState<string>('');
  const [transSelectedFile, setTransSelectedFile] = useState<File | null>(null);
  const [transPastedSrt, setTransPastedSrt] = useState<string>(
    `1\n00:00:01,000 --> 00:00:04,500\nHello everyone, welcome to KhmerDub AI.\n\n2\n00:00:05,000 --> 00:00:08,200\nToday we are translating speech with timestamps.`
  );
  const [transIsTranslating, setTransIsTranslating] = useState<boolean>(false);
  const [transEditingSegId, setTransEditingSegId] = useState<string | null>(null);
  const [transEditingSegText, setTransEditingSegText] = useState<string>('');
  const [transRetryingSegId, setTransRetryingSegId] = useState<string | null>(null);
  const transFileInputRef = useRef<HTMLInputElement | null>(null);

  // Subtitle Converter State (Phase 13E.5)
  const [convSourceFormat, setConvSourceFormat] = useState<string>('srt');
  const [convTargetFormat, setConvTargetFormat] = useState<string>('vtt');
  const [convContent, setConvContent] = useState<string>(
    `1\n00:00:01,000 --> 00:00:03,500\nសួស្តីបងប្អូនទាំងអស់គ្នា\n\n2\n00:00:04,000 --> 00:00:06,000\nសូមស្វាគមន៍`
  );
  const [convResult, setConvResult] = useState<SubtitleConvertResponse | null>(null);
  const [convIsConverting, setConvIsConverting] = useState<boolean>(false);
  const [convCopied, setConvCopied] = useState<boolean>(false);
  const convFileInputRef = useRef<HTMLInputElement | null>(null);

  // Video Downloader State (Phase 13F)
  const [downloaderUrl, setDownloaderUrl] = useState<string>('');
  const [downloaderOutputType, setDownloaderOutputType] = useState<'video' | 'audio'>('video');
  const [downloaderQuality, setDownloaderQuality] = useState<string>('best');
  const [downloaderAudioFormat, setDownloaderAudioFormat] = useState<string>('mp3');
  const [downloaderMeta, setDownloaderMeta] = useState<VideoDownloaderMetadata | null>(null);
  const [downloaderInspecting, setDownloaderInspecting] = useState<boolean>(false);
  const [downloaderStarting, setDownloaderStarting] = useState<boolean>(false);
  const [downloaderActiveTaskId, setDownloaderActiveTaskId] = useState<string | null>(null);
  const [downloaderActiveTask, setDownloaderActiveTask] = useState<ToolkitTask | null>(null);
  const [downloaderCancelling, setDownloaderCancelling] = useState<boolean>(false);
  const [downloaderImporting, setDownloaderImporting] = useState<boolean>(false);
  const [downloaderHandoffLoading, setDownloaderHandoffLoading] = useState<string | null>(null);

  // Active Task & History
  const [activeTask, setActiveTask] = useState<ToolkitTask | null>(null);
  const [tasks, setTasks] = useState<ToolkitTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState<boolean>(false);
  const [taskToDelete, setTaskToDelete] = useState<ToolkitTask | null>(null);
  const [isDeletingTask, setIsDeletingTask] = useState<boolean>(false);

  // Audio Preview Player
  const [playingTaskId, setPlayingTaskId] = useState<string | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Dependent derived tasks for lineage warning
  const taskDependentCount = taskToDelete
    ? tasks.filter((t) => t.source_task_id === taskToDelete.id).length
    : 0;

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

  // Scroll to top helper
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    const mainEl = document.getElementById('main-scroll-container');
    if (mainEl) {
      mainEl.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  // Sync state on hash change (browser back/forward or URL navigation)
  useEffect(() => {
    const handleHashChange = () => {
      const route = parseToolkitRoute(window.location.hash);
      setViewMode(route.mode);
      if (route.toolId) {
        setSelectedTool(route.toolId);
      }
      scrollToTop();
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigateToOverview = () => {
    setViewMode('overview');
    window.location.hash = 'toolkit';
    scrollToTop();
  };

  const navigateToTool = (toolId: string) => {
    const slug = TOOL_ID_TO_SLUG[toolId] || 'video-to-audio';
    setSelectedTool(toolId);
    setViewMode('workspace');
    window.location.hash = `toolkit/${slug}`;
    scrollToTop();
  };

  const navigateToHistory = () => {
    setViewMode('history');
    window.location.hash = 'toolkit/history';
    scrollToTop();
  };

  const handleOpenTaskInWorkspace = async (task: ToolkitTask) => {
    try {
      const full = await api.getToolkitTask(task.id);
      setActiveTask(full);
      let targetTool = full.tool_type;
      if (full.tool_type === 'video_downloader') {
        targetTool = 'video_downloader';
        setDownloaderActiveTask(full);
        const sourceUrl = (full.source_media_metadata && (full.source_media_metadata as any).url) || (full.source_file_path && full.source_file_path.startsWith('http') ? full.source_file_path : '');
        if (sourceUrl) {
          setDownloaderUrl(sourceUrl);
        }
      } else if (full.tool_type === 'transcript_translation') {
        targetTool = 'text_translation';
        setTransMode('transcript');
      } else if (full.tool_type === 'text_translation' || full.tool_type === 'translation') {
        targetTool = 'text_translation';
        setTransMode('text');
      } else if (full.tool_type === 'transcript_to_text') {
        targetTool = 'transcript_to_text';
      } else if (full.tool_type === 'text_to_speech' && full.full_text) {
        setTtsText(full.full_text);
      }
      navigateToTool(targetTool);
    } catch (err: any) {
      console.error('Failed to load task details:', err);
      setActiveTask(task);
      const targetTool = task.tool_type === 'translation' ? 'text_translation' : task.tool_type;
      navigateToTool(targetTool);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // Active Concurrent Processing Tasks
  const activeProcessingTasks = useMemo(() => {
    return tasks.filter((t) => ['pending', 'processing', 'cancelling'].includes(t.status));
  }, [tasks]);

  const getToolIcon = (toolType: string) => {
    switch (toolType) {
      case 'video_to_audio':
        return <FileAudio className="w-4 h-4 text-purple-400" />;
      case 'video_to_transcript':
      case 'video_to_text':
      case 'audio_to_transcript':
      case 'audio_to_text':
        return <FileText className="w-4 h-4 text-indigo-400" />;
      case 'text_to_speech':
        return <Volume2 className="w-4 h-4 text-amber-400" />;
      case 'transcript_to_audio':
        return <Mic2 className="w-4 h-4 text-emerald-400" />;
      case 'text_translation':
      case 'transcript_translation':
      case 'translation':
        return <Languages className="w-4 h-4 text-blue-400" />;
      case 'audio_cleaning':
        return <Sparkles className="w-4 h-4 text-teal-400" />;
      case 'video_downloader':
        return <Download className="w-4 h-4 text-rose-400" />;
      case 'video_trimmer':
      case 'audio_trimmer':
        return <Scissors className="w-4 h-4 text-orange-400" />;
      default:
        return <Zap className="w-4 h-4 text-indigo-400" />;
    }
  };

  const getToolLabel = (toolType: string) => {
    switch (toolType) {
      case 'video_to_audio':
        return 'Video to Audio';
      case 'video_to_transcript':
        return 'Video to Transcript';
      case 'video_to_text':
        return 'Video to Text';
      case 'audio_to_transcript':
        return 'Audio to Transcript';
      case 'audio_to_text':
        return 'Audio to Text';
      case 'text_to_speech':
        return 'Text to Speech';
      case 'transcript_to_audio':
        return 'Transcript to Audio';
      case 'text_translation':
        return 'Text Translation';
      case 'transcript_translation':
        return 'Transcript Translation';
      case 'audio_cleaning':
        return 'Audio Cleaning';
      case 'video_downloader':
        return 'Media Downloader';
      case 'video_trimmer':
        return 'Video Trimmer';
      case 'audio_trimmer':
        return 'Audio Trimmer';
      default:
        return toolType.replace(/_/g, ' ');
    }
  };

  // Unified Multi-Task Concurrency Polling (Runs automatically whenever tasks are active)
  useEffect(() => {
    if (activeProcessingTasks.length === 0 && !downloaderActiveTaskId) return;

    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const updated = await api.listToolkitTasks();
        if (!isMounted) return;
        setTasks(updated);

        // Keep activeTask synced if it's currently processing or recently completed
        if (activeTask && ['pending', 'processing', 'cancelling'].includes(activeTask.status)) {
          const matching = updated.find((t) => t.id === activeTask.id);
          if (matching && matching.status !== activeTask.status) {
            const fullTask = await api.getToolkitTask(matching.id);
            if (isMounted) setActiveTask(fullTask);
          }
        }

        // Also sync downloader if active
        if (downloaderActiveTaskId) {
          const dlTask = updated.find((t) => t.id === downloaderActiveTaskId);
          if (dlTask) {
            setDownloaderActiveTask(dlTask);
            if (['completed', 'failed', 'cancelled'].includes(dlTask.status)) {
              setDownloaderActiveTaskId(null);
              if (dlTask.status === 'completed') {
                setActiveTask(dlTask);
              }
            }
          }
        }
      } catch (err) {
        console.warn('Unified multi-task polling error:', err);
      }
    }, 1500);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeProcessingTasks.length, downloaderActiveTaskId, activeTask]);

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

  // Load Translation Providers & Supported Pairs (Phase 13E.5)
  useEffect(() => {
    api.getToolkitTranslationProviders()
      .then((data) => {
        setTransProviders(data);
        if (data.length > 0 && !data.some((p) => p.id === transProvider)) {
          setTransProvider(data[0].id);
        }
      })
      .catch((e) => console.warn('Could not load translation providers:', e));

    api.getTranslationLanguages()
      .then((data) => setTransLanguagePairs(data))
      .catch((e) => console.warn('Could not load translation language pairs:', e));

    api.getEmotionStyles()
      .then((data) => setEmotionStyles(data))
      .catch((e) => console.warn('Could not load emotion styles:', e));
  }, []);

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
      setIsExtractingAudio(true);
      setExtractProgress(20);
      setExtractStatusMsg('Validating video container & audio streams...');

      const formData = new FormData();
      if (inputMode === 'upload' && selectedFile) {
        formData.append('file', selectedFile);
      } else if (inputMode === 'project' && selectedProjectId) {
        formData.append('project_id', selectedProjectId);
      }
      formData.append('target_format', audioTargetFormat);

      setExtractProgress(50);
      setExtractStatusMsg(`Extracting audio stream into ${audioTargetFormat.toUpperCase()}...`);

      const result = await api.extractAudio(formData);
      setExtractProgress(100);
      setExtractStatusMsg('Extraction completed successfully!');
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
      setIsExtractingAudio(false);
      setTimeout(() => {
        setExtractProgress(0);
        setExtractStatusMsg('');
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

    try {
      setIsTranscribing(true);
      setTranscribeProgress(15);
      setTranscribeStatusMsg('Analyzing media container & preparing 16kHz audio stream...');

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

      setTranscribeProgress(45);
      setTranscribeStatusMsg('Transcribing speech segments with Faster-Whisper ASR...');

      const result = await api.transcribeMedia(formData);

      setTranscribeProgress(100);
      setTranscribeStatusMsg('Transcription completed successfully!');
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
      setIsTranscribing(false);
      setTimeout(() => {
        setTranscribeProgress(0);
        setTranscribeStatusMsg('');
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
      if (['audio_cleaning', 'video_to_audio', 'video_to_transcript', 'video_to_text', 'audio_to_transcript', 'audio_to_text', 'text_to_speech', 'transcript_to_audio', 'text_translation', 'transcript_translation', 'subtitle_conversion'].includes(full.tool_type)) {
        if (full.tool_type === 'transcript_translation') {
          setSelectedTool('text_translation');
          setTransMode('transcript');
        } else if (full.tool_type === 'text_translation') {
          setSelectedTool('text_translation');
          setTransMode('text');
        } else {
          setSelectedTool(full.tool_type);
        }
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
        emotion_style: ttsEmotionStyle,
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
        emotion_style: ttsEmotionStyle,
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

  const handleStartEditTtsSegment = (segId: string, currentText: string, currentEmotion?: string | null) => {
    setEditingTtsSegmentId(segId);
    setEditingTtsSegmentText(currentText);
    setEditingTtsSegmentEmotion(currentEmotion || ttsEmotionStyle || 'calm');
  };

  const handleCancelEditTtsSegment = () => {
    setEditingTtsSegmentId(null);
    setEditingTtsSegmentText('');
  };

  const handleRegenerateTtsSegment = async (segmentId: string, textToUse?: string, emotionToUse?: string) => {
    if (!activeTask) return;
    setError(null);
    try {
      setRegeneratingSegmentId(segmentId);
      const updated = await api.regenerateToolkitTTSSegment(activeTask.id, segmentId, {
        text: textToUse,
        pause_duration_seconds: ttsPauseDuration,
        emotion_style: emotionToUse || editingTtsSegmentEmotion || ttsEmotionStyle,
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

  const handleDeleteTask = (task: ToolkitTask) => {
    setTaskToDelete(task);
  };

  const handleConfirmDeleteTask = async () => {
    if (!taskToDelete) return;
    try {
      setIsDeletingTask(true);
      setError(null);
      if (playingTaskId === taskToDelete.id && audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        setPlayingTaskId(null);
      }
      await api.deleteToolkitTask(taskToDelete.id);
      if (activeTask?.id === taskToDelete.id) {
        setActiveTask(null);
      }
      setTaskToDelete(null);
      await fetchTasks();
    } catch (err: any) {
      console.error('Failed to delete toolkit task:', err);
      setError(err.message || 'Failed to delete toolkit task');
    } finally {
      setIsDeletingTask(false);
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
      if (res.has_timestamps) {
        setTtaMode('timed');
        setTtaFitToTimestamps(true);
      } else {
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
        if (res.has_timestamps) {
          setTtaMode('timed');
          setTtaFitToTimestamps(true);
        } else {
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
      if (res.has_timestamps) {
        setTtaMode('timed');
        setTtaFitToTimestamps(true);
      } else {
        setTtaMode('narration');
      }
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
          emotion_style: c.emotion_style || ttsEmotionStyle,
        })),
        mode: ttaMode,
        provider: ttsSelectedProvider,
        voice: ttsSelectedVoice,
        language: ttsLanguage,
        emotion_style: ttsEmotionStyle,
        target_format: ttsTargetFormat,
        pause_duration_seconds: ttsPauseDuration,
        fit_to_timestamps: ttaFitToTimestamps,
        min_speed: ttaMinSpeed,
        max_speed: ttaMaxSpeed,
        fit_tolerance_sec: ttaFitTolerance,
        allow_slow_down: ttaAllowSlowDown,
        overflow_policy: ttaOverflowPolicy,
        fill_mode: ttaFillMode,
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
    setTtaEditingCueEmotion(cue.emotion_style || '');
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
      emotion_style: ttaEditingCueEmotion || null,
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
        fit_to_timestamps: ttaFitToTimestamps,
        min_speed: ttaMinSpeed,
        max_speed: ttaMaxSpeed,
        fit_tolerance_sec: ttaFitTolerance,
        allow_slow_down: ttaAllowSlowDown,
        overflow_policy: ttaOverflowPolicy,
        fill_mode: ttaFillMode,
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

  // Translation Studio Handlers (Phase 13E.5)
  const handleTranslateText = async () => {
    setError(null);
    if (!transText.trim()) {
      setError('Please enter or paste text to translate.');
      return;
    }

    try {
      setTransIsTranslating(true);
      setStatusMessage('Translating text with neural AI model...');
      const result = await api.translateText({
        text: transText.trim(),
        source_lang: transSourceLang,
        target_lang: transTargetLang,
        provider: transProvider,
      });
      setActiveTask(result);
      setStatusMessage('Translation completed successfully!');
      await fetchTasks();
    } catch (err: any) {
      setError(err.message || 'Translation failed.');
    } finally {
      setTransIsTranslating(false);
    }
  };

  const handleTranslateTranscript = async () => {
    setError(null);
    try {
      setTransIsTranslating(true);
      setStatusMessage('Translating transcript segments with timing preservation...');

      const payload: any = {
        source_lang: transSourceLang,
        target_lang: transTargetLang,
        provider: transProvider,
      };

      if (transInputTab === 'import') {
        if (!transImportTaskId) {
          setError('Please select a completed transcription task to import.');
          setTransIsTranslating(false);
          return;
        }
        payload.source_task_id = transImportTaskId;
      } else if (transInputTab === 'upload') {
        if (!transSelectedFile) {
          setError('Please select a subtitle file (.srt or .vtt) to translate.');
          setTransIsTranslating(false);
          return;
        }
        const text = await transSelectedFile.text();
        const parsed = await api.parseTranscriptToAudio(text, transSelectedFile.name);
        payload.segments = parsed.segments.map((s: ParsedTranscriptCue) => ({
          segment_order: s.segment_order,
          text: s.text,
          start_time: s.start_time,
          end_time: s.end_time,
        }));
        payload.filename = transSelectedFile.name;
      } else {
        if (!transPastedSrt.trim()) {
          setError('Please paste subtitle content with timestamps.');
          setTransIsTranslating(false);
          return;
        }
        const parsed = await api.parseTranscriptToAudio(transPastedSrt, 'pasted.srt');
        payload.segments = parsed.segments.map((s: ParsedTranscriptCue) => ({
          segment_order: s.segment_order,
          text: s.text,
          start_time: s.start_time,
          end_time: s.end_time,
        }));
        payload.filename = 'pasted_transcript.srt';
      }

      const result = await api.translateTranscript(payload);
      setActiveTask(result);
      setStatusMessage('Transcript translated successfully!');
      await fetchTasks();
    } catch (err: any) {
      setError(err.message || 'Transcript translation failed.');
    } finally {
      setTransIsTranslating(false);
    }
  };

  const handleSaveTranslationSegment = async (segId: string) => {
    if (!activeTask) return;
    try {
      const updated = await api.updateToolkitTranslationSegment(activeTask.id, segId, {
        text: transEditingSegText,
      });
      if (activeTask.translation_segments) {
        const nextSegs = activeTask.translation_segments.map((s) =>
          s.id === segId ? updated : s
        );
        setActiveTask({ ...activeTask, translation_segments: nextSegs });
      }
      setTransEditingSegId(null);
    } catch (err: any) {
      setError(err.message || 'Failed to update segment.');
    }
  };

  const handleRetryTranslationSegment = async (segId: string) => {
    if (!activeTask) return;
    try {
      setTransRetryingSegId(segId);
      const retried = await api.retryToolkitTranslationSegment(activeTask.id, segId);
      if (activeTask.translation_segments) {
        const nextSegs = activeTask.translation_segments.map((s) =>
          s.id === segId ? retried : s
        );
        setActiveTask({ ...activeTask, translation_segments: nextSegs });
      }
    } catch (err: any) {
      setError(err.message || 'Failed to retry segment translation.');
    } finally {
      setTransRetryingSegId(null);
    }
  };

  const handleConvertSubtitle = async () => {
    setError(null);
    if (!convContent.trim()) {
      setError('Please provide subtitle content to convert.');
      return;
    }
    try {
      setConvIsConverting(true);
      const res = await api.convertSubtitle({
        content: convContent,
        source_format: convSourceFormat,
        target_format: convTargetFormat,
      });
      setConvResult(res);
      setStatusMessage(`Successfully converted ${res.segment_count} cues to ${res.target_format.toUpperCase()}!`);
    } catch (err: any) {
      setError(err.message || 'Subtitle conversion failed.');
    } finally {
      setConvIsConverting(false);
    }
  };

  // Connected Workflows Handoffs (Phase 13E.5)
  const handleSendToTranslation = (task: ToolkitTask) => {
    setSelectedTool('text_translation');
    setTransMode('transcript');
    setTransInputTab('import');
    setTransImportTaskId(task.id);
    setError(null);
    navigateToTool('text_translation');
  };

  const handleSendToTTS = (task: ToolkitTask) => {
    setSelectedTool('text_to_speech');
    if (task.full_text) {
      setTtsText(task.full_text);
    }
    setError(null);
    navigateToTool('text_to_speech');
  };

  const handleSendToTranscriptToAudio = (task: ToolkitTask) => {
    setSelectedTool('transcript_to_audio');
    setTtaInputTab('import');
    setTtaImportTaskId(task.id);
    setTtaMode('timed');
    setError(null);
    navigateToTool('transcript_to_audio');
  };

  const handleSendTranslationToTTS = (task: ToolkitTask) => {
    setSelectedTool('text_to_speech');
    if (task.full_text) {
      setTtsText(task.full_text);
    } else if (task.translation_segments) {
      const txt = task.translation_segments
        .map((s) => s.edited_text || s.translated_text)
        .filter(Boolean)
        .join('\n\n');
      setTtsText(txt);
    }
    setError(null);
    navigateToTool('text_to_speech');
  };

  const handleSendTranslationToTranscriptToAudio = (task: ToolkitTask) => {
    setSelectedTool('transcript_to_audio');
    setTtaInputTab('paste');
    setTtaMode('timed');
    if (task.translation_segments) {
      const cues: ParsedTranscriptCue[] = task.translation_segments.map((s) => ({
        segment_order: s.segment_order,
        text: s.edited_text || s.translated_text,
        start_time: s.start_time,
        end_time: s.end_time,
      }));
      setTtaParsedCues(cues);
      setTtaHasTimestamps(true);
      setTtaParsedFormat('SRT');
      setTtaSourceFilename(`${task.source_filename}_translated.srt`);
      setTtaSourceTaskId(task.id);
    }
    setError(null);
    navigateToTool('transcript_to_audio');
  };

  // Video Downloader Handlers (Phase 13F)
  const handleInspectUrl = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!downloaderUrl.trim()) {
      setError('Please enter a valid video link.');
      return;
    }
    try {
      setDownloaderInspecting(true);
      setError(null);
      setDownloaderMeta(null);
      const meta = await api.inspectDownloaderUrl(downloaderUrl.trim());
      setDownloaderMeta(meta);
      if (meta.available_video_qualities.length > 0) {
        setDownloaderQuality(meta.available_video_qualities[0]);
      }
      if (meta.is_audio_only_source) {
        setDownloaderOutputType('audio');
      }
    } catch (err: any) {
      console.error('Failed to inspect URL:', err);
      setError(err.message || 'Unable to fetch video information.');
    } finally {
      setDownloaderInspecting(false);
    }
  };

  const handleStartDownload = async () => {
    if (!downloaderUrl.trim()) {
      setError('Please enter a video URL.');
      return;
    }
    try {
      setDownloaderStarting(true);
      setError(null);
      const task = await api.startDownloaderTask({
        url: downloaderUrl.trim(),
        output_type: downloaderOutputType,
        quality: downloaderQuality,
        audio_format: downloaderAudioFormat,
        rights_confirmed: true,
      });
      setDownloaderActiveTask(task);
      setDownloaderActiveTaskId(task.id);
      setActiveTask(task);
      fetchTasks();
    } catch (err: any) {
      console.error('Download start failed:', err);
      setError(err.message || 'Failed to start video download.');
    } finally {
      setDownloaderStarting(false);
    }
  };

  const handleCancelDownload = async (taskId: string) => {
    try {
      setDownloaderCancelling(true);
      await api.cancelDownloaderTask(taskId);
      setDownloaderActiveTaskId(null);
      fetchTasks();
      const updated = await api.getToolkitTask(taskId);
      setDownloaderActiveTask(updated);
    } catch (err: any) {
      console.error('Failed to cancel download:', err);
      setError(err.message || 'Failed to cancel download task.');
    } finally {
      setDownloaderCancelling(false);
    }
  };

  const handleImportToDubbing = async (taskId: string) => {
    try {
      setDownloaderImporting(true);
      setError(null);
      const res = await api.importDownloaderTaskToDubbing(taskId);
      if (res && res.project_id) {
        window.location.hash = `project/${res.project_id}`;
      }
    } catch (err: any) {
      console.error('Import to dubbing failed:', err);
      setError(err.message || 'Failed to import video into dubbing studio.');
    } finally {
      setDownloaderImporting(false);
    }
  };

  const handleHandoffDownloader = async (taskId: string, targetTool: string) => {
    try {
      setDownloaderHandoffLoading(targetTool);
      setError(null);
      const newTask = await api.handoffDownloaderTask(taskId, targetTool);
      setActiveTask(newTask);
      fetchTasks();
      navigateToTool(targetTool);
    } catch (err: any) {
      console.error(`Handoff to ${targetTool} failed:`, err);
      setError(err.message || `Failed to transfer media to ${targetTool}.`);
    } finally {
      setDownloaderHandoffLoading(null);
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
    { id: 'audio_cleaning', title: 'Audio Noise & Music Remover',
      desc: 'Remove background noise or music from audio and video while keeping speech clear.',
      icon: Mic2, status: 'available' as const, category: 'audio_asr' as const },
    {
      id: 'video_to_audio',
      title: 'Video to Audio',
      desc: 'Extract audio from videos in MP3, WAV, or M4A.',
      icon: Video,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'video_to_transcript',
      title: 'Video to Transcript',
      desc: 'Generate timestamped subtitle transcripts from videos.',
      icon: FileText,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'video_to_text',
      title: 'Video to Text',
      desc: 'Extract plain text transcripts from videos.',
      icon: AlignLeft,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'audio_to_transcript',
      title: 'Audio to Transcript',
      desc: 'Transcribe audio recordings into timestamped segments.',
      icon: ListMusic,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'audio_to_text',
      title: 'Audio to Text',
      desc: 'Transcribe audio recordings into plain text.',
      icon: FileCode,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'transcript_to_text',
      title: 'Transcript to Text',
      desc: 'Convert subtitle files or cues into clean, readable narrative paragraphs or plain text.',
      icon: FileText,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'text_to_speech',
      title: 'Text to Speech Studio',
      desc: 'Convert text into natural Khmer or English speech.',
      icon: Mic2,
      status: 'available' as const,
      category: 'speech' as const,
    },
    {
      id: 'transcript_to_audio',
      title: 'Transcript to Audio',
      desc: 'Generate spoken audio from subtitle transcripts.',
      icon: Radio,
      status: 'available' as const,
      category: 'speech' as const,
    },
    {
      id: 'text_translation',
      title: 'Translation Studio',
      desc: 'Translate text or subtitle transcripts between English and Khmer.',
      icon: Languages,
      status: 'available' as const,
      category: 'translation' as const,
    },
    {
      id: 'subtitle_conversion',
      title: 'Subtitle Converter',
      desc: 'Convert subtitle files between SRT and WebVTT formats.',
      icon: Layers,
      status: 'available' as const,
      category: 'translation' as const,
    },
    {
      id: 'video_downloader',
      title: 'Video Downloader',
      desc: 'Import permitted videos from supported links.',
      icon: Download,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'video_trimmer',
      title: 'Video Trimmer',
      desc: 'Trim videos to keep only the sections you need.',
      icon: Scissors,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
    {
      id: 'audio_trimmer',
      title: 'Audio Trimmer',
      desc: 'Cut audio recordings and export selected sections.',
      icon: Scissors,
      status: 'available' as const,
      category: 'audio_asr' as const,
    },
  ];

  const getToolTitle = (toolId: string) => {
    if (toolId === 'transcript_to_text' || toolId === 'transcript-to-text') {
      return 'Transcript to Text';
    }
    if (toolId === 'video_downloader' || toolId === 'video-downloader') {
      return 'Video Downloader';
    }
    if (toolId === 'video_trimmer' || toolId === 'video-trimmer') {
      return 'Video Trimmer';
    }
    if (toolId === 'audio_trimmer' || toolId === 'audio-trimmer') {
      return 'Audio Trimmer';
    }
    if (toolId === 'translation' || toolId === 'text_translation' || toolId === 'transcript_translation') {
      return 'Translation Studio';
    }
    const found = toolsList.find((t) => t.id === toolId);
    return found ? found.title : toolId.replace(/_/g, ' ');
  };

  const currentTool = toolsList.find((t) => t.id === selectedTool) || toolsList[0];
  const CurrentToolIcon = currentTool.icon;

  const filteredTasks = useMemo(() => {
    return tasks
      .filter((task) => {
        if (historyToolFilter !== 'all') {
          if (historyToolFilter === 'text_translation') {
            if (task.tool_type !== 'translation' && task.tool_type !== 'text_translation' && task.tool_type !== 'transcript_translation') {
              return false;
            }
          } else if (task.tool_type !== historyToolFilter) {
            return false;
          }
        }
        if (historyStatusFilter !== 'all' && task.status !== historyStatusFilter) {
          return false;
        }
        if (historySearch.trim()) {
          const q = historySearch.toLowerCase();
          const matchFilename = task.source_filename?.toLowerCase().includes(q);
          const matchFormat = task.target_format?.toLowerCase().includes(q);
          const matchType = task.tool_type?.toLowerCase().includes(q);
          const matchId = task.id.toLowerCase().includes(q);
          const matchText = task.full_text?.toLowerCase().includes(q);
          if (!matchFilename && !matchFormat && !matchType && !matchId && !matchText) {
            return false;
          }
        }
        return true;
      })
      .sort((a, b) => {
        const timeA = new Date(a.created_at).getTime();
        const timeB = new Date(b.created_at).getTime();
        return historySortOrder === 'desc' ? timeB - timeA : timeA - timeB;
      });
  }, [tasks, historyToolFilter, historyStatusFilter, historySearch, historySortOrder]);

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-12">
      {/* Hidden audio element for preview */}
      <audio
        ref={audioPlayerRef}
        onEnded={() => setPlayingTaskId(null)}
        onError={() => setPlayingTaskId(null)}
      />

      {/* ======================================================== */}
      {/* MULTI-TASK CONCURRENT PROCESSING TRAY                    */}
      {/* ======================================================== */}
      {activeProcessingTasks.length > 0 && (
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-indigo-500/40 text-white shadow-xl space-y-3.5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-indigo-500/20 pb-3">
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
              <span className="font-bold text-xs sm:text-sm tracking-wide text-white flex items-center gap-1.5">
                <Zap className="w-4 h-4 text-amber-400" />
                Multi-Task Engine Active ({activeProcessingTasks.length} {activeProcessingTasks.length === 1 ? 'task' : 'tasks'} running in parallel)
              </span>
            </div>
            <span className="text-[11px] text-indigo-300 bg-indigo-500/20 px-2.5 py-0.5 rounded-full border border-indigo-500/30 font-medium">
              Asynchronous background workers executing concurrently
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeProcessingTasks.map((task) => (
              <div
                key={task.id}
                className="p-3.5 rounded-xl bg-slate-950/70 border border-indigo-500/30 hover:border-indigo-400/50 transition-all flex flex-col justify-between space-y-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="p-2 rounded-lg bg-indigo-500/20 text-indigo-300 shrink-0">
                      {getToolIcon(task.tool_type)}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-100 truncate">
                        {task.source_filename || 'Media Task'}
                      </div>
                      <div className="text-[10px] text-indigo-300 font-medium">
                        {getToolLabel(task.tool_type)}
                      </div>
                    </div>
                  </div>
                  <span className="text-[10px] font-bold text-amber-300 bg-amber-400/15 border border-amber-400/30 px-2 py-0.5 rounded-full shrink-0 flex items-center gap-1">
                    <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                    {task.progress_percentage || 25}%
                  </span>
                </div>

                <div className="space-y-1.5">
                  <div className="w-full bg-slate-800/80 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-indigo-500 via-indigo-400 to-emerald-400 h-full rounded-full transition-all duration-300"
                      style={{ width: `${Math.max(task.progress_percentage || 20, 10)}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400">
                    <span className="truncate">{task.error_message || 'Processing in background...'}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTask(task);
                        if (TOOL_ID_TO_SLUG[task.tool_type]) {
                          navigateToTool(task.tool_type);
                        }
                      }}
                      className="text-indigo-300 hover:text-white font-medium underline ml-2 shrink-0 cursor-pointer"
                    >
                      Inspect Output
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Global Status / Notification Message */}
      {statusMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between shadow-xs animate-in fade-in duration-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{statusMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setStatusMessage('')}
            className="text-emerald-600 hover:text-emerald-800 cursor-pointer p-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ======================================================== */}
      {/* VIEW 1: OVERVIEW (viewMode === 'overview')               */}
      {/* ======================================================== */}
      {viewMode === 'overview' && (
        <div className="space-y-8">
          {/* Header Banner */}
          <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-8 text-white shadow-xl relative overflow-hidden">
            <div className="absolute right-0 top-0 bottom-0 w-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
              <div>
                <div className="flex items-center gap-2.5 mb-2">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    AI Media Toolkit
                  </span>
                </div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                  Media Toolkit
                </h1>
                <p className="text-slate-400 text-sm mt-1 max-w-2xl">
                  Extract audio, transcribe speech, synthesize voice, and translate content across media formats.
                </p>
              </div>

              <button
                onClick={() => setShowLanguageInfo(!showLanguageInfo)}
                className="self-start md:self-auto inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium bg-slate-800/80 hover:bg-slate-800 text-slate-300 border border-slate-700/60 transition-colors shadow-sm cursor-pointer"
                title="Toggle capabilities overview"
              >
                <Info className="w-4 h-4 text-indigo-400" />
                <span>AI Capabilities Guide</span>
                {showLanguageInfo ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>

            {/* Expandable Language Capability Matrix */}
            {showLanguageInfo && (
              <div className="mt-6 pt-6 border-t border-slate-800/80 space-y-4">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span className="font-semibold uppercase tracking-wider text-slate-300">
                    System AI Capabilities & Supported Formats
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowLanguageInfo(false)}
                    className="hover:text-white p-1 rounded-lg hover:bg-slate-800 text-slate-400 transition-colors cursor-pointer flex items-center gap-1"
                    title="Close guide"
                  >
                    <X className="w-4 h-4" />
                    <span className="text-[11px]">Close</span>
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3.5 text-xs">
                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800 space-y-1.5">
                    <span className="font-semibold text-slate-200 flex items-center gap-2">
                      <FileAudio className="w-4 h-4 text-indigo-400" />
                      Audio Extraction
                    </span>
                    <p className="text-slate-400 leading-relaxed text-[11px]">
                      Extract audio from video containers into MP3, WAV, or M4A formats.
                    </p>
                  </div>

                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800 space-y-1.5">
                    <span className="font-semibold text-slate-200 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-emerald-400" />
                      Speech-to-Text
                    </span>
                    <p className="text-slate-400 leading-relaxed text-[11px]">
                      Generate timestamped transcripts or plain text with subtitle exports.
                    </p>
                  </div>

                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800 space-y-1.5">
                    <span className="font-semibold text-slate-200 flex items-center gap-2">
                      <Mic2 className="w-4 h-4 text-amber-400" />
                      Text-to-Speech
                    </span>
                    <p className="text-slate-400 leading-relaxed text-[11px]">
                      Generate natural speech in Khmer or English with standard and custom voices.
                    </p>
                  </div>

                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800 space-y-1.5">
                    <span className="font-semibold text-slate-200 flex items-center gap-2">
                      <Radio className="w-4 h-4 text-purple-400" />
                      Transcript to Audio
                    </span>
                    <p className="text-slate-400 leading-relaxed text-[11px]">
                      Convert subtitle transcripts into continuous narration or synchronized audio.
                    </p>
                  </div>

                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800 space-y-1.5">
                    <span className="font-semibold text-slate-200 flex items-center gap-2">
                      <Languages className="w-4 h-4 text-blue-400" />
                      Translation & Converter
                    </span>
                    <p className="text-slate-400 leading-relaxed text-[11px]">
                      Translate text and convert subtitle files between SRT and WebVTT formats.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Category Filter Pills & History Shortcut Button */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl overflow-x-auto">
              <button
                type="button"
                onClick={() => setOverviewCategory('all')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  overviewCategory === 'all'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                All Tools ({toolsList.length})
              </button>
              <button
                type="button"
                onClick={() => setOverviewCategory('audio_asr')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  overviewCategory === 'audio_asr'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Audio & Video ({toolsList.filter((t) => t.category === 'audio_asr').length})
              </button>
              <button
                type="button"
                onClick={() => setOverviewCategory('speech')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  overviewCategory === 'speech'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Speech Synthesis (2)
              </button>
              <button
                type="button"
                onClick={() => setOverviewCategory('translation')}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                  overviewCategory === 'translation'
                    ? 'bg-white text-indigo-600 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Translation & Subtitles (2)
              </button>
            </div>

            <button
              type="button"
              onClick={navigateToHistory}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-all shadow-xs cursor-pointer self-start sm:self-auto"
            >
              <History className="w-4 h-4 text-indigo-600" />
              <span>Full Task History</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                {tasks.length}
              </span>
              <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            </button>
          </div>

          {/* Tool Cards Grid */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
                Available Toolkit Modules
              </h2>
              <span className="text-xs text-slate-400">Click any card to launch its dedicated workspace</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {toolsList
                .filter((t) => overviewCategory === 'all' || t.category === overviewCategory)
                .map((tool) => {
                  const Icon = tool.icon;
                  return (
                    <button
                      key={tool.id}
                      onClick={() => navigateToTool(tool.id)}
                      className="text-left p-5 rounded-2xl border border-slate-200/90 bg-white hover:border-indigo-400 hover:shadow-md transition-all duration-200 relative flex flex-col justify-between group cursor-pointer"
                    >
                      <div>
                        <div className="mb-3.5">
                          <div className="w-10 h-10 rounded-xl bg-indigo-50 group-hover:bg-indigo-600 text-indigo-600 group-hover:text-white flex items-center justify-center transition-colors">
                            <Icon className="w-5 h-5" />
                          </div>
                        </div>
                        <h3 className="font-bold text-slate-900 text-base group-hover:text-indigo-600 transition-colors">
                          {tool.title}
                        </h3>
                        <p className="text-xs text-slate-500 mt-1.5 line-clamp-2 leading-relaxed">
                          {tool.desc}
                        </p>
                      </div>

                      <div className="mt-4 pt-3.5 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-indigo-600">
                        <span>Launch Workspace</span>
                        <ArrowRight className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" />
                      </div>
                    </button>
                  );
                })}
            </div>
          </div>

          {/* Recent Tasks Summary Section */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Clock className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">Recent Media Tasks</h3>
                  <p className="text-xs text-slate-400">Quickly reopen recent workspace jobs or download outputs</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={fetchTasks}
                  disabled={tasksLoading}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                  title="Refresh tasks"
                >
                  <RefreshCw className={`w-4 h-4 ${tasksLoading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  type="button"
                  onClick={navigateToHistory}
                  className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1 cursor-pointer"
                >
                  <span>View All {tasks.length} Tasks</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {tasks.length === 0 ? (
              <div className="text-center py-8 text-slate-400 text-xs">
                No media tasks yet. Select a tool card above to extract audio, generate speech, or translate content.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {tasks.slice(0, 4).map((task) => (
                  <div
                    key={task.id}
                    className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/60 rounded-xl px-2.5 transition-colors"
                  >
                    <div className="flex items-start sm:items-center gap-3 min-w-0">
                      <span className="px-2 py-1 rounded-lg text-[10px] font-bold uppercase bg-slate-100 text-slate-700 shrink-0">
                        {task.target_format}
                      </span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-xs text-slate-900 truncate">
                            {task.source_filename || 'Media Task'}
                          </span>
                          <span className="text-[10px] text-slate-400">·</span>
                          <span className="text-[11px] text-slate-500 font-medium">
                            {getToolTitle(task.tool_type)}
                          </span>
                          {task.is_outdated && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                              Outdated
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-400 flex items-center gap-2 mt-0.5">
                          <span>{formatCambodiaDateTime(task.created_at)}</span>
                          {task.output_duration_seconds ? (
                            <>
                              <span>·</span>
                              <span>{formatDuration(task.output_duration_seconds)}</span>
                            </>
                          ) : null}
                          <span>·</span>
                          {task.status === 'completed' && (
                            <span className="text-emerald-600 font-medium inline-flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" /> Done
                            </span>
                          )}
                          {task.status === 'processing' && (
                            <span className="text-indigo-600 font-medium inline-flex items-center gap-1">
                              <RefreshCw className="w-3 h-3 animate-spin" /> Processing
                            </span>
                          )}
                          {['pending', 'cancelling', 'cancelled'].includes(task.status) && (
                            <span className="text-slate-600 font-medium capitalize">{task.status === 'pending' ? 'Queued' : task.status}</span>
                          )}
                          {task.status === 'failed' && (
                            <span className="text-rose-600 font-medium inline-flex items-center gap-1">
                              <AlertCircle className="w-3 h-3" /> Failed
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                      <button
                        type="button"
                        onClick={() => handleOpenTaskInWorkspace(task)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                        title="Open in tool workspace"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>Open in Workspace</span>
                      </button>

                      {task.status === 'completed' && (
                        <>
                          {(task.tool_type === 'video_to_audio' || task.tool_type === 'text_to_speech' || task.tool_type === 'transcript_to_audio' || task.tool_type === 'audio_trimmer') && (
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
                            title="Download Output"
                          >
                            <Download className="w-4 h-4" />
                          </a>
                        </>
                      )}

                      <button
                        onClick={() => handleDeleteTask(task)}
                        className="p-1.5 rounded-lg hover:bg-rose-50 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                        title="Delete Task"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Global Status / Notification Message */}
      {statusMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between shadow-xs animate-in fade-in duration-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{statusMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setStatusMessage('')}
            className="text-emerald-600 hover:text-emerald-800 cursor-pointer p-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ======================================================== */}
      {/* VIEW 2: TOOL WORKSPACE (viewMode === 'workspace')         */}
      {/* ======================================================== */}
      {viewMode === 'workspace' && (
        <div className="space-y-6">
          {/* Breadcrumb Navigation Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white border border-slate-200/90 rounded-2xl px-5 py-3.5 shadow-xs">
            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={navigateToOverview}
                className="inline-flex items-center gap-1.5 font-bold text-slate-700 hover:text-indigo-600 transition-colors cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>All Tools</span>
              </button>
              <span className="text-slate-300">/</span>
              <button
                type="button"
                onClick={navigateToOverview}
                className="text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
              >
                Media Toolkit
              </button>
              <span className="text-slate-300">/</span>
              <span className="font-semibold text-slate-900">{currentTool.title}</span>
            </div>

            <div className="flex items-center gap-2 self-end sm:self-auto">
              <button
                type="button"
                onClick={navigateToHistory}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200/80 text-slate-700 transition-colors cursor-pointer"
                title="View Full Task History"
              >
                <History className="w-3.5 h-3.5 text-indigo-600" />
                <span>Task History ({tasks.length})</span>
              </button>
            </div>
          </div>

          {/* Tool Workspace Header Card */}
          <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-slate-800 rounded-2xl p-5 sm:p-6 text-white shadow-md relative overflow-hidden">
            <div className="flex items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-600/30 border border-indigo-500/30 flex items-center justify-center text-indigo-300 shrink-0">
                  <CurrentToolIcon className="w-6 h-6" />
                </div>
                <div>
                  <div>
                    <h2 className="text-xl font-bold tracking-tight">{currentTool.title}</h2>
                  </div>
                  <p className="text-xs text-slate-300 mt-1 max-w-2xl leading-relaxed">
                    {currentTool.desc}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={navigateToOverview}
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-800/80 hover:bg-slate-800 text-slate-300 border border-slate-700/60 transition-colors cursor-pointer shrink-0"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Switch Tool</span>
              </button>
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
            {isExtractingAudio && (
              <div className="space-y-2 p-4 rounded-xl bg-slate-50 border border-slate-200">
                <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                    {extractStatusMsg || 'Extracting audio...'}
                  </span>
                  <span>{extractProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${extractProgress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Button */}
            <button
              onClick={handleExtractAudio}
              disabled={isExtractingAudio || (inputMode === 'upload' && !selectedFile) || (inputMode === 'project' && !selectedProjectId)}
              className="w-full py-3 px-4 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white shadow-sm transition-all duration-150 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {isExtractingAudio ? (
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
                  <button
                    type="button"
                    onClick={() => setTaskToDelete(activeTask)}
                    className="py-2.5 px-3 rounded-xl text-xs font-semibold bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                    title="Delete this task"
                  >
                    <Trash2 className="w-4 h-4" />
                    <span className="sm:hidden">Delete</span>
                  </button>
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
                    setError(null);
                  }}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                >
                  <option value="en">English (en) — Faster-Whisper Base Model</option>
                  <option value="km">Khmer (km) — Fine-Tuned Whisper ASR Engine</option>
                </select>

                {/* Language Capability Notice */}
                <div className="p-3 rounded-xl bg-indigo-50/70 border border-indigo-200/80 text-xs text-indigo-950 space-y-1">
                  <div className="flex items-center gap-1.5 font-semibold text-indigo-900">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>Supported Transcription Languages</span>
                  </div>
                  <p className="text-[11px] text-indigo-700 leading-relaxed">
                    Speech recognition supports both <strong>English (en)</strong> and <strong>Khmer (km)</strong>. Khmer speech is transcribed using a specialized fine-tuned Whisper ASR model with timestamped segments.
                  </p>
                </div>
              </div>
            </div>

            {/* Progress Bar */}
            {isTranscribing && (
              <div className="space-y-2 p-4 rounded-xl bg-slate-50 border border-slate-200">
                <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                    {transcribeStatusMsg || 'Transcribing audio speech...'}
                  </span>
                  <span>{transcribeProgress}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${transcribeProgress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Transcribe Button */}
            <button
              onClick={handleTranscribeMedia}
              disabled={isTranscribing || (inputMode === 'upload' && !selectedFile) || (inputMode === 'project' && !selectedProjectId)}
              className="w-full py-3 px-4 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white shadow-sm transition-all duration-150 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {isTranscribing ? (
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

                {/* Connected Workflows Toolbar */}
                <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-100 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2 font-semibold text-indigo-900">
                    <Sparkles className="w-4 h-4 text-indigo-600" />
                    <span>Connected Workflows:</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleSendToTranslation(activeTask)}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                      title="Translate this transcript to Khmer or English"
                    >
                      <Languages className="w-3.5 h-3.5" />
                      <span>Translate Transcript</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSendToTTS(activeTask)}
                      className="px-3 py-1.5 rounded-lg bg-white border border-indigo-200 hover:bg-indigo-50 text-indigo-700 font-semibold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                      title="Generate continuous speech narration from this transcript"
                    >
                      <Mic2 className="w-3.5 h-3.5" />
                      <span>Send to Text-to-Speech</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSendToTranscriptToAudio(activeTask)}
                      className="px-3 py-1.5 rounded-lg bg-white border border-indigo-200 hover:bg-indigo-50 text-indigo-700 font-semibold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                      title="Convert timestamped segments to synchronized speech"
                    >
                      <Radio className="w-3.5 h-3.5" />
                      <span>Send to Transcript-to-Audio</span>
                    </button>
                    <a
                      href={api.getTaskBundleUrl(activeTask.id)}
                      download={`${activeTask.source_filename || 'task'}_bundle.zip`}
                      className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                      title="Download complete ZIP archive with transcripts, translations, and audio"
                    >
                      <Archive className="w-3.5 h-3.5" />
                      <span>Download All (ZIP)</span>
                    </a>
                    <button
                      type="button"
                      onClick={() => setTaskToDelete(activeTask)}
                      className="p-1.5 rounded-lg border border-slate-200 hover:bg-rose-50 hover:border-rose-200 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                      title="Delete this task"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
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
                  <optgroup label="Custom Voice Profiles">
                    {ttsVoices
                      .filter((v) => v.is_custom)
                      .map((v) => (
                        <option
                          key={`${v.provider}:${v.voice}`}
                          value={`${v.provider}:${v.voice}`}
                          disabled={!v.is_available}
                        >
                          {v.label} ({v.gender}) {!v.is_available ? '(Offline)' : '• Ready'}
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

            {/* Acting & Emotion Style Control (Drama / TVB Style, Storytelling, Explain, etc.) */}
            <div className="space-y-2.5 p-3.5 rounded-xl bg-slate-50 border border-slate-200">
              <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-amber-500" />
                  <span>Emotion & Acting Style (Drama / TVB)</span>
                </label>
                <span className="text-[10px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                  Adaptive Prosody
                </span>
              </div>

              {/* Quick Pills for instant 1-click selection */}
              <div className="flex flex-wrap gap-1">
                {[
                  { id: 'calm', label: 'ធម្មតា' },
                  { id: 'storytelling', label: '📖 និទានរឿង' },
                  { id: 'explain', label: '💡 ពន្យល់' },
                  { id: 'dramatic_tvb', label: '🎬 TVB Drama' },
                  { id: 'angry', label: '😡 ខឹង' },
                  { id: 'happy', label: '😊 រីករាយ' },
                  { id: 'sad', label: '😢 សោកសៅ' },
                  { id: 'whisper', label: '🤫 ខ្សឹប' },
                  { id: 'excited', label: '⚡ រំភើប' },
                ].map((pill) => (
                  <button
                    key={pill.id}
                    type="button"
                    onClick={() => setTtsEmotionStyle(pill.id)}
                    className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                      ttsEmotionStyle === pill.id
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'bg-white hover:bg-slate-200/80 text-slate-700 border border-slate-200'
                    }`}
                  >
                    {pill.label}
                  </button>
                ))}
              </div>

              {/* Full Emotion Style Dropdown */}
              <select
                value={ttsEmotionStyle}
                onChange={(e) => setTtsEmotionStyle(e.target.value)}
                className="w-full p-2 rounded-lg border border-slate-200 bg-white text-slate-800 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
              >
                {emotionStyles.map((emo) => (
                  <option key={emo.id} value={emo.id}>
                    {emo.label_km} ({emo.label_en}) • Rate: {emo.prosody.rate || '+0%'}, Pitch: {emo.prosody.pitch || '+0Hz'}
                  </option>
                ))}
              </select>

              {/* Active Emotion Description & Prosody Card */}
              {(() => {
                const currentEmo = emotionStyles.find((e) => e.id === ttsEmotionStyle);
                if (!currentEmo) return null;
                return (
                  <div className="p-2.5 rounded-lg bg-white border border-amber-200/80 text-[11px] space-y-1">
                    <div className="flex items-center justify-between text-amber-900 font-semibold">
                      <span>{currentEmo.label_km} ({currentEmo.label_en})</span>
                      <span className="font-mono text-[10px] bg-amber-100/80 text-amber-800 px-1.5 py-0.5 rounded">
                        Rate: {currentEmo.prosody.rate || '+0%'} | Pitch: {currentEmo.prosody.pitch || '+0Hz'} | Vol: {currentEmo.prosody.volume || '+0%'}
                      </span>
                    </div>
                    <p className="text-slate-500 text-[11px] leading-relaxed">
                      {currentEmo.description}
                    </p>
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
                    setTtsEmotionStyle('calm');
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
                    setTtsEmotionStyle('storytelling');
                    setTtsText(
                      'កាលពីព្រេងនាយ មានកុមារាម្នាក់រស់នៅតាមជនបទដ៏ស្រស់ស្អាត។ គាត់តែងតែឧស្សាហ៍ព្យាយាមរៀនសូត្ររាល់ថ្ងៃ។ ដោយសារការតស៊ូ គាត់បានក្លាយជាមនុស្សជោគជ័យ។'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  📖 និទានរឿង
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('km');
                    setTtsEmotionStyle('explain');
                    setTtsText(
                      'សូមជម្រាបសួរអ្នកទាំងអស់គ្នា។ ថ្ងៃនេះខ្ញុំនឹងពន្យល់អំពីរបៀបប្រើប្រាស់ប្រព័ន្ធបញ្ញាសិប្បនិម្មិត។ ដំបូងយើងត្រូវជ្រើសរើសឯកសារ បន្ទាប់មកចុចដំណើរការ។'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  💡 ពន្យល់ (Tutorial)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('km');
                    setTtsEmotionStyle('dramatic_tvb');
                    setTtsText(
                      'ឯងគិតថាឯងអាចគេចផុតពីកណ្តាប់ដៃរបស់ខ្ញុំបានឬ? ថ្ងៃនេះជាថ្ងៃចុងក្រោយរបស់ឯងហើយ! ចូលមក!'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  🎬 TVB Drama
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('km');
                    setTtsEmotionStyle('angry');
                    setTtsText(
                      'ឈប់ភ្លាម! ឯងហ៊ានក្បត់នឹងយើងឬ? ឆាប់ប្រគល់របស់នោះមកវិញភ្លាម វ៉ើយ!'
                    );
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors cursor-pointer"
                >
                  😡 ខឹងសម្បារ
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTtsLanguage('en');
                    setTtsEmotionStyle('calm');
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
                    <a
                      href={api.getTaskBundleUrl(activeTask.id)}
                      download={`${activeTask.source_filename || 'narration'}_bundle.zip`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition-colors shadow-xs cursor-pointer"
                      title="Download complete ZIP archive"
                    >
                      <Archive className="w-3.5 h-3.5" />
                      <span>Bundle (ZIP)</span>
                    </a>
                    <button
                      type="button"
                      onClick={() => setTaskToDelete(activeTask)}
                      className="p-1.5 rounded-lg border border-slate-200 hover:bg-rose-50 hover:border-rose-200 text-slate-400 hover:text-rose-600 transition-colors cursor-pointer"
                      title="Delete this task"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
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
                              {seg.emotion_style && (
                                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                                  {emotionStyles.find((e) => e.id === seg.emotion_style)?.label_km || seg.emotion_style}
                                </span>
                              )}
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
                                  onClick={() => handleStartEditTtsSegment(seg.id, seg.text, seg.emotion_style)}
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
                            <div className="space-y-2.5">
                              <textarea
                                value={editingTtsSegmentText}
                                onChange={(e) => setEditingTtsSegmentText(e.target.value)}
                                className="w-full p-2.5 rounded-lg border border-indigo-300 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 resize-y"
                                rows={2}
                                autoFocus
                              />
                              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-100">
                                <div className="flex items-center gap-1.5 text-xs">
                                  <span className="font-semibold text-slate-600">Acting Style:</span>
                                  <select
                                    value={editingTtsSegmentEmotion}
                                    onChange={(e) => setEditingTtsSegmentEmotion(e.target.value)}
                                    className="p-1 rounded-md border border-slate-300 bg-white text-xs font-medium cursor-pointer"
                                  >
                                    {emotionStyles.map((emo) => (
                                      <option key={emo.id} value={emo.id}>
                                        {emo.label_km} ({emo.label_en})
                                      </option>
                                    ))}
                                  </select>
                                </div>

                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={handleCancelEditTtsSegment}
                                    className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold cursor-pointer"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleRegenerateTtsSegment(seg.id, editingTtsSegmentText, editingTtsSegmentEmotion)}
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
            <div className="border-b border-slate-100 pb-4">
              <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                <Radio className="w-5 h-5 text-indigo-600" />
                Transcript to Audio Studio
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Convert timestamped transcripts or plain text into natural continuous speech or timed tracks.
              </p>
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

            {/* Timed Mode Slot Fitting Controls (Phase 13E.5) */}
            {ttaMode === 'timed' && (
              <div className="space-y-3 p-3.5 bg-slate-50 border border-slate-200 rounded-xl">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-800 flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ttaFitToTimestamps}
                      onChange={(e) => setTtaFitToTimestamps(e.target.checked)}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer w-4 h-4"
                    />
                    <span>Fit to timestamps</span>
                  </label>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${ttaFitToTimestamps ? 'bg-indigo-100 text-indigo-700 border border-indigo-200' : 'bg-slate-200 text-slate-600'}`}>
                    {ttaFitToTimestamps ? 'Exact Fit Active' : 'Pass-through'}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 leading-snug">
                  Speed up or slow down speech to fit every segment into its exact SRT slot.
                </p>

                {ttaFitToTimestamps && (
                  <div className="space-y-3 pt-2 border-t border-slate-200/80 text-xs">
                    {/* Fill Mode Setting (Phase 13E.5) */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-medium text-slate-600">Fill Mode</span>
                        <span className="font-mono text-[10px] text-slate-400">
                          {ttaFillMode === 'natural' ? 'Min 0.75x + Pad Silence' : 'Min 0.50x Stretch'}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setTtaFillMode('natural');
                            setTtaMinSpeed(0.75);
                          }}
                          className={`py-1.5 px-2 rounded-lg border text-xs font-semibold transition-all cursor-pointer text-left ${
                            ttaFillMode === 'natural'
                              ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                              : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                          }`}
                        >
                          <div className="font-bold text-[11px]">Natural (Default)</div>
                          <div className="text-[10px] text-slate-500 font-normal">Min 0.75x + pad silence</div>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setTtaFillMode('stretch');
                            setTtaMinSpeed(0.5);
                          }}
                          className={`py-1.5 px-2 rounded-lg border text-xs font-semibold transition-all cursor-pointer text-left ${
                            ttaFillMode === 'stretch'
                              ? 'bg-indigo-50 border-indigo-500 text-indigo-700 ring-1 ring-indigo-500'
                              : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                          }`}
                        >
                          <div className="font-bold text-[11px]">Stretch</div>
                          <div className="text-[10px] text-slate-500 font-normal">Min 0.50x speech fills slot</div>
                        </button>
                      </div>
                    </div>

                    {/* Speed limits */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-medium text-slate-600">Speed Clamping Limits</span>
                        <span className="font-mono font-bold text-indigo-600">{ttaMinSpeed.toFixed(2)}x – {ttaMaxSpeed.toFixed(2)}x</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="bg-white p-2 rounded-lg border border-slate-200">
                          <span className="text-[10px] text-slate-500 font-medium">Min Speed: {ttaMinSpeed.toFixed(2)}x</span>
                          <input
                            type="range"
                            min="0.5"
                            max="1.0"
                            step="0.05"
                            value={ttaMinSpeed}
                            onChange={(e) => setTtaMinSpeed(parseFloat(e.target.value))}
                            className="w-full accent-indigo-600 cursor-pointer mt-1"
                          />
                        </div>
                        <div className="bg-white p-2 rounded-lg border border-slate-200">
                          <span className="text-[10px] text-slate-500 font-medium">Max Speed: {ttaMaxSpeed.toFixed(2)}x</span>
                          <input
                            type="range"
                            min="1.0"
                            max="2.0"
                            step="0.05"
                            value={ttaMaxSpeed}
                            onChange={(e) => setTtaMaxSpeed(parseFloat(e.target.value))}
                            className="w-full accent-indigo-600 cursor-pointer mt-1"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Allow Slow Down */}
                    <label className="flex items-center gap-2 cursor-pointer text-[11px] text-slate-700">
                      <input
                        type="checkbox"
                        checked={ttaAllowSlowDown}
                        onChange={(e) => setTtaAllowSlowDown(e.target.checked)}
                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                      <span>Allow slow-down for short segments</span>
                    </label>

                    {/* Overflow policy */}
                    <div className="space-y-1">
                      <label className="text-[11px] font-medium text-slate-600">Overflow Policy</label>
                      <select
                        value={ttaOverflowPolicy}
                        onChange={(e: any) => setTtaOverflowPolicy(e.target.value)}
                        className="w-full p-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-xs cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      >
                        <option value="allow_overlap">Allow overlap into gap until next cue (default)</option>
                        <option value="truncate_fade">Truncate at slot with 50ms fade-out</option>
                        <option value="fail">Stop and fail on timing overflow</option>
                      </select>
                    </div>
                  </div>
                )}
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
                  <button
                    type="button"
                    onClick={() => setTaskToDelete(activeTask)}
                    className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:bg-rose-50 hover:border-rose-200 text-slate-400 hover:text-rose-600 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                    title="Delete this task"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Delete Task</span>
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
                      onClick={(e) => {
                        const conflictsCount = activeTask.output_media_metadata?.conflicts?.length || 0;
                        if (conflictsCount > 0 && acknowledgedConflictsTaskId !== activeTask.id) {
                          if (!window.confirm(`Speech timing conflicts detected (${conflictsCount} segment(s) overflow window). Do you acknowledge this timing overflow and wish to export anyway?`)) {
                            e.preventDefault();
                          }
                        }
                      }}
                      className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download MP3</span>
                    </a>
                    <a
                      href={api.getToolkitTTSExportUrl(activeTask.id, 'wav')}
                      download={`narration_${activeTask.id.slice(0, 8)}.wav`}
                      onClick={(e) => {
                        const conflictsCount = activeTask.output_media_metadata?.conflicts?.length || 0;
                        if (conflictsCount > 0 && acknowledgedConflictsTaskId !== activeTask.id) {
                          if (!window.confirm(`Speech timing conflicts detected (${conflictsCount} segment(s) overflow window). Do you acknowledge this timing overflow and wish to export anyway?`)) {
                            e.preventDefault();
                          }
                        }
                      }}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download WAV</span>
                    </a>
                    <a
                      href={api.getTaskBundleUrl(activeTask.id)}
                      download={`${activeTask.source_filename || 'narration'}_bundle.zip`}
                      className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs cursor-pointer"
                      title="Download complete ZIP archive"
                    >
                      <Archive className="w-3.5 h-3.5" />
                      <span>Bundle (ZIP)</span>
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
                          Per project architecture, silent truncation is prevented. You may shorten the text, acknowledge the overflow, or switch to Narration Mode.
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

                    {/* Explicit user acknowledgement checkbox per Section 7 */}
                    <div className="p-2.5 rounded-lg bg-white/90 border border-amber-300 flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={`ack-conflicts-${activeTask.id}`}
                        checked={acknowledgedConflictsTaskId === activeTask.id}
                        onChange={(e) => setAcknowledgedConflictsTaskId(e.target.checked ? activeTask.id : null)}
                        className="rounded border-amber-400 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                      <label htmlFor={`ack-conflicts-${activeTask.id}`} className="text-xs font-semibold text-amber-900 cursor-pointer">
                        I acknowledge the {activeTask.output_media_metadata.conflicts.length} timing conflict(s) and authorize export with adjusted duration.
                      </label>
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
                          <div className="flex items-center justify-between text-xs gap-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="px-2 py-0.5 rounded font-mono font-bold bg-slate-100 text-slate-700 text-[11px]">
                                #{seg.segment_order}
                              </span>
                              {seg.start_time !== null && seg.start_time !== undefined && seg.end_time !== null && seg.end_time !== undefined && (
                                <span className="font-mono text-indigo-700 font-semibold text-[11px]">
                                  {formatTimestamp(seg.start_time)} → {formatTimestamp(seg.end_time)}
                                </span>
                              )}
                              {seg.slot_sec !== undefined && seg.slot_sec !== null && (
                                <span className="font-mono text-[11px] text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200">
                                  Slot: {seg.slot_sec.toFixed(2)}s
                                </span>
                              )}
                              {/* Primary FINAL duration */}
                              <span
                                className="font-mono text-xs font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200"
                                title="Final segment duration"
                              >
                                {seg.final_duration_sec !== undefined && seg.final_duration_sec !== null
                                  ? `${seg.final_duration_sec.toFixed(2)}s`
                                  : seg.duration_seconds
                                  ? `${seg.duration_seconds.toFixed(2)}s`
                                  : '--'}
                              </span>
                              {/* Detailed Timing Label: e.g. "1.60s -> 3.00s (0.75x, +0.9s pad)" */}
                              {seg.raw_duration_sec !== undefined && seg.raw_duration_sec !== null && (
                                <span className="font-mono text-[11px] text-indigo-700 font-semibold bg-indigo-50/80 px-2 py-0.5 rounded border border-indigo-200/60">
                                  {seg.raw_duration_sec.toFixed(2)}s → {(seg.final_duration_sec ?? seg.duration_seconds ?? 0).toFixed(2)}s
                                  {seg.speed_factor_applied !== undefined && seg.speed_factor_applied !== null && (
                                    <span className="ml-1 text-slate-600 font-medium">
                                      ({seg.speed_factor_applied.toFixed(2)}x{seg.padded_sec && seg.padded_sec > 0.04 ? `, +${seg.padded_sec.toFixed(1)}s pad` : ''})
                                    </span>
                                  )}
                                </span>
                              )}
                              {seg.method && seg.method !== 'none' && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                                  {seg.method}
                                </span>
                              )}
                              <span
                                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                  seg.status === 'completed' || seg.status === 'fit'
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : seg.status === 'padded'
                                    ? 'bg-sky-50 text-sky-700 border border-sky-200'
                                    : seg.status === 'sped_up'
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : seg.status === 'slowed'
                                    ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                    : seg.status === 'overflow'
                                    ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                    : 'bg-slate-50 text-slate-700 border border-slate-200'
                                }`}
                              >
                                {seg.status}
                              </span>
                            </div>

                            <div className="flex items-center gap-1.5 shrink-0">
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

                              {/* Regenerate with fit individual segment */}
                              <button
                                type="button"
                                onClick={() => handleTtaRegenerateTaskSegment(seg.id, seg.text)}
                                disabled={isRegenerating}
                                className="p-1.5 rounded-lg hover:bg-indigo-50 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer disabled:opacity-40"
                                title="Regenerate with fit"
                              >
                                <RefreshCw className={`w-3.5 h-3.5 ${isRegenerating ? 'animate-spin text-indigo-600' : ''}`} />
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

                          {/* Overflow Warning Banner */}
                          {seg.warning && (
                            <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2.5 flex items-center gap-2">
                              <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
                              <span>{seg.warning}</span>
                            </div>
                          )}

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
                            {cue.emotion_style && (
                              <span className="px-2 py-0.5 rounded text-[10px] bg-amber-50 text-amber-800 font-semibold border border-amber-200">
                                {emotionStyles.find((e) => e.id === cue.emotion_style)?.label_km || cue.emotion_style}
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

                            {/* Voice & Emotion overrides */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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

                              <div>
                                <label className="text-[11px] font-semibold text-slate-600">Acting & Emotion Style</label>
                                <select
                                  value={ttaEditingCueEmotion}
                                  onChange={(e) => setTtaEditingCueEmotion(e.target.value)}
                                  className="w-full mt-1 p-1.5 rounded border border-slate-200 text-slate-800 text-xs font-medium"
                                >
                                  <option value="">-- Use Global Emotion ({ttsEmotionStyle}) --</option>
                                  {emotionStyles.map((emo) => (
                                    <option key={emo.id} value={emo.id}>
                                      {emo.label_km} ({emo.label_en})
                                    </option>
                                  ))}
                                </select>
                              </div>
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
      ) : selectedTool === 'text_translation' ? (
        /* Standalone Translation Studio (Phase 13E.5) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Input Configuration */}
          <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  <Languages className="w-5 h-5 text-indigo-600" />
                  Translation Studio
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Translate plain text or timestamped subtitle transcripts between English & Khmer.
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

            {/* Translation Mode Tabs: Plain Text vs Subtitle Transcript */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                Workflow Mode
              </label>
              <div className="grid grid-cols-2 gap-2 p-1 bg-slate-100 rounded-xl text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => setTransMode('text')}
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                    transMode === 'text'
                      ? 'bg-white text-indigo-700 shadow-sm'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Plain Text</span>
                </button>
                <button
                  type="button"
                  onClick={() => setTransMode('transcript')}
                  className={`py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                    transMode === 'transcript'
                      ? 'bg-white text-indigo-700 shadow-sm'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  <ListMusic className="w-3.5 h-3.5" />
                  <span>Subtitle Transcript</span>
                </button>
              </div>
            </div>

            {/* Language Pair Selector */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                Language Direction
              </label>
              <div className="flex items-center gap-2">
                {transLanguagePairs.length > 0 ? (
                  transLanguagePairs.map((pair) => {
                    const isSelected =
                      transSourceLang === pair.source_lang && transTargetLang === pair.target_lang;
                    return (
                      <button
                        key={`${pair.source_lang}-${pair.target_lang}`}
                        type="button"
                        onClick={() => {
                          setTransSourceLang(pair.source_lang);
                          setTransTargetLang(pair.target_lang);
                        }}
                        className={`flex-1 py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                          isSelected
                            ? 'bg-indigo-50 border-indigo-400 text-indigo-700 shadow-2xs'
                            : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        <span>{pair.source_name} ({pair.source_lang.toUpperCase()})</span>
                        <ArrowRight className="w-3.5 h-3.5 text-indigo-500" />
                        <span>{pair.target_name} ({pair.target_lang.toUpperCase()})</span>
                      </button>
                    );
                  })
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setTransSourceLang('en');
                        setTransTargetLang('km');
                      }}
                      className={`flex-1 py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                        transSourceLang === 'en' && transTargetLang === 'km'
                          ? 'bg-indigo-50 border-indigo-400 text-indigo-700 shadow-2xs'
                          : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                      }`}
                    >
                      <span>English (EN)</span>
                      <ArrowRight className="w-3.5 h-3.5 text-indigo-500" />
                      <span>Khmer (KM)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setTransSourceLang('km');
                        setTransTargetLang('en');
                      }}
                      className={`flex-1 py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer ${
                        transSourceLang === 'km' && transTargetLang === 'en'
                          ? 'bg-indigo-50 border-indigo-400 text-indigo-700 shadow-2xs'
                          : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                      }`}
                    >
                      <span>Khmer (KM)</span>
                      <ArrowRight className="w-3.5 h-3.5 text-indigo-500" />
                      <span>English (EN)</span>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Translation Provider Selector */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                AI Translation Provider
              </label>
              <select
                value={transProvider}
                onChange={(e) => setTransProvider(e.target.value)}
                className="w-full p-2.5 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
              >
                {transProviders.map((p) => {
                  const isUnavailable = p.requires_api_key && !p.is_configured;
                  let badge = '(Cloud Neural)';
                  if (p.type === 'local') {
                    badge = '(Local CPU · Zero Cost)';
                  } else if (isUnavailable) {
                    badge = '(Cloud · API Key Required)';
                  }
                  return (
                    <option key={p.id} value={p.id} disabled={isUnavailable}>
                      {p.name} {badge}
                    </option>
                  );
                })}
              </select>

              {/* Privacy Notice */}
              {transProviders.find((p) => p.id === transProvider)?.type !== 'local' && (
                <div className="p-3 rounded-xl bg-blue-50/80 border border-blue-200 text-xs text-blue-800 flex items-start gap-2">
                  <Info className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                  <div className="leading-relaxed">
                    <span className="font-semibold">Privacy Notice:</span> Selected source text will be transmitted securely to the third-party AI provider ({transProviders.find((p) => p.id === transProvider)?.name}) for neural inference. Do not transmit unmasked credentials or private keys.
                  </div>
                </div>
              )}
            </div>

            {/* Mode Specific Inputs */}
            {transMode === 'text' ? (
              /* Plain Text Input */
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                    Source Text ({transSourceLang.toUpperCase()})
                  </label>
                  <span className="text-[11px] text-slate-400">
                    {transText.length} characters
                  </span>
                </div>
                <textarea
                  rows={7}
                  value={transText}
                  onChange={(e) => setTransText(e.target.value)}
                  placeholder="Paste or type text to translate..."
                  className="w-full p-3.5 rounded-xl border border-slate-200 text-xs text-slate-800 leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 font-normal"
                />
              </div>
            ) : (
              /* Subtitle Transcript Input */
              <div className="space-y-3">
                <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl text-xs font-semibold">
                  <button
                    type="button"
                    onClick={() => setTransInputTab('import')}
                    className={`flex-1 py-1.5 px-2.5 rounded-lg transition-all cursor-pointer ${
                      transInputTab === 'import'
                        ? 'bg-white text-indigo-700 shadow-sm'
                        : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    Import Task
                  </button>
                  <button
                    type="button"
                    onClick={() => setTransInputTab('upload')}
                    className={`flex-1 py-1.5 px-2.5 rounded-lg transition-all cursor-pointer ${
                      transInputTab === 'upload'
                        ? 'bg-white text-indigo-700 shadow-sm'
                        : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    Upload File
                  </button>
                  <button
                    type="button"
                    onClick={() => setTransInputTab('paste')}
                    className={`flex-1 py-1.5 px-2.5 rounded-lg transition-all cursor-pointer ${
                      transInputTab === 'paste'
                        ? 'bg-white text-indigo-700 shadow-sm'
                        : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    Paste Cues
                  </button>
                </div>

                {transInputTab === 'import' ? (
                  <div className="space-y-2">
                    <label className="text-[11px] font-semibold text-slate-600">
                      Select Completed Transcription Task:
                    </label>
                    <select
                      value={transImportTaskId}
                      onChange={(e) => setTransImportTaskId(e.target.value)}
                      className="w-full p-2.5 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                    >
                      <option value="">-- Choose a Completed Task --</option>
                      {tasks
                        .filter((t) => t.status === 'completed' && (t.segments?.length || 0) > 0)
                        .map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.source_filename} ({t.segments?.length || 0} segments · {formatDuration(t.output_duration_seconds)})
                          </option>
                        ))}
                    </select>
                  </div>
                ) : transInputTab === 'upload' ? (
                  <div
                    onClick={() => transFileInputRef.current?.click()}
                    className="p-5 border-2 border-dashed border-slate-200 hover:border-indigo-400 rounded-xl bg-slate-50/50 hover:bg-indigo-50/20 text-center cursor-pointer transition-all space-y-2"
                  >
                    <input
                      type="file"
                      ref={transFileInputRef}
                      onChange={(e) => {
                        if (e.target.files?.[0]) {
                          setTransSelectedFile(e.target.files[0]);
                        }
                      }}
                      accept=".srt,.vtt,.txt"
                      className="hidden"
                    />
                    <Upload className="w-6 h-6 text-indigo-600 mx-auto" />
                    <div className="text-xs font-semibold text-slate-700">
                      {transSelectedFile ? transSelectedFile.name : 'Click to select SRT or WebVTT file'}
                    </div>
                    <p className="text-[11px] text-slate-400">Supports .srt, .vtt subtitle files</p>
                  </div>
                ) : (
                  <textarea
                    rows={7}
                    value={transPastedSrt}
                    onChange={(e) => setTransPastedSrt(e.target.value)}
                    placeholder="1&#10;00:00:01,000 --> 00:00:04,500&#10;Subtitle text here..."
                    className="w-full p-3.5 rounded-xl border border-slate-200 font-mono text-xs text-slate-800 leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  />
                )}
              </div>
            )}

            {/* Submit Translate Button */}
            <button
              type="button"
              onClick={transMode === 'text' ? handleTranslateText : handleTranslateTranscript}
              disabled={transIsTranslating}
              className="w-full py-3.5 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white font-bold text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {transIsTranslating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Translating with AI...</span>
                </>
              ) : (
                <>
                  <Languages className="w-4 h-4" />
                  <span>
                    {transMode === 'text' ? 'Translate Plain Text' : 'Translate Subtitle Transcript'}
                  </span>
                </>
              )}
            </button>
          </div>

          {/* Right Column: Results & Interactive Workspace */}
          <div className="lg:col-span-7 space-y-6">
            {activeTask && activeTask.status === 'completed' && activeTask.translation_segments ? (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
                {/* Header Summary */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                      <h4 className="font-bold text-slate-900 text-base">
                        {activeTask.source_filename}
                      </h4>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 uppercase">
                        {activeTask.tool_type === 'transcript_translation' ? 'Transcript Translation' : 'Text Translation'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      <span>{activeTask.translation_segments.length} segments</span>
                      <span>•</span>
                      <span>Format: {activeTask.target_format.toUpperCase()}</span>
                      {activeTask.is_outdated && (
                        <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 font-semibold border border-amber-200">
                          Outdated
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleCopyText(
                        activeTask.translation_segments
                          ?.map((s) => s.edited_text || s.translated_text)
                          .join('\n\n') || ''
                      )}
                      className="px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      {copiedFullText ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedFullText ? 'Copied' : 'Copy All'}</span>
                    </button>
                  </div>
                </div>

                {/* Outdated Upstream Banner */}
                {activeTask.is_outdated && (
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                    <div className="space-y-1 text-xs text-amber-900">
                      <h5 className="font-bold">Source Transcript Was Edited</h5>
                      <p className="leading-relaxed">
                        The upstream transcript segments have changed since this translation was generated. Your current translation edits are preserved. You can re-translate when ready.
                      </p>
                    </div>
                  </div>
                )}

                {/* Connected Workflows Actions & Export Bar */}
                <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-100 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2 font-semibold text-indigo-900">
                    <Sparkles className="w-4 h-4 text-indigo-600" />
                    <span>Connected Workflows:</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {activeTask.tool_type === 'text_translation' ? (
                      <button
                        type="button"
                        onClick={() => handleSendTranslationToTTS(activeTask)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                        title="Send translated text directly to Text-to-Speech Studio"
                      >
                        <Mic2 className="w-3.5 h-3.5" />
                        <span>Send to Text-to-Speech</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleSendTranslationToTranscriptToAudio(activeTask)}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                        title="Send timestamped translated transcript to Transcript-to-Audio Studio"
                      >
                        <Radio className="w-3.5 h-3.5" />
                        <span>Send to Transcript-to-Audio</span>
                      </button>
                    )}

                    {/* Export formats */}
                    {['srt', 'vtt', 'txt', 'csv', 'json'].map((fmt) => (
                      <a
                        key={fmt}
                        href={api.getToolkitExportUrl(activeTask.id, fmt)}
                        download
                        className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-200 hover:border-indigo-400 hover:text-indigo-600 font-semibold text-slate-700 shadow-2xs transition-all uppercase text-[11px] cursor-pointer"
                      >
                        {fmt}
                      </a>
                    ))}

                    <a
                      href={api.getTaskBundleUrl(activeTask.id)}
                      download={`${activeTask.source_filename || 'task'}_bundle.zip`}
                      className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                      title="Download complete ZIP archive with original transcripts, translations, and audio"
                    >
                      <Archive className="w-3.5 h-3.5" />
                      <span>Download All (ZIP)</span>
                    </a>
                  </div>
                </div>

                {/* Segments Cards List */}
                <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                  {activeTask.translation_segments.map((seg) => {
                    const isEditing = transEditingSegId === seg.id;
                    const isRetrying = transRetryingSegId === seg.id;

                    return (
                      <div
                        key={seg.id}
                        className="p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all space-y-3 shadow-xs"
                      >
                        {/* Header: Segment badge, timestamps, overflow risk */}
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
                            {seg.is_overflow_risk && (
                              <span
                                className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1"
                                title="Speech estimated to exceed the available time window."
                              >
                                <AlertTriangle className="w-3 h-3 text-amber-600" />
                                Duration Overflow (~{seg.estimated_duration_seconds}s)
                              </span>
                            )}
                            {seg.is_edited && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700">
                                Edited
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-1">
                            {!isEditing && (
                              <button
                                type="button"
                                onClick={() => {
                                  setTransEditingSegId(seg.id);
                                  setTransEditingSegText(seg.edited_text || seg.translated_text);
                                }}
                                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                title="Edit Translation"
                              >
                                <Edit2 className="w-3.5 h-3.5" />
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => handleRetryTranslationSegment(seg.id)}
                              disabled={isRetrying}
                              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer disabled:opacity-50"
                              title="Re-translate segment"
                            >
                              <RefreshCw className={`w-3.5 h-3.5 ${isRetrying ? 'animate-spin text-indigo-600' : ''}`} />
                            </button>

                            <button
                              type="button"
                              onClick={() => handleCopyText(seg.edited_text || seg.translated_text, seg.id)}
                              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                              title="Copy translated text"
                            >
                              {copiedSegmentId === seg.id ? (
                                <Check className="w-3.5 h-3.5 text-emerald-600" />
                              ) : (
                                <Copy className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Source Text Box */}
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-slate-600 text-xs leading-relaxed">
                          <span className="text-[10px] font-bold text-slate-400 block mb-1 uppercase tracking-wider">
                            Source ({transSourceLang.toUpperCase()})
                          </span>
                          {seg.source_text}
                        </div>

                        {/* Translated Text or Edit Area */}
                        {isEditing ? (
                          <div className="space-y-2">
                            <label className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider block">
                              Edit Translation ({transTargetLang.toUpperCase()})
                            </label>
                            <textarea
                              rows={3}
                              value={transEditingSegText}
                              onChange={(e) => setTransEditingSegText(e.target.value)}
                              className="w-full p-2.5 rounded-lg border border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 text-xs text-slate-800 leading-relaxed"
                            />
                            <div className="flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => setTransEditingSegId(null)}
                                className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold cursor-pointer"
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSaveTranslationSegment(seg.id)}
                                className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1 cursor-pointer"
                              >
                                <Save className="w-3.5 h-3.5" />
                                <span>Save Edit</span>
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="text-slate-900 text-sm font-medium leading-relaxed pl-1">
                            {seg.edited_text || seg.translated_text}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              /* Empty State */
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-12 text-center text-slate-400 space-y-4">
                <Languages className="w-14 h-14 text-slate-300 mx-auto" />
                <div className="space-y-1">
                  <h4 className="font-semibold text-slate-700 text-base">Translation Studio Ready</h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Translate between English and Khmer using local NLLB-200 or cloud models with strict timestamp preservation and duration overflow alerts.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-3 max-w-sm mx-auto text-left text-[11px] text-slate-500 pt-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>English & Khmer Verified</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Preserves Cue Timestamps</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Direct Handoff to Speech</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>Full ZIP Bundle Export</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : selectedTool === 'subtitle_conversion' ? (
        /* Subtitle Converter (Phase 13E.5) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Conversion Controls */}
          <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  <Layers className="w-5 h-5 text-indigo-600" />
                  Subtitle Converter
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Convert subtitle cues between SubRip (.srt) and WebVTT (.vtt) while strictly preserving timing.
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

            {/* Source & Target Formats */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                  Source Format
                </label>
                <select
                  value={convSourceFormat}
                  onChange={(e) => setConvSourceFormat(e.target.value)}
                  className="w-full p-2.5 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                >
                  <option value="srt">SubRip (.srt)</option>
                  <option value="vtt">WebVTT (.vtt)</option>
                  <option value="txt">Plain Text (.txt)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                  Target Format
                </label>
                <select
                  value={convTargetFormat}
                  onChange={(e) => setConvTargetFormat(e.target.value)}
                  className="w-full p-2.5 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                >
                  <option value="vtt">WebVTT (.vtt)</option>
                  <option value="srt">SubRip (.srt)</option>
                  <option value="txt">Plain Text (.txt)</option>
                </select>
              </div>
            </div>

            {/* Subtitle Input Textarea */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Subtitle Content
                </label>
                <button
                  type="button"
                  onClick={() => convFileInputRef.current?.click()}
                  className="text-xs text-indigo-600 hover:text-indigo-700 font-semibold flex items-center gap-1 cursor-pointer"
                >
                  <Upload className="w-3 h-3" />
                  <span>Upload File</span>
                </button>
                <input
                  type="file"
                  ref={convFileInputRef}
                  onChange={async (e) => {
                    if (e.target.files?.[0]) {
                      const text = await e.target.files[0].text();
                      setConvContent(text);
                    }
                  }}
                  accept=".srt,.vtt,.txt"
                  className="hidden"
                />
              </div>
              <textarea
                rows={9}
                value={convContent}
                onChange={(e) => setConvContent(e.target.value)}
                placeholder="Paste subtitle content here..."
                className="w-full p-3 rounded-xl border border-slate-200 font-mono text-xs text-slate-800 leading-relaxed focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              />
            </div>

            <button
              type="button"
              onClick={handleConvertSubtitle}
              disabled={convIsConverting}
              className="w-full py-3.5 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white font-bold text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
            >
              {convIsConverting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Converting Subtitles...</span>
                </>
              ) : (
                <>
                  <Layers className="w-4 h-4" />
                  <span>Convert to {convTargetFormat.toUpperCase()}</span>
                </>
              )}
            </button>
          </div>

          {/* Right Column: Converted Output Preview */}
          <div className="lg:col-span-6 space-y-6">
            {convResult ? (
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      <h4 className="font-bold text-slate-900 text-sm">Converted Successfully</h4>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 uppercase">
                        {convResult.target_format}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">
                      {convResult.segment_count} cues processed with full timing fidelity
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(convResult.content);
                        setConvCopied(true);
                        setTimeout(() => setConvCopied(false), 2000);
                      }}
                      className="px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      {convCopied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{convCopied ? 'Copied' : 'Copy'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        const blob = new Blob([convResult.content], { type: 'text/plain;charset=utf-8' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = convResult.filename;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download</span>
                    </button>
                  </div>
                </div>

                <textarea
                  readOnly
                  rows={13}
                  value={convResult.content}
                  className="w-full p-3 rounded-xl border border-slate-200 bg-slate-50 font-mono text-xs text-slate-800 leading-relaxed focus:outline-none"
                />
              </div>
            ) : (
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-12 text-center text-slate-400 space-y-3">
                <Layers className="w-12 h-12 text-slate-300 mx-auto" />
                <h4 className="font-semibold text-slate-700 text-sm">No Converted Output Yet</h4>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  Paste subtitle cues or upload an SRT or WebVTT file and click Convert to generate the converted output with precise timestamp formatting.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : selectedTool === 'video_downloader' ? (
        /* Video Downloader Studio (Phase 13F) */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Input URL, Inspection & Download Controls */}
          <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-6">
            <div className="border-b border-slate-100 pb-4">
              <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                <Download className="w-5 h-5 text-indigo-600" />
                Video Downloader & URL Media Import
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Download permitted videos from supported links and import them into KhmerDub AI.
              </p>
            </div>

            {error && (
              <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <span className="font-semibold">Error:</span> {error}
                </div>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="text-rose-400 hover:text-rose-700 text-xs"
                >
                  ✕
                </button>
              </div>
            )}

            {/* URL Input Form */}
            <form onSubmit={handleInspectUrl} className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                <span>Video or Media Link</span>
                <span className="text-[11px] font-normal text-slate-400">YouTube, TikTok, Direct MP4/Audio</span>
              </label>

              <div className="flex gap-2">
                <input
                  type="url"
                  value={downloaderUrl}
                  onChange={(e) => setDownloaderUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=... or https://.../video.mp4"
                  className="flex-1 p-2.5 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  disabled={downloaderInspecting || downloaderStarting || !!downloaderActiveTaskId}
                />
                <button
                  type="submit"
                  disabled={!downloaderUrl.trim() || downloaderInspecting || downloaderStarting || !!downloaderActiveTaskId}
                  className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold transition shadow-xs flex items-center gap-1.5 cursor-pointer disabled:cursor-not-allowed shrink-0"
                >
                  {downloaderInspecting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Inspecting...</span>
                    </>
                  ) : (
                    <>
                      <Search className="w-3.5 h-3.5" />
                      <span>Fetch Info</span>
                    </>
                  )}
                </button>
              </div>

              {/* Supported Platforms Hints */}
              <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[11px] text-slate-500">
                <span className="font-medium text-slate-600">Supported:</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">YouTube</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Shorts</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">TikTok</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Facebook</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Instagram</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">X / Twitter</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Vimeo</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Dailymotion</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Reddit</span>
                <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">Direct Media</span>
              </div>
            </form>

            {/* Metadata Preview Card (when metadata fetched) */}
            {downloaderMeta && (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                <div className="flex gap-3 items-start">
                  {downloaderMeta.thumbnail_url ? (
                    <img
                      src={downloaderMeta.thumbnail_url}
                      alt={downloaderMeta.title}
                      className="w-24 h-16 object-cover rounded-lg bg-black shrink-0 border border-slate-200"
                    />
                  ) : (
                    <div className="w-24 h-16 rounded-lg bg-slate-200 flex items-center justify-center shrink-0 text-slate-400">
                      <Film className="w-6 h-6" />
                    </div>
                  )}

                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-700">
                        {downloaderMeta.source_platform}
                      </span>
                      {downloaderMeta.duration_seconds ? (
                        <span className="text-[11px] text-slate-500 flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-400" />
                          {formatDuration(downloaderMeta.duration_seconds)}
                        </span>
                      ) : null}
                    </div>

                    <h4 className="font-bold text-slate-900 text-xs sm:text-sm line-clamp-2" title={downloaderMeta.title}>
                      {downloaderMeta.title}
                    </h4>

                    <div className="text-[11px] text-slate-500 flex items-center gap-2">
                      <span>By: {downloaderMeta.uploader || 'Creator'}</span>
                      {downloaderMeta.estimated_file_size_bytes ? (
                        <>
                          <span>•</span>
                          <span>~{formatBytes(downloaderMeta.estimated_file_size_bytes)}</span>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>

                {/* Configuration: Output Type & Quality */}
                <div className="pt-3 border-t border-slate-200/80 space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setDownloaderOutputType('video')}
                      disabled={downloaderMeta.is_audio_only_source}
                      className={`py-2 px-3 rounded-xl text-xs font-bold transition cursor-pointer flex items-center justify-center gap-1.5 ${
                        downloaderOutputType === 'video'
                          ? 'bg-indigo-600 text-white shadow-xs'
                          : 'bg-white border border-slate-200 text-slate-600 hover:text-slate-900'
                      } ${downloaderMeta.is_audio_only_source ? 'opacity-40 cursor-not-allowed' : ''}`}
                    >
                      <Film className="w-3.5 h-3.5" />
                      <span>Video (MP4)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDownloaderOutputType('audio')}
                      className={`py-2 px-3 rounded-xl text-xs font-bold transition cursor-pointer flex items-center justify-center gap-1.5 ${
                        downloaderOutputType === 'audio'
                          ? 'bg-indigo-600 text-white shadow-xs'
                          : 'bg-white border border-slate-200 text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <Volume2 className="w-3.5 h-3.5" />
                      <span>Audio Only</span>
                    </button>
                  </div>

                  {downloaderOutputType === 'video' ? (
                    <div className="space-y-1">
                      <label className="text-[11px] font-semibold text-slate-600 block">
                        Video Quality / Resolution
                      </label>
                      <select
                        value={downloaderQuality}
                        onChange={(e) => setDownloaderQuality(e.target.value)}
                        className="w-full p-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                      >
                        {downloaderMeta.available_video_qualities.map((q) => (
                          <option key={q} value={q}>
                            {q === 'best' ? 'Best Available Resolution' : `${q} Resolution`}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <label className="text-[11px] font-semibold text-slate-600 block">
                        Output Audio Format
                      </label>
                      <select
                        value={downloaderAudioFormat}
                        onChange={(e) => setDownloaderAudioFormat(e.target.value)}
                        className="w-full p-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                      >
                        <option value="mp3">MP3 (High Quality 192k)</option>
                        <option value="m4a">M4A (AAC Audio)</option>
                        <option value="wav">WAV (Lossless 44.1kHz)</option>
                      </select>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Informational Rights & Availability Notice */}
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/90 flex items-start gap-2.5 text-xs text-slate-600">
              <ShieldCheck className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
              <p className="leading-relaxed text-[11px] text-slate-500">
                Only download media you have the right to use. Availability depends on the source website and applicable restrictions.
              </p>
            </div>

            {/* Action Buttons */}
            {downloaderActiveTaskId ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-600">
                  <span className="font-semibold flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                    Downloading Media...
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCancelDownload(downloaderActiveTaskId)}
                    disabled={downloaderCancelling}
                    className="px-3 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 font-semibold text-xs border border-rose-200 transition cursor-pointer"
                  >
                    {downloaderCancelling ? 'Cancelling...' : 'Cancel Download'}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleStartDownload}
                disabled={!downloaderMeta || downloaderStarting}
                className="w-full py-3.5 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white font-bold text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
              >
                {downloaderStarting ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Queuing Download...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    <span>Start Download</span>
                  </>
                )}
              </button>
            )}
          </div>

          {/* Right Column: Download Progress, Preview & Downstream Actions */}
          <div className="lg:col-span-6 space-y-6">
            {downloaderActiveTaskId && downloaderActiveTask ? (
              /* In-Progress View */
              <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-5">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h4 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-indigo-600 animate-spin" />
                    <span>Download in Progress</span>
                  </h4>
                  <span className="text-xs font-bold text-indigo-600">
                    {downloaderActiveTask.progress_percentage}%
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden">
                    <div
                      className="bg-indigo-600 h-full rounded-full transition-all duration-300"
                      style={{ width: `${downloaderActiveTask.progress_percentage}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span>
                      {downloaderActiveTask.source_media_metadata?.stage === 'downloading'
                        ? 'Transferring media stream...'
                        : downloaderActiveTask.source_media_metadata?.stage === 'transcoding'
                        ? 'Optimizing container with FFmpeg...'
                        : 'Connecting to media server...'}
                    </span>
                    {downloaderActiveTask.source_media_metadata?.speed_bytes_per_sec ? (
                      <span>{formatBytes(downloaderActiveTask.source_media_metadata.speed_bytes_per_sec)}/s</span>
                    ) : null}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1 text-xs text-slate-600">
                  <div className="font-semibold text-slate-800 truncate">
                    {downloaderActiveTask.source_filename}
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Task ID: {downloaderActiveTask.id.slice(0, 8)}...
                  </div>
                </div>
              </div>
            ) : (downloaderActiveTask && downloaderActiveTask.status === 'completed') || (activeTask && activeTask.tool_type === 'video_downloader' && activeTask.status === 'completed') ? (
              /* Completed Download View */
              (() => {
                const completedTask = (downloaderActiveTask && downloaderActiveTask.status === 'completed')
                  ? downloaderActiveTask
                  : activeTask!;
                const isVideo = completedTask.target_format === 'mp4' || completedTask.output_filename?.endsWith('.mp4');

                return (
                  <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-5">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        <h4 className="font-bold text-slate-900 text-sm">Media Ready</h4>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 uppercase">
                          {completedTask.target_format}
                        </span>
                      </div>

                      <a
                        href={api.getToolkitAudioDownloadUrl(completedTask.id)}
                        className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs cursor-pointer"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>Download</span>
                      </a>
                    </div>

                    {/* Media Player Preview */}
                    <div className="rounded-xl overflow-hidden bg-black aspect-video flex items-center justify-center">
                      {isVideo ? (
                        <video
                          controls
                          src={api.getToolkitAudioStreamUrl(completedTask.id)}
                          className="w-full h-full object-contain"
                        />
                      ) : (
                        <div className="p-6 w-full text-center space-y-3">
                          <Volume2 className="w-12 h-12 text-slate-400 mx-auto" />
                          <audio
                            controls
                            src={api.getToolkitAudioStreamUrl(completedTask.id)}
                            className="w-full"
                          />
                        </div>
                      )}
                    </div>

                    {/* Media Details */}
                    <div className="grid grid-cols-3 gap-2.5 text-center text-xs">
                      <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                        <span className="text-[10px] text-slate-400 block uppercase">Duration</span>
                        <span className="font-bold text-slate-800">
                          {formatDuration(completedTask.output_duration_seconds)}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                        <span className="text-[10px] text-slate-400 block uppercase">File Size</span>
                        <span className="font-bold text-slate-800">
                          {formatBytes(completedTask.output_file_size_bytes)}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                        <span className="text-[10px] text-slate-400 block uppercase">Container</span>
                        <span className="font-bold text-slate-800 uppercase">
                          {completedTask.target_format}
                        </span>
                      </div>
                    </div>

                    {/* Downstream Actions / Handoffs */}
                    <div className="pt-3 border-t border-slate-100 space-y-2.5">
                      <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                        Import & Connected Workflows
                      </label>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        {isVideo && (
                          <button
                            type="button"
                            onClick={() => handleImportToDubbing(completedTask.id)}
                            disabled={downloaderImporting}
                            className="py-2.5 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
                          >
                            {downloaderImporting ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <ExternalLink className="w-3.5 h-3.5" />
                            )}
                            <span>Import to Video Dubbing</span>
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => handleHandoffDownloader(completedTask.id, 'video_to_audio')}
                          disabled={!!downloaderHandoffLoading}
                          className="py-2.5 px-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
                        >
                          <FileAudio className="w-3.5 h-3.5 text-indigo-600" />
                          <span>Extract Audio</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleHandoffDownloader(completedTask.id, 'video_to_transcript')}
                          disabled={!!downloaderHandoffLoading}
                          className="py-2.5 px-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
                        >
                          <FileText className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Transcribe Video</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => handleHandoffDownloader(completedTask.id, 'video_to_text')}
                          disabled={!!downloaderHandoffLoading}
                          className="py-2.5 px-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
                        >
                          <AlignLeft className="w-3.5 h-3.5 text-purple-600" />
                          <span>Convert to Text</span>
                        </button>

                        {isVideo ? (
                          <button
                            type="button"
                            onClick={() => handleHandoffDownloader(completedTask.id, 'video_trimmer')}
                            disabled={!!downloaderHandoffLoading}
                            className="py-2.5 px-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
                          >
                            <Scissors className="w-3.5 h-3.5 text-indigo-600" />
                            <span>Trim Video</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleHandoffDownloader(completedTask.id, 'audio_trimmer')}
                            disabled={!!downloaderHandoffLoading}
                            className="py-2.5 px-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 text-xs font-semibold transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer"
                          >
                            <Scissors className="w-3.5 h-3.5 text-indigo-600" />
                            <span>Trim Audio</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })()
            ) : (downloaderActiveTask && (downloaderActiveTask.status === 'failed' || downloaderActiveTask.status === 'cancelled')) || (activeTask && activeTask.tool_type === 'video_downloader' && (activeTask.status === 'failed' || activeTask.status === 'cancelled')) ? (
              /* Failed / Cancelled View */
              (() => {
                const failedTask = (downloaderActiveTask && (downloaderActiveTask.status === 'failed' || downloaderActiveTask.status === 'cancelled'))
                  ? downloaderActiveTask
                  : activeTask!;
                const isCancelled = failedTask.status === 'cancelled';

                return (
                  <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-7 space-y-4">
                    <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                      <AlertCircle className={`w-5 h-5 ${isCancelled ? 'text-amber-500' : 'text-rose-500'}`} />
                      <h4 className="font-bold text-slate-900 text-sm">
                        {isCancelled ? 'Download Cancelled' : 'Download Failed'}
                      </h4>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        isCancelled ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}>
                        {failedTask.status}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1.5">
                      <div className="font-semibold text-slate-800">
                        {failedTask.source_filename}
                      </div>
                      <p className="text-slate-600">
                        {failedTask.error_message || (isCancelled ? 'This download was cancelled by the user.' : 'The download operation encountered an error.')}
                      </p>
                    </div>

                    <div className="text-[11px] text-slate-500">
                      {isCancelled ? (
                        <span>No partial files or temporary data were preserved on the server.</span>
                      ) : (
                        <span>Tip: Verify that the source video is public, permitted, and within the 500 MB limit. For YouTube videos requiring login or bot checks, downloading is restricted.</span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        setDownloaderActiveTaskId(null);
                        setDownloaderActiveTask(null);
                        setActiveTask(null);
                      }}
                      className="w-full py-2.5 px-4 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs transition cursor-pointer"
                    >
                      Clear & Try Another URL
                    </button>
                  </div>
                );
              })()
            ) : (
              /* Idle Placeholder */
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-12 text-center text-slate-400 space-y-3">
                <Download className="w-12 h-12 text-slate-300 mx-auto" />
                <h4 className="font-semibold text-slate-700 text-sm">No Downloaded Media Yet</h4>
                <p className="text-xs text-slate-400 max-w-sm mx-auto">
                  Paste a video link on the left, fetch information, and start download. You can then preview the video, download it, or import it directly into Video Dubbing.
                </p>
              </div>
            )}
          </div>
        </div>
      ) : selectedTool === 'transcript_to_text' ? (
        <TranscriptToText
          tasks={tasks}
          initialTask={activeTask?.tool_type === 'transcript_to_text' ? activeTask : null}
          onTaskCreated={(task) => {
            setActiveTask(task);
            fetchTasks();
          }}
          onSendToTTS={(text) => {
            setTtsText(text);
            navigateToTool('text_to_speech');
          }}
          onSendToTranslation={(text) => {
            setTransText(text);
            setTransMode('text');
            navigateToTool('text_translation');
          }}
          onSendToTranscriptToAudio={(taskId) => {
            const task = tasks.find((t) => t.id === taskId);
            if (task) {
              handleSendToTranscriptToAudio(task);
            }
          }}
          onNavigateToTool={(toolId) => navigateToTool(toolId)}
        />
      ) : selectedTool === 'audio_cleaning' ? (
        <AudioCleaning projects={projects} initialTask={activeTask}
          onTaskUpdate={(task) => { setActiveTask(task); if (!['pending', 'processing', 'cancelling'].includes(task.status)) fetchTasks(); }} />
      ) : selectedTool === 'video_trimmer' ? (
        <VideoTrimmer
          tasks={tasks}
          projects={projects}
          onTaskCompleted={() => {
            fetchTasks();
          }}
          onNavigateToTool={(toolId) => navigateToTool(toolId)}
          initialSourceTaskId={activeTask?.id || undefined}
        />
      ) : selectedTool === 'audio_trimmer' ? (
        <AudioTrimmer
          tasks={tasks}
          projects={projects}
          onTaskCompleted={() => {
            fetchTasks();
          }}
          onNavigateToTool={(toolId) => navigateToTool(toolId)}
          initialSourceTaskId={activeTask?.id || undefined}
        />
      ) : null}
        </div>
      )}

      {/* ======================================================== */}
      {/* VIEW 3: FULL TASK HISTORY (viewMode === 'history')        */}
      {/* ======================================================== */}
      {viewMode === 'history' && (
        <div className="space-y-6">
          {/* Breadcrumb Navigation Bar */}
          <div className="flex items-center justify-between bg-white border border-slate-200/90 rounded-2xl px-5 py-3.5 shadow-xs">
            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={navigateToOverview}
                className="inline-flex items-center gap-1.5 font-bold text-slate-700 hover:text-indigo-600 transition-colors cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>All Tools</span>
              </button>
              <span className="text-slate-300">/</span>
              <button
                type="button"
                onClick={navigateToOverview}
                className="text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
              >
                Media Toolkit
              </button>
              <span className="text-slate-300">/</span>
              <span className="font-semibold text-slate-900">Task History</span>
            </div>
          </div>

          {/* History Header & Summary Cards */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
              <div>
                <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2.5">
                  <History className="w-6 h-6 text-indigo-600" />
                  Media Toolkit Task History
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Persistent log of all extraction, speech synthesis, transcription, and translation operations.
                </p>
              </div>

              <div className="flex items-center gap-2 self-start sm:self-auto">
                <button
                  type="button"
                  onClick={fetchTasks}
                  disabled={tasksLoading}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${tasksLoading ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>
              </div>
            </div>

            {/* Quick Stat Badges */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
                <div className="text-slate-400 font-medium">Total Tasks</div>
                <div className="text-xl font-bold text-slate-900 mt-0.5">{tasks.length}</div>
              </div>
              <div className="p-3.5 rounded-xl bg-emerald-50/60 border border-emerald-200/80">
                <div className="text-emerald-700 font-medium">Completed</div>
                <div className="text-xl font-bold text-emerald-800 mt-0.5">
                  {tasks.filter((t) => t.status === 'completed').length}
                </div>
              </div>
              <div className="p-3.5 rounded-xl bg-indigo-50/60 border border-indigo-200/80">
                <div className="text-indigo-700 font-medium">Processing</div>
                <div className="text-xl font-bold text-indigo-800 mt-0.5">
                  {tasks.filter((t) => t.status === 'processing').length}
                </div>
              </div>
              <div className="p-3.5 rounded-xl bg-rose-50/60 border border-rose-200/80">
                <div className="text-rose-700 font-medium">Failed</div>
                <div className="text-xl font-bold text-rose-800 mt-0.5">
                  {tasks.filter((t) => t.status === 'failed').length}
                </div>
              </div>
            </div>

            {/* Filter & Search Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 pt-2">
              {/* Search input */}
              <div className="sm:col-span-5 relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  placeholder="Search by filename, format, or task ID..."
                  className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                />
              </div>

              {/* Tool Type Filter */}
              <div className="sm:col-span-3">
                <select
                  value={historyToolFilter}
                  onChange={(e) => setHistoryToolFilter(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                >
                  <option value="all">All Tool Types</option>
                  <option value="audio_cleaning">Audio Noise &amp; Music Remover</option>
                  <option value="video_downloader">Video Downloader</option>
                  <option value="video_to_audio">Video to Audio</option>
                  <option value="video_to_transcript">Video to Transcript</option>
                  <option value="video_to_text">Video to Text</option>
                  <option value="audio_to_transcript">Audio to Transcript</option>
                  <option value="audio_to_text">Audio to Text</option>
                  <option value="text_to_speech">Text to Speech</option>
                  <option value="transcript_to_audio">Transcript to Audio</option>
                  <option value="text_translation">Translation Studio</option>
                  <option value="subtitle_conversion">Subtitle Converter</option>
                  <option value="video_trimmer">Video Trimmer</option>
                  <option value="audio_trimmer">Audio Trimmer</option>
                </select>
              </div>

              {/* Status Filter */}
              <div className="sm:col-span-2">
                <select
                  value={historyStatusFilter}
                  onChange={(e) => setHistoryStatusFilter(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 cursor-pointer"
                >
                  <option value="all">All Statuses</option>
                  <option value="completed">Completed</option>
                  <option value="processing">Processing</option>
                  <option value="failed">Failed</option>
                  <option value="pending">Queued</option>
                  <option value="cancelling">Cancelling</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>

              {/* Sort Order */}
              <div className="sm:col-span-2">
                <button
                  type="button"
                  onClick={() => setHistorySortOrder(historySortOrder === 'desc' ? 'asc' : 'desc')}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700 flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                >
                  {historySortOrder === 'desc' ? (
                    <>
                      <ArrowDown className="w-3.5 h-3.5 text-indigo-600" />
                      <span>Newest First</span>
                    </>
                  ) : (
                    <>
                      <ArrowUp className="w-3.5 h-3.5 text-indigo-600" />
                      <span>Oldest First</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Table */}
            {filteredTasks.length === 0 ? (
              <div className="text-center py-12 text-slate-400 text-xs space-y-2">
                <p>No tasks match the selected criteria.</p>
                {(historySearch || historyToolFilter !== 'all' || historyStatusFilter !== 'all') && (
                  <button
                    type="button"
                    onClick={() => {
                      setHistorySearch('');
                      setHistoryToolFilter('all');
                      setHistoryStatusFilter('all');
                    }}
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 underline cursor-pointer"
                  >
                    Reset Filters
                  </button>
                )}
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
                    {filteredTasks.map((task) => (
                      <tr
                        key={task.id}
                        onClick={() => handleSelectTask(task)}
                        className={`hover:bg-slate-50/70 transition-colors cursor-pointer ${
                          activeTask?.id === task.id ? 'bg-indigo-50/30' : ''
                        }`}
                      >
                        <td className="py-3 px-3 text-slate-400 whitespace-nowrap">
                          {formatCambodiaDateTime(task.created_at)}
                        </td>
                        <td className="py-3 px-3 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                            {getToolTitle(task.tool_type)}
                          </span>
                        </td>
                        <td className="py-3 px-3 font-medium text-slate-900 max-w-[200px] truncate" title={task.source_filename}>
                          <div className="flex items-center gap-1.5">
                            <span className="truncate">{task.source_filename}</span>
                            {task.is_outdated && (
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-50 text-amber-700 border border-amber-200 shrink-0">
                                Outdated
                              </span>
                            )}
                          </div>
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
                          {['pending', 'cancelling', 'cancelled'].includes(task.status) && (
                            <span className="text-slate-600 font-medium capitalize">{task.status === 'pending' ? 'Queued' : task.status}</span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => handleOpenTaskInWorkspace(task)}
                              className="px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold inline-flex items-center gap-1 transition-colors cursor-pointer mr-1"
                              title="Open task in workspace"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                              <span>Open Task</span>
                            </button>

                            {task.status === 'completed' && (
                              <>
                                {(task.tool_type === 'video_to_audio' || task.tool_type === 'text_to_speech' || task.tool_type === 'transcript_to_audio' || task.tool_type === 'audio_trimmer') && (
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

                                <a
                                  href={api.getTaskBundleUrl(task.id)}
                                  download={`${task.source_filename || 'task'}_bundle.zip`}
                                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-indigo-600 transition-colors cursor-pointer"
                                  title="Download All (ZIP Bundle)"
                                >
                                  <Archive className="w-4 h-4" />
                                </a>
                              </>
                            )}

                            <button
                              onClick={() => handleDeleteTask(task)}
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
      )}

      {/* Global Status / Notification Message */}
      {statusMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between shadow-xs animate-in fade-in duration-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{statusMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setStatusMessage('')}
            className="text-emerald-600 hover:text-emerald-800 cursor-pointer p-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Delete Confirmation Modal for Toolkit Task / Project */}
      <DeleteToolkitTaskModal
        isOpen={!!taskToDelete}
        task={taskToDelete}
        dependentCount={taskDependentCount}
        loading={isDeletingTask}
        onClose={() => setTaskToDelete(null)}
        onConfirm={handleConfirmDeleteTask}
      />
    </div>
  );
};

export default MediaToolkit;
