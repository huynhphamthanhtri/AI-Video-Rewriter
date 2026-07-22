export type PresetIntent = {
  rewrite_style: string;
  tone: string;
  target_audience: string;
};

export type PresetStrategy = {
  retention_mode: string;
  hook_style: string;
  clip_strategy: string;
  reuse_level: string;
  content_density: string;
};

export type PresetConstraints = {
  target_duration: string;
  target_language: string;
  target_market: string;
  localization_level: 'none' | 'light' | 'medium' | 'heavy';
  rename_characters: boolean;
  adapt_culture: boolean;
  adapt_currency: boolean;
  adapt_units: boolean;
  adapt_company_names: boolean;
  adaptation_mode: 'faithful' | 'localized' | 'inspired';
  narrator_persona: string;
};

export type Preset = {
  id: string;
  name: string;
  description: string;
  rewrite_style: string;
  target_audience: string;
  tone: string;
  target_duration: string;
  retention_mode: string;
  hook_style: string;
  clip_strategy: string;
  reuse_level: string;
  content_density: string;
  target_language: string;
  target_market: string;
  localization_level: 'none' | 'light' | 'medium' | 'heavy';
  rename_characters: boolean;
  adapt_culture: boolean;
  adapt_currency: boolean;
  adapt_units: boolean;
  adapt_company_names: boolean;
  adaptation_mode: 'faithful' | 'localized' | 'inspired';
  narrator_persona: 'neutral_narrator' | 'funny_friend' | 'drama_storyteller' | 'movie_reviewer' | 'news_anchor' | 'expert_analyst' | 'detective' | 'teacher' | 'podcast_host' | 'tech_reviewer' | 'investor';
  is_builtin: boolean;
  preset_schema_version: number;
  prompt_template_version: number;
  json_output_schema_version: number;
};

export function presetIntent(p: Preset): PresetIntent {
  return { rewrite_style: p.rewrite_style, tone: p.tone, target_audience: p.target_audience };
}

export function presetStrategy(p: Preset): PresetStrategy {
  return { retention_mode: p.retention_mode, hook_style: p.hook_style, clip_strategy: p.clip_strategy, reuse_level: p.reuse_level, content_density: p.content_density };
}

export function presetConstraints(p: Preset): PresetConstraints {
  return {
    target_duration: p.target_duration, target_language: p.target_language,
    target_market: p.target_market, localization_level: p.localization_level,
    rename_characters: p.rename_characters, adapt_culture: p.adapt_culture,
    adapt_currency: p.adapt_currency, adapt_units: p.adapt_units,
    adapt_company_names: p.adapt_company_names, adaptation_mode: p.adaptation_mode,
    narrator_persona: p.narrator_persona,
  };
}

export type PromptHealthDetail = {
  factor: string;
  label: string;
  value: string;
  impact: number;
  reason: string;
};

export type PromptHealthResponse = {
  score: number;
  level: 'excellent' | 'good' | 'risky' | 'weak';
  warnings: string[];
  strengths: string[];
  details: PromptHealthDetail[];
};

export type PromptPreviewSection = {
  title: string;
  start: number;
  end: number;
  excerpt: string;
};

export type PromptPreviewResponse = {
  preview_text: string;
  full_length: number;
  estimated_tokens: number;
  sections: PromptPreviewSection[];
};

export type PromptForm = {
  source_mode: 'single' | 'multi';
  youtube_url: string;
  youtube_urls_text: string;
  ytdlp_cookies_file: string;
  target_language: string;
  user_instruction: string;
  output_dir_name?: string;
  output_dir_path?: string;
};

export type SrtItem = { index: number; start: string; end: string; text: string; tts_text?: string };

export type VideoSegment = {
  segment_id: number;
  order: number;
  source_id?: string;
  source_start: string;
  source_end: string;
  subtitle_start: number;
  subtitle_end: number;
  scene_description: string;
};

export type GeminiEdlPayload = {
  metadata: { video_title: string; rewrite_style: string; target_audience: string; tone: string; target_duration: string; target_language?: string; target_market?: string; localization_level?: string; adaptation_mode?: string; narrator_persona?: string };
  sources?: { source_id: string; youtube_url?: string | null; local_video_path?: string | null; label?: string }[];
  rewrite_script: { full_text: string };
  srt: SrtItem[];
  video_segments: VideoSegment[];
};

