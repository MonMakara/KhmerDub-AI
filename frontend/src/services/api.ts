import {
  HealthResponse,
  ProjectSummary,
  ProjectDetail,
  ProcessingJob,
  TranscriptResponse,
  TranscriptSegment,
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
    text: string,
    language: string = 'km'
  ): Promise<SubtitleSegment> {
    const res = await fetch(
      `${API_BASE}/projects/${projectId}/subtitles/${segmentOrder}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, language }),
      }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to update subtitle: ${res.statusText}`);
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
};
