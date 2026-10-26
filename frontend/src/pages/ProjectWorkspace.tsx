import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  StudioHeader,
  StudioTab,
} from '../components/studio/StudioHeader';
import { PersistentVideoPlayer, VideoPlayerRef } from '../components/studio/PersistentVideoPlayer';
import { DubbingTimeline } from '../components/studio/DubbingTimeline';
import { MediaTab } from '../components/studio/MediaTab';
import { TranscriptTab } from '../components/studio/TranscriptTab';
import { TranslationTab } from '../components/studio/TranslationTab';
import { SubtitleTab } from '../components/studio/SubtitleTab';
import { VoiceTab } from '../components/studio/VoiceTab';
import { ExportTab } from '../components/studio/ExportTab';
import { AIImproveModal } from '../components/studio/AIImproveModal';
import { RenameProjectModal } from '../components/common/RenameProjectModal';
import { api } from '../services/api';
import {
  ProjectDetail,
  TranscriptSegment,
  TranslationSegment,
  GeneratedAudio,
  TimingConflict,
  ExportStatusResponse,
  VoiceOption,
  TranslationProviderInfo,
  SubtitleSegment,
  SubtitleStylePreferences,
} from '../types';

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
  // Project detail
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<StudioTab>('media');

  // Segments and data
  const [transcriptSegments, setTranscriptSegments] = useState<TranscriptSegment[]>([]);
  const [segmentationMode, setSegmentationMode] = useState<string>('sentence');
  const [translationSegments, setTranslationSegments] = useState<TranslationSegment[]>([]);
  const [generatedAudios, setGeneratedAudios] = useState<GeneratedAudio[]>([]);
  const [timingConflicts, setTimingConflicts] = useState<TimingConflict[]>([]);
  const [exportStatus, setExportStatus] = useState<ExportStatusResponse | null>(null);

  // Providers & voices catalog
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [translationProviders, setTranslationProviders] = useState<TranslationProviderInfo[]>([]);

  // Selection state
  const [selectedVoice, setSelectedVoice] = useState<{ provider: string; voice: string }>({
    provider: 'gtts',
    voice: 'default',
  });
  const [selectedTransProvider, setSelectedTransProvider] = useState<string>('nllb');
  const [selectedTransStyle, setSelectedTransStyle] = useState<string>('natural');

  // Job states
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);
  const [isTranslating, setIsTranslating] = useState<boolean>(false);
  const [isGeneratingVoice, setIsGeneratingVoice] = useState<boolean>(false);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  // Errors
  const [transcriptionError, setTranscriptionError] = useState<string | null>(null);
  const [translationError, setTranslationError] = useState<string | null>(null);
  const [ttsError, setTtsError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Video Playhead Tracking & Player Ref
  const videoPlayerRef = useRef<VideoPlayerRef>(null);
  const [currentPlayTime, setCurrentPlayTime] = useState<number>(0);
  const [isVideoPlaying, setIsVideoPlaying] = useState<boolean>(false);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  // Voice Preview
  const [previewAudioUrl, setPreviewAudioUrl] = useState<string | null>(null);
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);

  // Subtitles State
  const [subtitles, setSubtitles] = useState<SubtitleSegment[]>([]);
  const [subtitleLanguage, setSubtitleLanguage] = useState<'km' | 'en'>('km');
  const [inPlayerSubtitleLang, setInPlayerSubtitleLang] = useState<'off' | 'km' | 'en'>('km');
  const [subtitleStyles, setSubtitleStyles] = useState<SubtitleStylePreferences>({
    preset: 'standard',
    fontSize: 'base',
    textColor: 'white',
    position: 'bottom',
    bgOpacity: 0.75,
    bottomMargin: 12,
    shadow: false,
  });

  // Global AI Modal (opened from Voice or Export tab)
  const [activeAIModalSegment, setActiveAIModalSegment] = useState<TranslationSegment | null>(null);
  const [isRenameModalOpen, setIsRenameModalOpen] = useState<boolean>(false);

  // Compute active segment based on current playback time
  const activeSegmentId = useMemo(() => {
    if (!currentPlayTime) return null;
    const match = transcriptSegments.find(
      (s) => currentPlayTime >= s.start_time && currentPlayTime <= s.end_time
    );
    return match?.id || null;
  }, [currentPlayTime, transcriptSegments]);

  // Stage fetchers
  const fetchTranscriptData = useCallback(async () => {
    try {
      const data = await api.getTranscript(projectId);
      setTranscriptSegments(data.segments || []);
      if (data.segmentation_mode) {
        setSegmentationMode(data.segmentation_mode);
      }
    } catch {
      // ignore if empty
    }
  }, [projectId]);

  const fetchTranslationData = useCallback(async () => {
    try {
      const data = await api.getTranslations(projectId);
      setTranslationSegments(data.segments || []);
    } catch {
      // ignore if empty
    }
  }, [projectId]);

  const fetchAudioData = useCallback(async () => {
    try {
      const data = await api.getGeneratedAudios(projectId);
      setGeneratedAudios(data.audios || []);
    } catch {
      // ignore if empty
    }
  }, [projectId]);

  const fetchExportData = useCallback(async () => {
    try {
      const status = await api.getExportStatus(projectId);
      setExportStatus(status);
      setTimingConflicts(status.timing_conflicts || []);
    } catch {
      // ignore if empty
    }
  }, [projectId]);

  const fetchSubtitlesData = useCallback(
    async (lang: 'km' | 'en' = subtitleLanguage) => {
      try {
        const data = await api.getSubtitles(projectId, lang);
        setSubtitles(data.segments || []);
      } catch {
        // ignore if empty
      }
    },
    [projectId, subtitleLanguage]
  );

  useEffect(() => {
    fetchSubtitlesData(subtitleLanguage);
  }, [fetchSubtitlesData, subtitleLanguage]);

  const fetchCatalogs = useCallback(async () => {
    try {
      const [vData, pData] = await Promise.all([
        api.getVoices().catch(() => ({ voices: [], default_voice: 'default' })),
        api.getTranslationProviders().catch(() => ({ providers: [], default_provider: 'nllb', default_style: 'natural', styles: [] })),
      ]);
      setVoices(vData.voices || []);
      setTranslationProviders(pData.providers || []);
    } catch (e) {
      console.error('Failed to load catalogs', e);
    }
  }, []);

  const fetchProjectData = useCallback(async (isInitial = false) => {
    try {
      if (isInitial) setLoading(true);
      const data = await api.getProject(projectId);
      setProject(data);

      if (data.tts_provider && data.tts_voice) {
        setSelectedVoice({ provider: data.tts_provider, voice: data.tts_voice });
      }
      if (data.translation_provider) {
        setSelectedTransProvider(data.translation_provider);
      }
      if (data.translation_style) {
        setSelectedTransStyle(data.translation_style);
      }

      // Initial tab smart selection on first load
      if (isInitial) {
        if (data.status === 'completed' || Boolean(data.video?.exported_video_path)) {
          setActiveTab('export');
        } else if (data.status === 'voice_generated' || data.status === 'generating_voice') {
          setActiveTab('voice');
        } else if (data.status === 'translated' || data.status === 'translating') {
          setActiveTab('translation');
        } else if (data.status === 'transcribed' || data.status === 'transcribing') {
          setActiveTab('translation');
        } else if (data.status === 'audio_extracted' || data.status === 'uploaded') {
          setActiveTab('transcript');
        } else {
          setActiveTab('media');
        }
      }

      // Synchronize running flags
      const isExtractJobRunning =
        data.status === 'uploaded' ||
        Boolean(data.jobs?.some((j) => j.job_type === 'extract_audio' && (j.status === 'pending' || j.status === 'running')));
      setIsExtracting(isExtractJobRunning);

      const isSttJobRunning =
        data.status === 'transcribing' ||
        Boolean(data.jobs?.some((j) => j.job_type === 'transcribe' && (j.status === 'pending' || j.status === 'running')));
      setIsTranscribing(isSttJobRunning);

      const isTransJobRunning =
        data.status === 'translating' ||
        Boolean(data.jobs?.some((j) => j.job_type === 'translate' && (j.status === 'pending' || j.status === 'running')));
      setIsTranslating(isTransJobRunning);

      const isTtsJobRunning =
        data.status === 'generating_voice' ||
        Boolean(data.jobs?.some((j) => j.job_type === 'tts' && (j.status === 'pending' || j.status === 'running')));
      setIsGeneratingVoice(isTtsJobRunning);

      const isDubJobRunning =
        data.status === 'synchronizing' ||
        Boolean(data.jobs?.some((j) => j.job_type === 'dub' && (j.status === 'pending' || j.status === 'running')));
      setIsExporting(isDubJobRunning);

      // Load stage segments
      await Promise.all([
        fetchTranscriptData(),
        fetchTranslationData(),
        fetchAudioData(),
        fetchExportData(),
        fetchSubtitlesData(subtitleLanguage),
      ]);
    } catch (err: any) {
      console.error('Failed to fetch project data:', err);
    } finally {
      if (isInitial) setLoading(false);
      setRefreshing(false);
    }
  }, [projectId, fetchTranscriptData, fetchTranslationData, fetchAudioData, fetchExportData]);

  // Initial load
  useEffect(() => {
    fetchCatalogs();
    fetchProjectData(true);
  }, [fetchCatalogs, fetchProjectData]);

  // Active job polling interval
  useEffect(() => {
    const isAnyJobRunning =
      isExtracting || isTranscribing || isTranslating || isGeneratingVoice || isExporting;

    if (!isAnyJobRunning) return;

    const interval = setInterval(async () => {
      try {
        const data = await api.getProject(projectId);
        setProject(data);

        // Check transcription
        if (isTranscribing) {
          const job = data.jobs?.find((j) => j.job_type === 'transcribe');
          if (job?.status === 'completed' || data.status === 'transcribed') {
            setIsTranscribing(false);
            setTranscriptionError(null);
            await fetchTranscriptData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (job?.status === 'failed' || data.status === 'failed') {
            setIsTranscribing(false);
            setTranscriptionError(job?.error_message || 'Transcription failed.');
          }
        }

        // Check translation
        if (isTranslating) {
          const job = data.jobs?.find((j) => j.job_type === 'translate');
          if (job?.status === 'completed' || data.status === 'translated') {
            setIsTranslating(false);
            setTranslationError(null);
            await fetchTranslationData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (job?.status === 'failed' || data.status === 'failed') {
            setIsTranslating(false);
            setTranslationError(job?.error_message || 'Translation failed.');
          }
        }

        // Check TTS
        if (isGeneratingVoice) {
          const job = data.jobs?.find((j) => j.job_type === 'tts');
          if (job?.status === 'completed' || data.status === 'voice_generated') {
            setIsGeneratingVoice(false);
            setTtsError(null);
            await fetchAudioData();
            await fetchExportData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (job?.status === 'failed' || data.status === 'failed') {
            setIsGeneratingVoice(false);
            setTtsError(job?.error_message || 'Speech synthesis failed.');
          }
        }

        // Check Dub export
        if (isExporting) {
          const job = data.jobs?.find((j) => j.job_type === 'dub');
          if (job?.status === 'completed' || data.status === 'completed') {
            setIsExporting(false);
            setExportError(null);
            await fetchExportData();
            if (onProjectUpdated) onProjectUpdated();
          } else if (job?.status === 'failed' || data.status === 'failed') {
            setIsExporting(false);
            setExportError(job?.error_message || 'Export failed.');
          }
        }

        // Check audio extraction
        if (isExtracting && (data.status === 'audio_extracted' || data.status !== 'uploaded')) {
          setIsExtracting(false);
          if (onProjectUpdated) onProjectUpdated();
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [
    isExtracting,
    isTranscribing,
    isTranslating,
    isGeneratingVoice,
    isExporting,
    projectId,
    fetchTranscriptData,
    fetchTranslationData,
    fetchAudioData,
    fetchExportData,
    onProjectUpdated,
  ]);

  // Actions
  const handleUploadFile = async (file: File) => {
    setIsUploading(true);
    setUploadProgress(0);
    try {
      await api.uploadVideo(projectId, file, (percentage) => {
        setUploadProgress(percentage);
      });
      setIsExtracting(true);
      await fetchProjectData();
      if (onProjectUpdated) onProjectUpdated();
    } finally {
      setIsUploading(false);
    }
  };

  const handleExtractAudio = async () => {
    setIsExtracting(true);
    try {
      await api.triggerAudioExtraction(projectId);
      await fetchProjectData();
    } catch (err: any) {
      alert(`Audio extraction failed: ${err.message}`);
      setIsExtracting(false);
    }
  };

  const handleStartTranscription = async () => {
    setIsTranscribing(true);
    setTranscriptionError(null);
    try {
      await api.startTranscription(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setIsTranscribing(false);
      setTranscriptionError(err.message || 'Failed to start transcription');
    }
  };

  const handleUpdateTranscriptSegment = async (segmentId: string, text: string) => {
    const updated = await api.updateTranscriptSegment(projectId, segmentId, text);
    setTranscriptSegments((prev) => prev.map((s) => (s.id === segmentId ? updated : s)));
  };

  const handleStartTranslation = async () => {
    setIsTranslating(true);
    setTranslationError(null);
    try {
      await api.startTranslation(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setIsTranslating(false);
      setTranslationError(err.message || 'Failed to start translation');
    }
  };

  const handleUpdateTranslationSettings = async (provider: string, style: string) => {
    setSelectedTransProvider(provider);
    setSelectedTransStyle(style);
    try {
      await api.updateProjectTranslationSettings(projectId, {
        translation_provider: provider,
        translation_style: style,
      });
      await fetchProjectData();
    } catch (err: any) {
      console.error('Failed to update translation settings:', err);
    }
  };

  const handleUpdateTranslationSegment = async (segmentId: string, khmerText: string) => {
    const updated = await api.updateTranslationSegment(projectId, segmentId, khmerText);
    setTranslationSegments((prev) => prev.map((s) => (s.id === segmentId ? updated : s)));
    await fetchAudioData();
    await fetchExportData();
  };

  const handleRetranslateSegment = async (segmentId: string) => {
    const updated = await api.retranslateSegment(projectId, segmentId);
    setTranslationSegments((prev) => prev.map((s) => (s.id === segmentId ? updated : s)));
    await fetchAudioData();
    await fetchExportData();
  };

  const handleApplyAIImprovement = async (
    segmentId: string,
    khmerText: string,
    style?: string,
    explanation?: string
  ) => {
    const updated = await api.applyTranslationSuggestion(projectId, segmentId, {
      khmer_text: khmerText,
      style: style || selectedTransStyle,
      explanation: explanation || undefined,
    });
    setTranslationSegments((prev) => prev.map((s) => (s.id === segmentId ? updated : s)));
    await fetchAudioData();
    await fetchExportData();
  };

  const handleSelectVoice = async (provider: string, voice: string) => {
    setSelectedVoice({ provider, voice });
    try {
      await api.updateProjectVoice(projectId, provider, voice);
      await fetchProjectData();
    } catch (err: any) {
      console.error('Failed to update voice:', err);
    }
  };

  const handlePreviewVoice = async (provider: string, voice: string) => {
    try {
      setPreviewingVoice(`${provider}-${voice}`);
      const blob = await api.previewVoice(provider, voice);
      const url = URL.createObjectURL(blob);
      setPreviewAudioUrl(url);
    } catch (err: any) {
      alert(`Voice preview failed: ${err.message}`);
    } finally {
      setPreviewingVoice(null);
    }
  };

  const handleGenerateAllSpeech = async () => {
    setIsGeneratingVoice(true);
    setTtsError(null);
    try {
      await api.startTTS(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setIsGeneratingVoice(false);
      setTtsError(err.message || 'Failed to start TTS speech synthesis');
    }
  };

  const handleRegenerateSegmentAudio = async (segmentId: string) => {
    try {
      await api.regenerateAudioSegment(projectId, segmentId);
      await fetchAudioData();
      await fetchExportData();
    } catch (err: any) {
      alert(`Audio regeneration failed: ${err.message}`);
    }
  };

  const handleExportVideo = async () => {
    setIsExporting(true);
    setExportError(null);
    try {
      await api.startExport(projectId);
      await fetchProjectData();
    } catch (err: any) {
      setIsExporting(false);
      setExportError(err.message || 'Failed to trigger video dubbing export');
    }
  };

  const handleSeekVideo = (timestamp: number) => {
    if (videoPlayerRef.current) {
      videoPlayerRef.current.seekTo(timestamp);
    }
  };

  const isMediaReady = Boolean(project?.video?.file_path || project?.original_video_path);
  const isTranscriptReady = transcriptSegments.length > 0;
  const isTranslationReady = translationSegments.length > 0;
  const isVoiceReady = generatedAudios.length > 0;
  const isExportReady = project?.status === 'completed' || Boolean(exportStatus?.exported_video_path);

  if (loading || !project) {
    return (
      <div className="p-16 text-center space-y-3 max-w-7xl mx-auto">
        <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-semibold text-slate-700">Loading Dubbing Studio...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-12">
      {/* Studio Navigation & Workflow Progress Header */}
      <StudioHeader
        project={project}
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab)}
        onBack={onBack}
        onRefresh={() => {
          setRefreshing(true);
          fetchProjectData();
        }}
        refreshing={refreshing}
        hasMedia={isMediaReady}
        hasTranscript={isTranscriptReady}
        hasTranslation={isTranslationReady}
        hasVoice={isVoiceReady}
        hasExport={isExportReady}
        isExtracting={isExtracting}
        isTranscribing={isTranscribing}
        isTranslating={isTranslating}
        isGeneratingVoice={isGeneratingVoice}
        isExporting={isExporting}
        timingConflictsCount={timingConflicts.length}
        onRename={() => setIsRenameModalOpen(true)}
      />

      {/* 1. Persistent Video Preview Section */}
      {project.video && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-8">
            <PersistentVideoPlayer
              ref={videoPlayerRef}
              projectId={projectId}
              video={project.video || null}
              activeSegmentOrder={
                transcriptSegments.find((s) => s.id === activeSegmentId)?.segment_order || null
              }
              onTimeUpdate={(t) => setCurrentPlayTime(t)}
              onPlayStateChange={(playing) => setIsVideoPlaying(playing)}
              subtitles={subtitles}
              subtitleLanguage={inPlayerSubtitleLang}
              onSubtitleLanguageChange={(lang) => {
                setInPlayerSubtitleLang(lang);
                if (lang !== 'off') {
                  setSubtitleLanguage(lang);
                }
              }}
              subtitleStyles={subtitleStyles}
            />
          </div>

          <div className="lg:col-span-4 space-y-4">
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs text-xs space-y-3">
              <div className="flex items-center justify-between text-slate-500 text-[11px] border-b border-slate-100 pb-2">
                <span className="font-semibold uppercase tracking-wider">Active Workspace</span>
                <span className="font-mono text-indigo-600 capitalize font-medium">{activeTab} tab</span>
              </div>

              <div className="space-y-1.5 text-slate-600">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Video Duration:</span>
                  <span className="font-mono font-medium text-slate-800">
                    {project.video?.duration_seconds ? `${project.video.duration_seconds.toFixed(1)}s` : 'N/A'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">English Speech Segments:</span>
                  <span className="font-mono font-medium text-slate-800">
                    {transcriptSegments.length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Khmer Synthesized Speech:</span>
                  <span className="font-mono font-medium text-slate-800">
                    {generatedAudios.length} / {transcriptSegments.length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Speech Timing Conflicts:</span>
                  <span
                    className={`font-mono font-semibold ${
                      timingConflicts.length > 0 ? 'text-rose-600' : 'text-emerald-600'
                    }`}
                  >
                    {timingConflicts.length}
                  </span>
                </div>
              </div>

              <p className="text-slate-500 text-[11px] leading-relaxed pt-1 border-t border-slate-100">
                Scrub the playhead or click any timeline block to seek video playback and synchronize transcript, translation, and speech tracks.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 2. Interactive Dubbing Timeline (Positioned between Video Preview and Workspace Tab) */}
      {isTranscriptReady && (
        <DubbingTimeline
          duration={project.video?.duration_seconds || transcriptSegments[transcriptSegments.length - 1]?.end_time || 0}
          currentTime={currentPlayTime}
          transcriptSegments={transcriptSegments}
          translationSegments={translationSegments}
          generatedAudios={generatedAudios}
          timingConflicts={timingConflicts}
          selectedSegmentId={selectedSegmentId}
          onSelectSegment={(id) => setSelectedSegmentId(id)}
          onSeek={handleSeekVideo}
          onNavigateToTranslation={(id) => {
            setSelectedSegmentId(id);
            setActiveTab('translation');
          }}
          onNavigateToSubtitles={(id) => {
            setSelectedSegmentId(id);
            setActiveTab('subtitles');
          }}
          onOpenAIImprove={(seg) => setActiveAIModalSegment(seg)}
          isPlaying={isVideoPlaying}
        />
      )}

      {/* 3. Active Workspace Stage Editor Tab */}
      <div className="space-y-6">
        {activeTab === 'media' && (
          <MediaTab
            project={project}
            video={project.video || null}
            onUploadFile={handleUploadFile}
            onExtractAudio={handleExtractAudio}
            isUploading={isUploading}
            isExtracting={isExtracting}
            uploadProgress={uploadProgress}
          />
        )}

        {activeTab === 'transcript' && (
          <TranscriptTab
            projectId={projectId}
            segmentationMode={segmentationMode}
            segments={transcriptSegments}
            isTranscribing={isTranscribing}
            onStartTranscription={handleStartTranscription}
            onUpdateSegment={handleUpdateTranscriptSegment}
            onSeekVideo={handleSeekVideo}
            onResegmentSuccess={async () => {
              await Promise.all([
                fetchTranscriptData(),
                fetchTranslationData(),
                fetchAudioData(),
              ]);
            }}
            activeSegmentId={activeSegmentId}
            selectedSegmentId={selectedSegmentId}
            transcriptionError={transcriptionError}
            isMediaReady={isMediaReady}
          />
        )}

        {activeTab === 'translation' && (
          <TranslationTab
            projectId={projectId}
            translationSegments={translationSegments}
            transcriptSegments={transcriptSegments}
            generatedAudios={generatedAudios}
            timingConflicts={timingConflicts}
            providers={translationProviders}
            selectedProvider={selectedTransProvider}
            selectedStyle={selectedTransStyle}
            isTranslating={isTranslating}
            onUpdateTranslationSettings={handleUpdateTranslationSettings}
            onStartTranslation={handleStartTranslation}
            onUpdateSegment={handleUpdateTranslationSegment}
            onRetranslateSegment={handleRetranslateSegment}
            onApplyAIImprovement={handleApplyAIImprovement}
            onSeekVideo={handleSeekVideo}
            activeSegmentId={activeSegmentId}
            selectedSegmentId={selectedSegmentId}
            translationError={translationError}
            isTranscriptReady={isTranscriptReady}
          />
        )}

        {activeTab === 'subtitles' && (
          <SubtitleTab
            projectId={projectId}
            subtitles={subtitles}
            currentLanguage={subtitleLanguage}
            onLanguageChange={(lang) => {
              setSubtitleLanguage(lang);
              if (inPlayerSubtitleLang !== 'off') {
                setInPlayerSubtitleLang(lang);
              }
            }}
            onRefreshSubtitles={() => fetchSubtitlesData(subtitleLanguage)}
            onSeekVideo={handleSeekVideo}
            activeSegmentId={activeSegmentId}
            selectedSegmentId={selectedSegmentId}
            subtitleStyles={subtitleStyles}
            onUpdateStyles={setSubtitleStyles}
          />
        )}

        {activeTab === 'voice' && (
          <VoiceTab
            voices={voices}
            selectedVoice={selectedVoice}
            generatedAudios={generatedAudios}
            translationSegments={translationSegments}
            timingConflicts={timingConflicts}
            isGeneratingSpeech={isGeneratingVoice}
            onSelectVoice={handleSelectVoice}
            onPreviewVoice={handlePreviewVoice}
            onGenerateAllSpeech={handleGenerateAllSpeech}
            onRegenerateSegmentAudio={handleRegenerateSegmentAudio}
            onOpenAIImprove={(seg) => setActiveAIModalSegment(seg)}
            onSeekVideo={handleSeekVideo}
            activeSegmentId={activeSegmentId}
            selectedSegmentId={selectedSegmentId}
            ttsError={ttsError}
            previewAudioUrl={previewAudioUrl}
            previewingVoice={previewingVoice}
          />
        )}

        {activeTab === 'export' && (
          <ExportTab
            project={project}
            exportStatus={exportStatus}
            timingConflicts={timingConflicts}
            translationSegments={translationSegments}
            isExporting={isExporting}
            onExportVideo={handleExportVideo}
            onOpenAIImprove={(seg) => setActiveAIModalSegment(seg)}
            exportError={exportError}
          />
        )}
      </div>

      {/* Global AI Refinement Modal for Voice / Export tabs */}
      {activeAIModalSegment && (
        <AIImproveModal
          segment={activeAIModalSegment}
          projectId={projectId}
          onClose={() => setActiveAIModalSegment(null)}
          onApply={async (text, style, explanation) => {
            await handleApplyAIImprovement(activeAIModalSegment.id, text, style, explanation);
            setActiveAIModalSegment(null);
          }}
          targetDuration={
            activeAIModalSegment.end_time && activeAIModalSegment.start_time
              ? activeAIModalSegment.end_time - activeAIModalSegment.start_time
              : undefined
          }
          activeProviderId={selectedTransProvider}
          providers={translationProviders}
          initialMode="improve"
        />
      )}

      {/* Rename Project Modal */}
      <RenameProjectModal
        isOpen={isRenameModalOpen}
        project={project ? { id: project.id, title: project.title } : null}
        onClose={() => setIsRenameModalOpen(false)}
        onRenamed={(_id, newTitle) => {
          setProject((prev) => (prev ? { ...prev, title: newTitle } : null));
          onProjectUpdated?.();
        }}
      />
    </div>
  );
};
