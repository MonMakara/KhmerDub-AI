export type ProjectStatus =
  | 'created'
  | 'uploaded'
  | 'audio_extracted'
  | 'transcribing'
  | 'transcribed'
  | 'translating'
  | 'translated'
  | 'generating_voice'
  | 'voice_generated'
  | 'synchronizing'
  | 'completed'
  | 'failed';

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  environment: string;
  system_info: {
    ffmpeg_available: boolean;
    storage_ready: boolean;
    whisper_device: string;
    whisper_model: string;
    [key: string]: any;
  };
}

export interface ProcessingJob {
  id: string;
  project_id: string;
  job_type: string;
  status: JobStatus;
  progress_percentage: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VideoInfo {
  id: string;
  filename: string;
  file_path?: string | null;
  file_size_bytes: number;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  video_codec?: string | null;
  audio_codec?: string | null;
  extracted_audio_path?: string | null;
  exported_video_path?: string | null;
  created_at: string;
}

export interface ProjectSummary {
  id: string;
  title: string;
  original_language: string;
  target_language: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface TranscriptSegment {
  id: string;
  segment_order: number;
  start_time: number;
  end_time: number;
  text: string;
  created_at?: string;
}

export interface TranscriptResponse {
  project_id: string;
  status: ProjectStatus;
  segments: TranscriptSegment[];
}

export interface TranslationSegment {
  id: string;
  project_id: string;
  transcript_segment_id?: string | null;
  segment_order: number;
  khmer_text: string;
  english_text?: string | null;
  start_time?: number | null;
  end_time?: number | null;
  is_manually_edited: boolean;
  is_outdated: boolean;
  created_at: string;
  updated_at: string;
}

export interface TranslationListResponse {
  project_id: string;
  status: ProjectStatus;
  segments: TranslationSegment[];
}

export interface ProjectDetail extends ProjectSummary {
  original_video_path?: string | null;
  video?: VideoInfo | null;
  jobs?: ProcessingJob[];
  transcript_segments?: TranscriptSegment[];
  translation_segments?: TranslationSegment[];
}
