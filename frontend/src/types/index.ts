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
  pipeline_version?: string;
  created_at: string;
  updated_at: string;
}

export interface TranscriptSegment {
  source_word_ids?: string[];
  source_audio_reference?: string | null;
  duration_seconds?: number | null;
  id: string;
  segment_order: number;
  start_time: number;
  end_time: number;
  text: string;
  is_approximate?: boolean;
  is_manually_edited?: boolean;
  dubbing_unit_id?: string | null;
  speaker_label?: string | null;
  created_at?: string;
}

export interface TranscriptResponse {
  project_id: string;
  status: ProjectStatus;
  segmentation_mode?: string;
  segments: TranscriptSegment[];
}

export interface SegmentationPreviewItem {
  segment_order: number;
  start_time: number;
  end_time: number;
  duration: number;
  text: string;
  is_approximate: boolean;
}

export interface SegmentationPreviewResponse {
  project_id: string;
  current_mode: string;
  requested_mode: string;
  current_segment_count: number;
  proposed_segment_count: number;
  proposed_segments: SegmentationPreviewItem[];
  has_user_edits: boolean;
  has_translations: boolean;
  translation_count: number;
  has_audio: boolean;
  audio_count: number;
  has_exported_video: boolean;
  requires_confirmation: boolean;
  impact_warning?: string | null;
}

export interface SegmentationApplyResponse {
  project_id: string;
  segmentation_mode: string;
  segment_count: number;
  message: string;
  segments: TranscriptSegment[];
  invalidated_translations: number;
  invalidated_audios: number;
}