export type RenderJobStart = { job_id: string; status: string; message: string };
export type VerticalMode = 'none' | 'blur_fit' | 'center_crop';
export type RenderQuality = 'fast' | 'balanced' | 'high';
export type OutputResolution = 'auto' | '720p' | '1080p';
export type SubtitleMode = 'burn' | 'srt_only' | 'none';
export type RenderOptions = {
  vertical_mode: VerticalMode;
  render_quality: RenderQuality;
  output_resolution: OutputResolution;
  render_stability: 'fast' | 'stable' | 'max_quality';
  video_encoder: 'auto' | 'cpu' | 'nvenc' | 'qsv' | 'amf';
  segment_fps: 'auto' | '30' | '60';
  blur_mode: 'none' | 'review';
  tts_mode: 'none' | 'voiceover';
  tts_engine: 'edge_tts';
  tts_persona: 'neutral' | 'sports_commentator' | 'drama_storyteller' | 'news_anchor' | 'funny_reviewer' | 'podcast_host';
  tts_voice_region: 'auto' | 'vi_north' | 'vi_south';
  tts_voice_gender: 'auto' | 'female' | 'male';
  tts_voice_id: 'auto' | 'vi-VN-HoaiMyNeural' | 'vi-VN-NamMinhNeural' | 'en-US-JennyNeural' | 'en-US-GuyNeural'
    | 'de-DE-KatjaNeural' | 'de-DE-ConradNeural' | 'ja-JP-NanamiNeural' | 'ja-JP-KeitaNeural'
    | 'es-MX-DaliaNeural' | 'es-MX-JorgeNeural' | 'ko-KR-SunHiNeural' | 'ko-KR-InJoonNeural';
  tts_voice_mode: 'preset';
  tts_clone_voice_id: string;
  tts_emotion: 'natural' | 'storytelling';
  tts_fit_policy: 'segment_uniform';
  tts_max_speed: number;
  tts_temperature: number;
  tts_top_k: number;
  tts_max_chars: number;
  tts_apply_watermark: boolean;
  original_audio_mode: 'lower_fixed' | 'mute';
  original_audio_volume: number;
  voiceover_volume: number;
  title_mode: 'none' | 'auto' | 'custom';
  title_text: string;
  title_style: 'yellow_highlight' | 'dark_badge' | 'clean_white' | 'breaking_yellow';
  title_font_size: 'auto' | 'small' | 'medium' | 'large';
  title_max_lines: number;
  title_chars_per_line: number;
  title_position: 'top' | 'upper_third' | 'center' | 'bottom';
  title_text_align: 'left' | 'center' | 'right';
  title_show_duration: 'full' | 'intro_only';
  title_intro_seconds: number;
  title_badge_mode: 'none' | 'auto' | 'custom';
  title_badge_text: string;
  title_header_height: number;
  title_safe_margin: number;
  subtitle_style: 'default' | 'shorts_bold' | 'documentary' | 'minimal' | 'news' | 'high_contrast';
  subtitle_font_size: 'auto' | 'small' | 'medium' | 'large';
  subtitle_position: 'bottom' | 'center' | 'top';
  subtitle_text_align: 'center' | 'left';
  subtitle_max_chars_per_line: number;
  subtitle_outline: boolean;
  subtitle_shadow: boolean;
  subtitle_box: boolean;
  artifact_retention: 'smart' | 'keep_all';
  video_speed: number;
};
export type ValidateJsonResponse = { valid: boolean; errors: string[]; warnings?: string[]; fixed_payload?: GeminiEdlPayload | null };
export type RenderJobStatus = {
  job_id: string;
  status: 'queued' | 'running' | 'waiting_blur' | 'done' | 'error' | 'cancelled';
  step: string;
  message: string;
  progress?: number;
  total_segments?: number | null;
  completed_segments?: number;
  started_at?: number | null;
  updated_at?: number | null;
  elapsed_seconds?: number | null;
  estimated_total_seconds?: number | null;
  remaining_seconds?: number | null;
  result?: Record<string, string> | null;
  errors: string[];
};

export type StorageStats = { outputs_size_bytes: number; temp_size_bytes: number; outputs_count: number; temp_count: number };
export type StorageCleanupResponse = { target: 'temp' | 'outputs' | 'all'; dry_run: boolean; matched_count: number; deleted_count: number; freed_bytes: number; items: string[] };

export type PresetSyncStatus = {
  expected_count: number;
  db_builtin_count: number;
  missing: { id: string; name: string }[];
  outdated: { id: string; name: string; fields: string[] }[];
  extra_builtin_ids: string[];
  in_sync: boolean;
};

export type RuntimeHealth = {
  pid: number;
  backend_started_at: number;
  python_executable: string;
  tts_status: { status: string; engine: string; message: string };
  video_encoder_auto_result: { selected?: string; label?: string; codec?: string; hardware?: boolean; error?: string };
  preset_sync_status: PresetSyncStatus;
};

export type LicenseStatus = {
  licensed: boolean;
  status: string;
  message: string;
  hardware_id: string;
  enforcement: boolean;
  plan?: string | null;
  expires_at?: string | null;
  customer_name?: string | null;
  customer_email?: string | null;
  license_id?: string | null;
  license_key_hint?: string | null;
  cache_status?: 'fresh' | 'stale' | 'offline' | null;
  features: Record<string, boolean>;
};

