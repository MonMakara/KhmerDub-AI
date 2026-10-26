import {
  HealthResponse,
  ProjectSummary,
  ProjectDetail,
  ProcessingJob,
  TranscriptResponse,
  TranscriptSegment,
  SegmentationPreviewResponse,
  SegmentationApplyResponse,
  TranslationSegment,
  TranslationListResponse,
  GeneratedAudio,
  GeneratedAudioListResponse,
  ExportStatusResponse,
  VoiceListResponse,
  TranslationProviderListResponse,
  TestConnectionRequest,
  TestConnectionResponse,
  AIImproveRequest,
  AIImproveResponse,
  AlternativesResponse,
  ApplyTranslationRequest,
  ProjectTranslationSettingsUpdate,
  ProjectDeleteResponse,
  SubtitleSegment,
  SubtitleListResponse,
  VoiceProfile,
  VoiceStudioData,
  CreateVoiceProfilePayload,
  UpdateVoiceProfilePayload,
  ToolkitTask,
  ToolkitTranscriptSegment,
  ToolkitCapabilities,
  TTSVoiceOption,
  ToolkitTranslationSegment,
  TranslationLanguagePair,
  SubtitleConvertResponse,
  TranslationProviderInfo,
  VideoDownloaderMetadata,
  VideoDownloaderStartPayload,
  VideoDownloaderImportDubbingPayload,
  VideoDownloaderImportDubbingResponse,
  TrimmerMediaInfo,
  TrimmerTrimPayload,
  TrimmerThumbnailsPayload,
  TrimmerImportDubbingPayload,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : '/api';

export const api = {
  async getHealth(): Promise<HealthResponse> {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) {
      throw new Error(`Failed to fetch health check: ${res.statusText}`);
    }
    return res.json();
  },

  async listProjects(): Promise<ProjectSummary[]> {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) {
      throw new Error(`Failed to fetch projects: ${res.statusText}`);
    }
    return res.json();
  },

  async createProject(title: string): Promise<ProjectDetail> {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title,
        original_language: 'en',
        target_language: 'km',
      }),
    });
    if (!res.ok) {
      throw new Error(`Failed to create project: ${res.statusText}`);
    }
    return res.json();
  },

  async getProject(projectId: string): Promise<ProjectDetail> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch project ${projectId}: ${res.statusText}`);
    }
    return res.json();
  },

  async renameProject(projectId: string, title: string): Promise<ProjectDetail> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) {
      let detail = `Failed to rename project: ${res.statusText}`;
      try {
        const data = await res.json();
        if (data && data.detail) {
          detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        }
      } catch {}
      throw new Error(detail);
    }
    return res.json();
  },

  async deleteProject(projectId: string): Promise<ProjectDeleteResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      let detail = `Failed to delete project: ${res.statusText}`;
      try {
        const data = await res.json();
        if (data && data.detail) {
          detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        }
      } catch {}
      throw new Error(detail);
    }
    return res.json();
  },

  uploadVideo(
    projectId: string,
    file: File,
    onProgress?: (percentage: number) => void
  ): Promise<ProjectDetail> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('file', file);

      xhr.open('POST', `${API_BASE}/projects/${projectId}/upload`);

      if (xhr.upload && onProgress) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const pct = Math.round((event.loaded / event.total) * 100);
            onProgress(pct);
          }
        };
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve(data);
          } catch (e) {
            reject(new Error('Invalid JSON response from server'));
          }
        } else {
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(err.detail || `Upload failed with status ${xhr.status}`));
          } catch {
            reject(new Error(xhr.responseText || `Upload failed with status ${xhr.status}`));
          }
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during video upload'));
      };

      xhr.send(formData);
    });
  },

  async triggerAudioExtraction(projectId: string): Promise<ProcessingJob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/extract-audio`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to trigger extraction: ${res.statusText}`);
    }
    return res.json();
  },

  async getProjectJobs(projectId: string): Promise<ProcessingJob[]> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/jobs`);
    if (!res.ok) {
      throw new Error(`Failed to fetch jobs: ${res.statusText}`);
    }
    return res.json();
  },

  getVideoUrl(projectId: string): string {
    return `${API_BASE}/projects/${projectId}/video`;
  },

  getAudioUrl(projectId: string): string {
    return `${API_BASE}/projects/${projectId}/audio`;
  },

  async startTranscription(projectId: string): Promise<ProcessingJob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/transcribe`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Transcription request failed: ${res.statusText}`);
    }
    return res.json();
  },

  async getTranscript(projectId: string): Promise<TranscriptResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/transcript`);
    if (!res.ok) {
      throw new Error(`Failed to fetch transcript: ${res.statusText}`);
    }
    return res.json();
  },

  async updateTranscriptSegment(
    projectId: string,
    segmentId: string,
    text: string
  ): Promise<TranscriptSegment> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/transcript/${segmentId}`,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update segment: ${res.statusText}`);
    }
    return res.json();
  },

  async previewTranscriptSegmentation(
    projectId: string,
    mode: string
  ): Promise<SegmentationPreviewResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/transcript/segmentation/preview?mode=${encodeURIComponent(mode)}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to preview segmentation: ${res.statusText}`);
    }
    return res.json();
  },

  async applyTranscriptSegmentation(
    projectId: string,
    mode: string,
    confirm: boolean = false
  ): Promise<SegmentationApplyResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/transcript/segmentation/apply`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, confirm }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to apply segmentation: ${res.statusText}`);
    }
    return res.json();
  },

  async splitTranscriptSegment(
    projectId: string,
    segmentId: string,
    wordIndex: number
  ): Promise<{ message: string; segments: TranscriptSegment[] }> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/transcript/${segmentId}/split`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word_index: wordIndex }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to split segment: ${res.statusText}`);
    }
    return res.json();
  },

  async mergeTranscriptSegmentNext(
    projectId: string,
    segmentId: string
  ): Promise<{ message: string; segments: TranscriptSegment[] }> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/transcript/${segmentId}/merge-next`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to merge segment: ${res.statusText}`);
    }
    return res.json();
  },

  async startTranslation(projectId: string): Promise<ProcessingJob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/translate`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Translation request failed: ${res.statusText}`);
    }
    return res.json();
  },

  async getTranslations(projectId: string): Promise<TranslationListResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/translations`);
    if (!res.ok) {
      throw new Error(`Failed to fetch translations: ${res.statusText}`);
    }
    return res.json();
  },

  async updateTranslationSegment(
    projectId: string,
    segmentId: string,
    khmerText: string
  ): Promise<TranslationSegment> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/translations/${segmentId}`,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ khmer_text: khmerText }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update translation: ${res.statusText}`);
    }
    return res.json();
  },

  async retranslateSegment(
    projectId: string,
    segmentId: string
  ): Promise<TranslationSegment> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/translations/${segmentId}/retranslate`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to retranslate segment: ${res.statusText}`);
    }
    return res.json();
  },

  async getVoices(): Promise<VoiceListResponse> {
    const res = await fetch(`${API_BASE}/tts/voices`);
    if (!res.ok) {
      throw new Error(`Failed to fetch voices: ${res.statusText}`);
    }
    return res.json();
  },

  async previewVoice(
    provider: string,
    voice: string,
    text?: string
  ): Promise<Blob> {
    const res = await fetch(`${API_BASE}/tts/preview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        provider,
        voice,
        text,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Voice preview failed: ${res.statusText}`);
    }
    return res.blob();
  },

  async updateProjectVoice(
    projectId: string,
    tts_provider: string,
    tts_voice: string
  ): Promise<ProjectDetail> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/voice`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        tts_provider,
        tts_voice,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update project voice: ${res.statusText}`);
    }
    return res.json();
  },

  async startTTS(projectId: string): Promise<ProcessingJob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/tts`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `TTS synthesis request failed: ${res.statusText}`);
    }
    return res.json();
  },

  async getGeneratedAudios(projectId: string): Promise<GeneratedAudioListResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/generated-audio`);
    if (!res.ok) {
      throw new Error(`Failed to fetch generated audios: ${res.statusText}`);
    }
    return res.json();
  },

  async regenerateAudioSegment(
    projectId: string,
    segmentId: string
  ): Promise<GeneratedAudio> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/tts/${segmentId}/regenerate`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to regenerate audio segment: ${res.statusText}`);
    }
    return res.json();
  },

  getAudioSegmentUrl(projectId: string, segmentId: string): string {
    return `${API_BASE}/projects/${projectId}/tts/${segmentId}/audio`;
  },

  async startExport(projectId: string): Promise<ProcessingJob> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/export`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Export request failed: ${res.statusText}`);
    }
    return res.json();
  },

  async autoFitDubbing(projectId: string, maxTempo: number = 1.25): Promise<ExportStatusResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/dubbing/auto-fit?max_tempo=${maxTempo}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Auto-fit failed: ${res.statusText}`);
    }
    return res.json();
  },

  async getExportStatus(projectId: string): Promise<ExportStatusResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/export/status`);
    if (!res.ok) {
      throw new Error(`Failed to fetch export status: ${res.statusText}`);
    }
    return res.json();
  },

  getExportVideoUrl(projectId: string): string {
    return `${API_BASE}/projects/${projectId}/export/video`;
  },

  getExportDownloadUrl(projectId: string): string {
    return `${API_BASE}/projects/${projectId}/export/download`;
  },

  async getTranslationProviders(): Promise<TranslationProviderListResponse> {
    const res = await fetch(`${API_BASE}/translation/providers`);
    if (!res.ok) {
      throw new Error(`Failed to fetch translation providers: ${res.statusText}`);
    }
    return res.json();
  },

  async testTranslationConnection(
    data: TestConnectionRequest
  ): Promise<TestConnectionResponse> {
    const res = await fetch(`${API_BASE}/translation/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Connection test failed: ${res.statusText}`);
    }
    return res.json();
  },

  async saveTranslationCredentials(
    provider: string,
    apiKey: string,
    baseUrl?: string,
    model?: string
  ): Promise<{ success: boolean; message?: string }> {
    const res = await fetch(`${API_BASE}/translation/credentials`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        base_url: baseUrl || undefined,
        model: model || undefined,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to save credentials: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteTranslationCredentials(
    provider: string
  ): Promise<{ success: boolean; message: string }> {
    const res = await fetch(`${API_BASE}/translation/credentials/${provider}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to delete credentials: ${res.statusText}`);
    }
    return res.json();
  },

  async updateProjectTranslationSettings(
    projectId: string,
    settings: ProjectTranslationSettingsUpdate
  ): Promise<ProjectDetail> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/translation-settings`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err.detail || `Failed to update translation settings: ${res.statusText}`
      );
    }
    return res.json();
  },

  async aiImproveSegment(
    projectId: string,
    segmentId: string,
    req: AIImproveRequest
  ): Promise<AIImproveResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/translations/${segmentId}/ai-improve`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `AI improvement failed: ${res.statusText}`);
    }
    return res.json();
  },

  async getTranslationAlternatives(
    projectId: string,
    segmentId: string
  ): Promise<AlternativesResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/translations/${segmentId}/alternatives`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err.detail || `Failed to fetch translation alternatives: ${res.statusText}`
      );
    }
    return res.json();
  },

  async applyTranslationSuggestion(
    projectId: string,
    segmentId: string,
    req: ApplyTranslationRequest
  ): Promise<TranslationSegment> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/translations/${segmentId}/apply`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        err.detail || `Failed to apply translation: ${res.statusText}`
      );
    }
    return res.json();
  },

  async getSubtitles(
    projectId: string,
    language: string = 'km'
  ): Promise<SubtitleListResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles?language=${encodeURIComponent(language)}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to fetch subtitles: ${res.statusText}`);
    }
    return res.json();
  },

  async updateSubtitleSegment(
    projectId: string,
    segmentOrder: number,
    payload: {
      text?: string;
      start_time?: number;
      end_time?: number;
      language?: string;
    }
  ): Promise<SubtitleSegment> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/${segmentOrder}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update subtitle: ${res.statusText}`);
    }
    return res.json();
  },

  async autoSplitSubtitles(
    projectId: string,
    language: string = 'km',
    maxChars: number = 75,
    maxDuration: number = 6.5
  ): Promise<SubtitleListResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/subtitles/auto-split`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        language,
        max_chars: maxChars,
        max_duration: maxDuration,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to auto-split subtitles: ${res.statusText}`);
    }
    return res.json();
  },

  async splitSubtitleCue(
    projectId: string,
    segmentOrder: number,
    language: string = 'km',
    splitIndex?: number,
    splitRatio: number = 0.5
  ): Promise<SubtitleListResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/${segmentOrder}/split`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          language,
          split_index: splitIndex,
          split_ratio: splitRatio,
        }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to split subtitle cue: ${res.statusText}`);
    }
    return res.json();
  },

  async mergeSubtitleCue(
    projectId: string,
    segmentOrder: number,
    language: string = 'km'
  ): Promise<SubtitleListResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/${segmentOrder}/merge`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to merge subtitle cue: ${res.statusText}`);
    }
    return res.json();
  },

  async keepSubtitleEdits(
    projectId: string,
    segmentOrder: number,
    language: string = 'km'
  ): Promise<SubtitleListResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/${segmentOrder}/keep`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to keep subtitle edits: ${res.statusText}`);
    }
    return res.json();
  },

  async resetSubtitleCue(
    projectId: string,
    segmentOrder: number,
    language: string = 'km'
  ): Promise<SubtitleListResponse> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/${segmentOrder}/reset?language=${encodeURIComponent(language)}`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reset subtitle cue: ${res.statusText}`);
    }
    return res.json();
  },

  async resetSubtitles(
    projectId: string,
    language: string = 'km'
  ): Promise<{ message: string; deleted_count: number; language: string }> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/reset?language=${encodeURIComponent(language)}`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reset subtitles: ${res.statusText}`);
    }
    return res.json();
  },

  getSubtitleExportUrl(
    projectId: string,
    language: string = 'km',
    format: string = 'srt'
  ): string {
    return `${API_BASE}/projects/${projectId}/subtitles/export?language=${encodeURIComponent(language)}&format=${encodeURIComponent(format)}`;
  },

  getSubtitleStreamUrl(
    projectId: string,
    language: string = 'km',
    format: string = 'vtt'
  ): string {
    return `${API_BASE}/projects/${projectId}/subtitles/stream?language=${encodeURIComponent(language)}&format=${encodeURIComponent(format)}`;
  },

  // ---------------- Voice Studio APIs (Phase 13A) ----------------

  async getVoiceStudio(): Promise<VoiceStudioData> {
    const res = await fetch(`${API_BASE}/voices`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to fetch Voice Studio data: ${res.statusText}`);
    }
    return res.json();
  },

  async getVoiceProfile(profileId: string): Promise<VoiceProfile> {
    const res = await fetch(`${API_BASE}/voices/${profileId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to fetch voice profile: ${res.statusText}`);
    }
    return res.json();
  },

  async createVoiceProfile(payload: CreateVoiceProfilePayload): Promise<VoiceProfile> {
    const formData = new FormData();
    formData.append('name', payload.name);
    if (payload.description) {
      formData.append('description', payload.description);
    }
    formData.append('gender', payload.gender || 'neutral');
    formData.append('speaker_name', payload.speaker_name);
    formData.append('authorized_by', payload.authorized_by);
    formData.append('consent_confirmed', String(payload.consent_confirmed));
    if (payload.reference_transcript) {
      formData.append('reference_transcript', payload.reference_transcript);
    }
    formData.append('file', payload.file);

    const res = await fetch(`${API_BASE}/voices`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to create voice profile: ${res.statusText}`);
    }
    return res.json();
  },

  async updateVoiceProfile(
    profileId: string,
    payload: UpdateVoiceProfilePayload
  ): Promise<VoiceProfile> {
    const res = await fetch(`${API_BASE}/voices/${profileId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update voice profile: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteVoiceProfile(
    profileId: string
  ): Promise<{ message: string; id: string; deleted_files_count: number }> {
    const res = await fetch(`${API_BASE}/voices/${profileId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to delete voice profile: ${res.statusText}`);
    }
    return res.json();
  },

  getVoiceProfileAudioUrl(profileId: string): string {
    return `${API_BASE}/voices/${profileId}/audio`;
  },

  // Media Toolkit API methods
  async getToolkitCapabilities(): Promise<ToolkitCapabilities> {
    const res = await fetch(`${API_BASE}/toolkit/capabilities`);
    if (!res.ok) {
      throw new Error(`Failed to fetch toolkit capabilities: ${res.statusText}`);
    }
    return res.json();
  },

  async extractAudio(formData: FormData): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/extract-audio`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Audio extraction failed: ${res.statusText}`);
    }
    return res.json();
  },

  async listToolkitTasks(toolType?: string): Promise<ToolkitTask[]> {
    const url = toolType
      ? `${API_BASE}/toolkit/tasks?tool_type=${encodeURIComponent(toolType)}`
      : `${API_BASE}/toolkit/tasks`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to list toolkit tasks: ${res.statusText}`);
    }
    return res.json();
  },

  async getToolkitTask(taskId: string): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/tasks/${taskId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to fetch toolkit task: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteToolkitTask(taskId: string): Promise<{ success: boolean; task_id: string }> {
    const res = await fetch(`${API_BASE}/toolkit/tasks/${taskId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to delete toolkit task: ${res.statusText}`);
    }
    return res.json();
  },

  getToolkitAudioStreamUrl(taskId: string): string {
    return `${API_BASE}/toolkit/tasks/${taskId}/stream`;
  },

  getToolkitAudioDownloadUrl(taskId: string): string {
    return `${API_BASE}/toolkit/tasks/${taskId}/download`;
  },

  async transcribeMedia(formData: FormData): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/transcribe`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Transcription failed: ${res.statusText}`);
    }
    return res.json();
  },

  async updateToolkitSegment(
    taskId: string,
    segmentId: string,
    text: string
  ): Promise<ToolkitTranscriptSegment> {
    const res = await fetch(`${API_BASE}/toolkit/tasks/${taskId}/segments/${segmentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update segment: ${res.statusText}`);
    }
    return res.json();
  },

  async resetToolkitEdits(
    taskId: string,
    segmentId?: string
  ): Promise<{ success: boolean; reset_count: number; segments: ToolkitTranscriptSegment[] }> {
    const res = await fetch(`${API_BASE}/toolkit/tasks/${taskId}/reset-edits`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(segmentId ? { segment_id: segmentId } : {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to reset edits: ${res.statusText}`);
    }
    return res.json();
  },

  getToolkitExportUrl(taskId: string, format: string): string {
    return `${API_BASE}/toolkit/tasks/${taskId}/export/${format}`;
  },

  // Standalone Text-to-Speech Studio API methods (Phase 13E.3)
  async getToolkitVoices(language?: string): Promise<TTSVoiceOption[]> {
    const url = language
      ? `${API_BASE}/toolkit/tts/voices?language=${encodeURIComponent(language)}`
      : `${API_BASE}/toolkit/tts/voices`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`Failed to list TTS voices: ${res.statusText}`);
    }
    return res.json();
  },

  async previewToolkitTTS(data: {
    text: string;
    provider: string;
    voice: string;
    language?: string;
  }): Promise<Blob> {
    const res = await fetch(`${API_BASE}/toolkit/tts/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `TTS preview failed: ${res.statusText}`);
    }
    return res.blob();
  },

  async generateToolkitTTS(data: {
    text: string;
    provider: string;
    voice: string;
    language?: string;
    target_format?: string;
    pause_duration_seconds?: number;
  }): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/tts/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `TTS generation failed: ${res.statusText}`);
    }
    return res.json();
  },

  async regenerateToolkitTTSSegment(
    taskId: string,
    segmentId: string,
    data?: { text?: string; pause_duration_seconds?: number }
  ): Promise<ToolkitTask> {
    const res = await fetch(
      `${API_BASE}/toolkit/tts/tasks/${taskId}/segments/${segmentId}/regenerate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {}),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Segment regeneration failed: ${res.statusText}`);
    }
    return res.json();
  },

  getToolkitTTSSegmentStreamUrl(taskId: string, segmentId: string): string {
    return `${API_BASE}/toolkit/tts/tasks/${taskId}/segments/${segmentId}/stream`;
  },

  getToolkitTTSSegmentDownloadUrl(taskId: string, segmentId: string): string {
    return `${API_BASE}/toolkit/tts/tasks/${taskId}/segments/${segmentId}/download`;
  },

  getToolkitTTSExportUrl(taskId: string, format: string): string {
    return `${API_BASE}/toolkit/tts/tasks/${taskId}/export?format=${format}`;
  },

  async parseTranscriptToAudio(content: string, filename?: string): Promise<any> {
    const res = await fetch(`${API_BASE}/toolkit/transcript-to-audio/parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, filename }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Parse transcript failed: ${res.statusText}`);
    }
    return res.json();
  },

  async importTranscriptFromTask(taskId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/toolkit/transcript-to-audio/import/${taskId}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Import transcript failed: ${res.statusText}`);
    }
    return res.json();
  },

  async generateTranscriptToAudio(data: {
    segments: Array<{
      segment_order: number;
      text: string;
      start_time?: number | null;
      end_time?: number | null;
      voice?: string | null;
      provider?: string | null;
    }>;
    mode: 'narration' | 'timed';
    provider: string;
    voice: string;
    language?: string;
    target_format?: string;
    pause_duration_seconds?: number;
    source_task_id?: string;
    filename?: string;
  }): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/transcript-to-audio/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Speech generation failed: ${res.statusText}`);
    }
    return res.json();
  },

  async updateTranscriptToAudioSegment(
    taskId: string,
    segmentId: string,
    data: {
      text?: string;
      start_time?: number | null;
      end_time?: number | null;
      voice?: string | null;
      provider?: string | null;
    }
  ): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/transcript-to-audio/tasks/${taskId}/segments/${segmentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Segment update failed: ${res.statusText}`);
    }
    return res.json();
  },

  async regenerateTranscriptToAudioSegment(
    taskId: string,
    segmentId: string,
    data?: {
      text?: string;
      start_time?: number | null;
      end_time?: number | null;
      voice?: string | null;
      provider?: string | null;
    }
  ): Promise<ToolkitTask> {
    const res = await fetch(
      `${API_BASE}/toolkit/transcript-to-audio/tasks/${taskId}/segments/${segmentId}/regenerate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {}),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Segment regeneration failed: ${res.statusText}`);
    }
    return res.json();
  },

  async deleteTranscriptToAudioSegment(taskId: string, segmentId: string): Promise<ToolkitTask> {
    const res = await fetch(
      `${API_BASE}/toolkit/transcript-to-audio/tasks/${taskId}/segments/${segmentId}`,
      {
        method: 'DELETE',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Segment deletion failed: ${res.statusText}`);
    }
    return res.json();
  },

  getTaskBundleUrl(taskId: string): string {
    return `${API_BASE}/toolkit/tasks/${taskId}/bundle`;
  },

  async getTranslationLanguages(): Promise<TranslationLanguagePair[]> {
    const res = await fetch(`${API_BASE}/toolkit/translation/languages`);
    if (!res.ok) {
      throw new Error(`Failed to fetch translation languages: ${res.statusText}`);
    }
    return res.json();
  },

  async getToolkitTranslationProviders(): Promise<TranslationProviderInfo[]> {
    const res = await fetch(`${API_BASE}/toolkit/translation/providers`);
    if (!res.ok) {
      throw new Error(`Failed to fetch translation providers: ${res.statusText}`);
    }
    return res.json();
  },

  async translateText(data: {
    text: string;
    source_lang?: string;
    target_lang?: string;
    provider?: string;
    source_task_id?: string;
  }): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/translation/translate-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Translation failed: ${res.statusText}`);
    }
    return res.json();
  },

  async translateTranscript(data: {
    segments?: {
      segment_order: number;
      text: string;
      start_time?: number | null;
      end_time?: number | null;
    }[];
    source_lang?: string;
    target_lang?: string;
    provider?: string;
    source_task_id?: string;
    filename?: string;
  }): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/translation/translate-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Transcript translation failed: ${res.statusText}`);
    }
    return res.json();
  },

  async updateToolkitTranslationSegment(
    taskId: string,
    segmentId: string,
    data: { text: string }
  ): Promise<ToolkitTranslationSegment> {
    const res = await fetch(
      `${API_BASE}/toolkit/translation/tasks/${taskId}/segments/${segmentId}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Segment update failed: ${res.statusText}`);
    }
    return res.json();
  },

  async retryToolkitTranslationSegment(
    taskId: string,
    segmentId: string
  ): Promise<ToolkitTranslationSegment> {
    const res = await fetch(
      `${API_BASE}/toolkit/translation/tasks/${taskId}/segments/${segmentId}/retry`,
      {
        method: 'POST',
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Segment re-translation failed: ${res.statusText}`);
    }
    return res.json();
  },

  async convertSubtitle(data: {
    content?: string;
    source_task_id?: string;
    source_format: string;
    target_format: string;
    filename?: string;
  }): Promise<SubtitleConvertResponse> {
    const res = await fetch(`${API_BASE}/toolkit/subtitle/convert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Subtitle conversion failed: ${res.statusText}`);
    }
    return res.json();
  },

  // ---------------- Video Downloader (Phase 13F) ----------------
  async inspectDownloaderUrl(url: string): Promise<VideoDownloaderMetadata> {
    const res = await fetch(`${API_BASE}/toolkit/downloader/info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to inspect video URL: ${res.statusText}`);
    }
    return res.json();
  },

  async startDownloaderTask(payload: VideoDownloaderStartPayload): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/downloader/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to start video download: ${res.statusText}`);
    }
    return res.json();
  },

  async cancelDownloaderTask(taskId: string): Promise<{ task_id: string; status: string; message: string }> {
    const res = await fetch(`${API_BASE}/toolkit/downloader/${taskId}/cancel`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to cancel download: ${res.statusText}`);
    }
    return res.json();
  },

  async importDownloaderTaskToDubbing(
    taskId: string,
    payload?: VideoDownloaderImportDubbingPayload
  ): Promise<VideoDownloaderImportDubbingResponse> {
    const res = await fetch(`${API_BASE}/toolkit/downloader/${taskId}/import-dubbing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to import video into dubbing: ${res.statusText}`);
    }
    return res.json();
  },

  async handoffDownloaderTask(taskId: string, targetTool: string): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/downloader/${taskId}/handoff`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_tool: targetTool }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to transfer media to ${targetTool}: ${res.statusText}`);
    }
    return res.json();
  },

  // ---------------- Media Trimmer (Phase 13G) ----------------
  async inspectTrimmerMedia(
    file?: File | null,
    sourceTaskId?: string | null,
    sourceProjectId?: string | null
  ): Promise<TrimmerMediaInfo> {
    const formData = new FormData();
    if (file) {
      formData.append('file', file);
    }
    if (sourceTaskId) {
      formData.append('source_task_id', sourceTaskId);
    }
    if (sourceProjectId) {
      formData.append('source_project_id', sourceProjectId);
    }

    const res = await fetch(`${API_BASE}/toolkit/trimmer/info`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to inspect media: ${res.statusText}`);
    }
    return res.json();
  },

  async getTrimmerThumbnails(payload: TrimmerThumbnailsPayload): Promise<string[]> {
    const res = await fetch(`${API_BASE}/toolkit/trimmer/thumbnails`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      return [];
    }
    const data = await res.json();
    return data.thumbnails || [];
  },

  async executeTrim(payload: TrimmerTrimPayload): Promise<ToolkitTask> {
    const formData = new FormData();
    formData.append('tool_type', payload.tool_type);
    formData.append('start_time', payload.start_time);
    formData.append('end_time', payload.end_time);
    formData.append('trim_mode', payload.trim_mode);
    if (payload.target_format) {
      formData.append('target_format', payload.target_format);
    }
    if (payload.cached_upload_path) {
      formData.append('cached_upload_path', payload.cached_upload_path);
    }
    if (payload.source_task_id) {
      formData.append('source_task_id', payload.source_task_id);
    }
    if (payload.source_project_id) {
      formData.append('source_project_id', payload.source_project_id);
    }
    if (payload.file) {
      formData.append('file', payload.file);
    }

    const res = await fetch(`${API_BASE}/toolkit/trimmer/trim`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to trim media: ${res.statusText}`);
    }
    return res.json();
  },

  async importTrimmerToDubbing(
    taskId: string,
    payload?: TrimmerImportDubbingPayload
  ): Promise<VideoDownloaderImportDubbingResponse> {
    const res = await fetch(`${API_BASE}/toolkit/trimmer/${taskId}/import-dubbing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to import trimmed video into dubbing: ${res.statusText}`);
    }
    return res.json();
  },

  async handoffTrimmerTask(taskId: string, targetTool: string): Promise<ToolkitTask> {
    const res = await fetch(`${API_BASE}/toolkit/trimmer/${taskId}/handoff`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_tool: targetTool }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to transfer media to ${targetTool}: ${res.statusText}`);
    }
    return res.json();
  },

  async cancelTrimmerTask(taskId: string): Promise<{ status: string; task_id: string }> {
    const res = await fetch(`${API_BASE}/toolkit/trimmer/${taskId}/cancel`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to cancel trimming: ${res.statusText}`);
    }
    return res.json();
  },
};