export interface TranslationSegment {
  voice_override_provider?: string | null;
  voice_override_id?: string | null;
  effective_tts_provider?: string | null;
  effective_tts_voice?: string | null;
  voice_revision?: number;
  tts_error?: string | null;
  speaker_label?: string | null;
  id: string;
  project_id: string;
  transcript_segment_id?: string | null;
  segment_order: number;
  khmer_text: string;
  english_text?: string | null;
  start_time?: number | null;
  end_time?: number | null;
  source_segment_ids?: string[] | null;
  source_text?: string | null;
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
  voice_revision?: number | null;
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

export interface AudioStatusSummary {
  total_dubbing_units: number;
  current: number;
  outdated: number;
  missing: number;
  generating?: number;
  failed?: number;
}

export interface ScheduledSpeechUnit {
  local_overflow_seconds: number;
  alignment_delay_seconds: number;
  translation_segment_id: string;
  segment_order: number;
  scheduled_start: number;
  scheduled_end: number;
  processed_duration: number;
  tempo_factor: number;
  status: string;
  overflow_seconds: number;
}

export interface TimingSummary {
  schedule?: ScheduledSpeechUnit[];
  alignment_review_units?: number;
  total_segments: number;
  fitted_naturally?: number;
  fitted_without_changes?: number;
  speed_adjusted?: number;
  sentence_optimized?: number;
  automatically_optimized: number;
  synchronized_successfully?: number;
  unresolved_conflicts: number;
  status: 'ready' | 'review_required' | 'speech_generation_required' | string;
  audio_status?: AudioStatusSummary | null;
  speech_required_message?: string;
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
  timing_summary?: TimingSummary | null;
  audio_status?: AudioStatusSummary | null;
  pipeline_version?: string;
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
  language?: string;
  availability_reason?: string | null;
  provider: string;
  voice: string;
  label: string;
  gender: 'male' | 'female' | 'neutral' | string;
  description: string;
  sample_rate?: number;
  is_custom?: boolean;
  profile_id?: string;
  is_available?: boolean;
}

export interface VoiceListResponse {
  voices: VoiceOption[];
  default_provider: string;
  default_voice: string;
}

export interface ProjectSpeaker {
  id: string;
  project_id: string;
  speaker_label: string;
  display_name: string;
  detected_gender: 'male' | 'female' | 'unknown' | string;
  average_pitch_hz?: number | null;
  color: string;
  assigned_voice_provider?: string | null;
  assigned_voice_id?: string | null;
  segment_count: number;
  total_duration: number;
  created_at: string;
  updated_at: string;
}

export interface DiarizationRunResponse {
  project_id: string;
  speakers_detected: number;
  speakers: ProjectSpeaker[];
  assigned_segments_count: number;
  message: string;
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

export interface VoiceConsent {
  id: string;
  speaker_name: string;
  authorized_by: string;
  consent_statement: string;
  signature_hash: string;
  granted_at: string;
}

export interface VoiceProfile {
  id: string;
  name: string;
  description?: string | null;
  gender: string;
  language: string;
  reference_audio_duration?: number | null;
  reference_audio_sample_rate?: number | null;
  reference_transcript?: string | null;
  audio_format: string;
  is_active: boolean;
  is_library?: boolean;
  project_id?: string | null;
  consent: VoiceConsent;
  created_at: string;
  updated_at: string;
  model_status: string;
}

export interface VoiceStudioData {
  system_voices: VoiceOption[];
  custom_profiles: VoiceProfile[];
  total_custom_profiles: number;
  cloning_engine_status: string;
  default_provider: string;
  default_voice: string;
}

export interface CreateVoiceProfilePayload {
  name: string;
  description?: string;
  gender: string;
  speaker_name: string;
  authorized_by: string;
  consent_confirmed: boolean;
  reference_transcript?: string;
  file: File;
}

export interface UpdateVoiceProfilePayload {
  name?: string;
  description?: string;
  gender?: string;
  reference_transcript?: string;
}

export interface CloneCandidate {
  candidate_id: string;
  segment_order: number;
  segment_ids: string[];
  start_time: number;
  end_time: number;
  duration: number;
  text: string;
  score: number;
  preview_url: string;
}

export interface CloneCandidatesListResponse {
  project_id: string;
  candidates: CloneCandidate[];
  recommended_candidate_id?: string | null;
}

export interface CloneFromVideoRequest {
  segment_id?: string;
  start_time?: number;
  end_time?: number;
  voice_name?: string;
  set_as_project_voice?: boolean;
  store_in_voice_studio?: boolean;
}

export interface CloneSpeakerVoiceRequest {
  speaker_label?: string | null;
  store_in_voice_studio?: boolean;
}

export interface ClonedSpeakerItem {
  speaker_label: string;
  display_name: string;
  voice_profile_id: string;
  voice_profile_name: string;
  assigned_voice_provider: string;
  is_library: boolean;
}

export interface CloneSpeakerVoiceResponse {
  project_id: string;
  cloned_speakers: ClonedSpeakerItem[];
  created_profiles_count: number;
  message: string;
}

export interface AutoDiarizeAndCloneRequest {
  min_speakers?: number;
  max_speakers?: number;
  store_in_voice_studio?: boolean;
}

export interface AutoDiarizeAndCloneResponse {
  project_id: string;
  speakers_detected: number;
  cloned_voices_count: number;
  speakers: ProjectSpeaker[];
  cloned_speakers: ClonedSpeakerItem[];
  message: string;
}

export type ToolkitTargetFormat = 'mp3' | 'wav' | 'm4a' | 'srt' | 'vtt' | 'txt' | 'json' | 'csv' | string;

export interface ToolkitAudioMetadata {
  duration_seconds: number;
  codec_name: string;
  sample_rate: number;
  channels: number;
  bit_rate?: number | null;
  channel_layout?: string | null;
  file_size_bytes?: number;
}

export interface ToolkitVideoMetadata {
  duration_seconds: number;
  width: number;
  height: number;
  video_codec?: string;
  audio_codec?: string;
  audio_sample_rate?: number;
  audio_channels?: number;
  file_size_bytes?: number;
}

export interface ToolkitTranscriptSegment {
  id: string;
  task_id: string;
  segment_order: number;
  start_time: number;
  end_time: number;
  raw_text: string;
  edited_text?: string | null;
  text: string;
  is_edited: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmotionStyleOption {
  id: string;
  label_km: string;
  label_en: string;
  category: string;
  icon: string;
  description: string;
  prosody: {
    rate?: string;
    pitch?: string;
    volume?: string;
  };
  translation_guidance?: string;
}

export interface ToolkitTTSSegment {
  id: string;
  task_id: string;
  segment_order: number;
  text: string;
  start_time?: number | null;
  end_time?: number | null;
  voice?: string | null;
  provider?: string | null;
  emotion_style?: string | null;
  audio_file_path?: string | null;
  duration_seconds?: number | null;
  file_size_bytes?: number | null;
  status: 'pending' | 'completed' | 'failed' | 'fit' | 'padded' | 'sped_up' | 'slowed' | 'overflow' | string;
  error_message?: string | null;
  slot_sec?: number | null;
  raw_duration_sec?: number | null;
  final_duration_sec?: number | null;
  speed_factor_applied?: number | null;
  method?: 'native_rate' | 'atempo' | 'none' | string | null;
  padded_sec?: number | null;
  fill_mode?: 'natural' | 'stretch' | string | null;
  warning?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TimingConflictItem {
  segment_order: number;
  transcript_segment_id: string;
  start_time: number;
  end_time: number;
  original_duration: number;
  khmer_duration: number;
  available_window: number;
  effective_window: number;
  tempo_factor: number;
  overflow_seconds: number;
  suggested_action: string;
  message: string;
}

export interface ParsedTranscriptCue {
  segment_order: number;
  text: string;
  start_time?: number | null;
  end_time?: number | null;
  voice?: string | null;
  provider?: string | null;
  emotion_style?: string | null;
}

export interface ParsedTranscriptResponse {
  format: string;
  has_timestamps: boolean;
  source_task_id?: string;
  source_filename?: string;
  segments: ParsedTranscriptCue[];
  warnings: string[];
}

export interface TTSVoiceOption {
  provider: string;
  voice: string;
  label: string;
  gender: string;
  language: string;
  description?: string;
  sample_rate?: number;
  is_custom: boolean;
  profile_id?: string;
  is_available: boolean;
}

export interface ToolkitTranslationSegment {
  id: string;
  task_id: string;
  segment_order: number;
  start_time?: number | null;
  end_time?: number | null;
  source_text: string;
  translated_text: string;
  edited_text?: string | null;
  text: string;
  is_edited: boolean;
  status: 'pending' | 'translating' | 'completed' | 'failed' | string;
  error_message?: string | null;
  estimated_duration_seconds?: number | null;
  is_overflow_risk?: boolean;
  created_at: string;
  updated_at: string;
}

export interface TranslationLanguagePair {
  source_lang: string;
  target_lang: string;
  source_name: string;
  target_name: string;
  verified: boolean;
}

export interface SubtitleConvertResponse {
  success: boolean;
  source_format: string;
  target_format: string;
  segment_count: number;
  filename: string;
  content: string;
}

export interface TranscriptToTextRequest {
  content?: string;
  source_task_id?: string;
  filename?: string;
  paragraph_mode?: 'smart_paragraphs' | 'continuous' | 'line_by_line' | 'timestamped';
  speaker_handling?: 'strip' | 'keep';
  pause_threshold_seconds?: number;
  deduplicate_phrases?: boolean;
  strip_tags?: boolean;
  target_format?: 'txt' | 'md' | 'json';
  title?: string;
}

export interface ToolkitTask {
  id: string;
  tool_type: string;
  source_type: 'upload' | 'project' | 'direct_text' | 'imported_transcript' | 'imported_translation' | string;
  source_project_id?: string | null;
  source_task_id?: string | null;
  is_outdated?: boolean;
  source_filename: string;
  source_file_path?: string | null;
  target_format: ToolkitTargetFormat | string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled' | 'cancelling';
  progress_percentage: number;
  output_filename?: string | null;
  output_duration_seconds?: number | null;
  output_file_size_bytes?: number | null;
  source_media_metadata?: Record<string, any> | null;
  output_media_metadata?: Record<string, any> | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  segments?: ToolkitTranscriptSegment[];
  tts_segments?: ToolkitTTSSegment[];
  translation_segments?: ToolkitTranslationSegment[];
  full_text?: string | null;
}


export interface ToolkitToolItem {
  id: string;
  title: string;
  description: string;
  category: string;
  status: 'available' | 'planned';
  phase: string;
  supported_formats: string[];
}

export interface ToolkitCapabilities {
  version: string;
  tools: ToolkitToolItem[];
  language_capabilities: {
    transcription: Record<string, string>;
    translation: Record<string, string>;
    speech_synthesis: Record<string, string>;
  };
}

export interface VideoDownloaderMetadata {
  url: string;
  title: string;
  source_platform: string;
  uploader?: string | null;
  duration_seconds?: number | null;
  thumbnail_url?: string | null;
  available_video_qualities: string[];
  available_audio_formats: string[];
  estimated_file_size_bytes?: number | null;
  is_audio_only_source?: boolean;
  notice?: string;
}

export interface VideoDownloaderStartPayload {
  url: string;
  output_type: 'video' | 'audio';
  quality: string;
  audio_format: string;
  rights_confirmed?: boolean;
}

export interface VideoDownloaderImportDubbingPayload {
  title?: string;
  original_language?: string;
  target_language?: string;
}

export interface VideoDownloaderImportDubbingResponse {
  success: boolean;
  project_id: string;
  title: string;
  status: string;
  duration?: number | null;
}

// ---------------- Media Trimmer (Phase 13G) ----------------
export interface TrimmerMediaInfo {
  duration_seconds: number;
  formatted_duration: string;
  has_video: boolean;
  has_audio: boolean;
  video_codec?: string | null;
  audio_codec?: string | null;
  width?: number | null;
  height?: number | null;
  size_bytes: number;
  format_name: string;
  waveform_peaks: number[];
  peaks?: number[];
  source_filename: string;
  source_type: string;
  source_task_id?: string | null;
  source_project_id?: string | null;
  cached_upload_path?: string | null;
}

export interface TrimmerTrimPayload {
  tool_type: 'video_trimmer' | 'audio_trimmer';
  start_time: string;
  end_time: string;
  trim_mode: 'fast' | 'precise';
  target_format?: string;
  cached_upload_path?: string;
  source_task_id?: string;
  source_project_id?: string;
  file?: File;
}

export interface TrimmerThumbnailsPayload {
  source_task_id?: string;
  source_project_id?: string;
  cached_upload_path?: string;
  count?: number;
}

export interface TrimmerImportDubbingPayload {
  title?: string;
}

// ---------------- Storage Management ----------------
export interface StorageDiskInfo {
  total_bytes: number;
  total_human: string;
  used_bytes: number;
  used_human: string;
  free_bytes: number;
  free_human: string;
  used_percent: number;
  free_percent: number;
}

export interface StorageCategoryInfo {
  category: string;
  label: string;
  size_bytes: number;
  size_human: string;
  item_count?: number | null;
  path: string;
  is_protected: boolean;
  cleanable: boolean;
  cleanable_bytes?: number | null;
  cleanable_human?: string | null;
  description?: string | null;
  details?: Record<string, any> | null;
}

export interface StorageUsageResponse {
  disk: StorageDiskInfo;
  categories: Record<string, StorageCategoryInfo>;
  total_data_bytes: number;
  total_data_human: string;
  total_cleanable_bytes: number;
  total_cleanable_human: string;
}

export interface StorageCleanRequest {
  targets: string[];
  older_than_days?: number;
}

export interface StorageCleanResponse {
  success: boolean;
  freed_bytes: number;
  freed_human: string;
  targets_processed: string[];
  details: Record<string, any>;
  storage: StorageUsageResponse;
}






