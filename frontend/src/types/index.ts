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
  | 'failed'
  | 'deleting';

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
  audio_timeline_path?: string | null;
  exported_video_path?: string | null;
  exported_duration_seconds?: number | null;
  exported_file_size_bytes?: number | null;
  is_export_outdated?: boolean;
  created_at: string;
}

export interface ProjectSummary {
  id: string;
  title: string;
  original_language: string;
  target_language: string;
  translation_provider?: string;
  translation_style?: string;
  tts_provider?: string;
  tts_voice?: string;
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
  style?: string | null;
  explanation?: string | null;
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

export interface GeneratedAudio {
  id: string;
  project_id: string;
  translation_segment_id?: string | null;
  segment_order?: number | null;
  khmer_text?: string | null;
  audio_path: string;
  duration_seconds?: number | null;
  provider: string;
  voice: string;
  is_outdated: boolean;
  created_at: string;
  updated_at?: string | null;
  audio_url?: string | null;
}

export interface GeneratedAudioListResponse {
  project_id: string;
  status: ProjectStatus;
  audios: GeneratedAudio[];
  total_duration_seconds: number;
}

export interface TimingConflict {
  segment_order: number;
  transcript_segment_id: string;
  start_time: number;
  end_time: number;
  original_duration: number;
  khmer_duration: number;
  available_window: number;
  effective_window: number;
  safety_margin_seconds: number;
  required_tempo: number;
  max_tempo_factor: number;
  tempo_factor: number;
  overflow_seconds: number;
  suggested_action: string;
  message: string;
}

export interface ExportStatusResponse {
  project_id: string;
  status: ProjectStatus;
  job?: ProcessingJob | null;
  is_export_ready: boolean;
  is_export_outdated: boolean;
  exported_video_path?: string | null;
  audio_timeline_path?: string | null;
  exported_duration_seconds?: number | null;
  exported_file_size_bytes?: number | null;
  timing_conflicts: TimingConflict[];
  video_url?: string | null;
  download_url?: string | null;
}

export interface ProjectDetail extends ProjectSummary {
  original_video_path?: string | null;
  video?: VideoInfo | null;
  jobs?: ProcessingJob[];
  transcript_segments?: TranscriptSegment[];
  translation_segments?: TranslationSegment[];
  generated_audios?: GeneratedAudio[];
}

export interface VoiceOption {
  provider: string;
  voice: string;
  label: string;
  gender: 'male' | 'female' | 'neutral' | string;
  description: string;
  sample_rate?: number;
}

export interface VoiceListResponse {
  voices: VoiceOption[];
  default_provider: string;
  default_voice: string;
}

export interface VoicePreviewRequest {
  provider: string;
  voice: string;
  text?: string;
}

export interface TranslationProviderInfo {
  id: string;
  name: string;
  type: string;
  description: string;
  requires_api_key: boolean;
  is_configured: boolean;
  masked_key?: string | null;
  supports_styles: boolean;
  supports_alternatives: boolean;
  default_model: string;
  available_models: string[];
  base_url?: string | null;
  configured_model?: string | null;
  requires_base_url?: boolean;
}

export interface TranslationStyleOption {
  id: string;
  label: string;
  description: string;
}

export interface TranslationProviderListResponse {
  providers: TranslationProviderInfo[];
  default_provider: string;
  default_style: string;
  styles: TranslationStyleOption[];
}

export interface TestConnectionRequest {
  provider?: string;
  api_key?: string;
  model?: string;
  base_url?: string;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
  provider: string;
}

export interface SaveCredentialsRequest {
  provider: string;
  api_key: string;
  base_url?: string;
  model?: string;
}

export interface AIImproveRequest {
  style?: string;
  target_duration?: number;
  custom_prompt?: string;
}

export interface AIImproveResponse {
  segment_id: string;
  original_text: string;
  current_khmer_text: string;
  improved_khmer_text: string;
  explanation: string;
  style: string;
  provider: string;
  model: string;
}

export interface AlternativeOption {
  style: string;
  label: string;
  khmer_text: string;
  explanation?: string | null;
}

export interface AlternativesResponse {
  segment_id: string;
  english_text: string;
  current_khmer_text: string;
  alternatives: AlternativeOption[];
}

export interface ApplyTranslationRequest {
  khmer_text: string;
  style?: string;
  explanation?: string;
}

export interface ProjectTranslationSettingsUpdate {
  translation_provider: string;
  translation_style: string;
}

export interface ProjectDeleteResponse {
  message: string;
  id: string;
  deleted_files_count: number;
}

export interface SubtitleReadabilityMetrics {
  duration: number;
  character_count: number;
  line_count: number;
  characters_per_second: number;
  warnings: string[];
  has_warnings: boolean;
}

export interface SubtitleSegment {
  id: string;
  segment_order: number;
  start_time: number;
  end_time: number;
  text: string;
  source_text?: string | null;
  source_segment_order?: number | null;
  timing_confidence?: 'verified' | 'estimated' | 'manual';
  is_source_outdated?: boolean;
  is_customized: boolean;
  language: string;
  readability?: SubtitleReadabilityMetrics;
}

export interface SubtitleListResponse {
  project_id: string;
  language: string;
  has_custom_edits: boolean;
  total_segments: number;
  segments: SubtitleSegment[];
}

export interface SubtitleStylePreferences {
  preset: 'standard' | 'cinema' | 'custom';
  fontSize: 'sm' | 'base' | 'lg' | 'xl';
  textColor: 'white' | 'yellow' | 'cyan' | 'green';
  position: 'bottom' | 'top' | 'middle';
  bgOpacity: number;
  bottomMargin: number;
  shadow: boolean;
}

