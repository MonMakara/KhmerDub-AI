import {
  HealthResponse,
  ProjectSummary,
  ProjectDetail,
  ProcessingJob,
  TranscriptResponse,
  TranscriptSegment,
  TranslationSegment,
  TranslationListResponse,
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
};