export type BlurKeyframe = { time: number; x: number; y: number; width: number; height: number; strength: number };
export type BlurRegion = { start: number; end: number; keyframes: BlurKeyframe[]; interpolate: boolean };
export type BlurUploadResponse = { message: string; video_path: string; preview_url: string; width?: number | null; height?: number | null; duration_seconds?: string | null };
export type BlurRenderResponse = { message: string; final_video_path: string; output_dir: string; video_encoder?: string | null; video_encoder_label?: string | null; video_encoder_codec?: string | null; output_codec?: string | null; output_fps?: string | null; output_resolution_actual?: string | null; output_duration_seconds?: string | null; output_file_size_bytes?: string | null };

export type TtsVoice = { id: string; label: string; description: string; gender: 'female' | 'male'; region?: string; languages: string[]; recommended_for?: string[]; rank?: number; best_for?: string; locale?: string };

export interface TitleLinePreview {
  text: string;
  x_px: number;
  y_px: number;
  font_size: number;
  font_color: string;
  width_px: number;
  height_px: number;
  has_background: boolean;
  background_color: string | null;
}

export interface TitleBadgePreview {
  text: string;
  x_px: number;
  y_px: number;
  font_size: number;
  font_color: string;
  width_px: number;
  height_px: number;
  has_background: boolean;
  background_color: string | null;
}

export interface TitleLayoutPreviewResponse {
  lines: TitleLinePreview[];
  badge: TitleBadgePreview | null;
  header_drawbox: string[] | null;
  safe_margin_px: number;
  header_height_px: number;
}

export type PresetCompareDiff = {
  group: string;
  field: string;
  left: string | number | boolean;
  right: string | number | boolean;
};

export type PresetCompareResponse = {
  left_name: string;
  right_name: string;
  same: string[];
  different: PresetCompareDiff[];
};

export interface PresetRecommendationItem {
  preset_name: string;
  confidence: number;
  confidence_label: 'strong' | 'medium' | 'weak' | 'none';
  matched_keywords: string[];
}

export interface PresetRecommendResponse {
  title: string | null;
  title_source: 'provided' | 'extracted' | 'none';
  recommendations: PresetRecommendationItem[];
}

export interface PromptRunStats {
  total_runs: number;
  success_count: number;
  error_count: number;
  avg_health_score: number | null;
  top_presets: { name: string; count: number }[];
  top_rewrite_styles: { style: string; count: number }[];
  daily_counts: { date: string; count: number; avg_health: number | null }[];
  last_7d_count: number;
  prev_7d_count: number;
}

export interface SubtitleStyleCss {
  font_family: string;
  font_size_px: number;
  color: string;
  outline_color: string;
  outline_width_px: number;
  shadow_color: string;
  shadow_offset_px: number;
  background_color: string;
  text_align: string;
}

export interface SubtitleStylePreviewItem {
  key: string;
  label: string;
  description: string;
  css: SubtitleStyleCss;
}

export interface SubtitlePreviewStyleResponse {
  styles: SubtitleStylePreviewItem[];
}

export interface UpdateCheckResponse {
  local_version: string;
  remote_version: string;
  channel: string;
  update_available: boolean;
  notes: string[];
  download_url: string;
  message: string;
}

export interface UpdateLaunchResponse {
  started: boolean;
  message: string;
}

export type AutoPipelineStateEntry = {
  step: string;
  label: string;
  status: 'running' | 'done' | 'error';
  start_ts: number;
  end_ts: number | null;
};

export type AutoPipelineProgress = {
  task_id: string;
  step: string;
  status: 'running' | 'done' | 'error';
  message: string | null;
  detail: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  states?: AutoPipelineStateEntry[];
};

export type GeminiAutoSubmitResponse = {
  task_id: string;
  prompt_text: string;
};

export type GeminiSessionStatus = {
  exists: boolean;
  session_file_exists?: boolean;
  has_auth_cookies?: boolean;
  live_checked?: boolean;
  needs_login?: boolean;
  browser_open?: boolean;
  browser_id?: string | null;
  path: string;
  message?: string;
  method?: string;
};

export type GeminiThinkingMode = 'standard' | 'extended';

export type GeminiModelOption = {
  key: string;
  label: string;
};

export type GeminiModelsResponse = {
  default_model: string;
  models: GeminiModelOption[];
};

export type GeminiOpenBrowserResponse = {
  browser_id: string;
  message: string;
  user_data_dir?: string | null;
};

export type BatchItemProgress = {
  index: number;
  source_url: string;
  status: 'pending' | 'running' | 'done' | 'error' | 'cancelled';
  task_id?: string | null;
  job_id?: string | null;
  states: AutoPipelineStateEntry[];
  result?: Record<string, unknown> | null;
  error?: string | null;
  render_status?: RenderJobStatus | null;
  started_at?: number | null;
  ended_at?: number | null;
};

export type BatchProgress = {
  batch_id: string;
  status: 'pending' | 'running' | 'done' | 'error' | 'cancelled';
  total_items: number;
  current_index: number;
  items: BatchItemProgress[];
  started_at?: number | null;
  ended_at?: number | null;
  error?: string | null;
};

