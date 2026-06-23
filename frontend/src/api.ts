import type { AutoPipelineProgress, BatchProgress, BlurRegion, BlurRenderResponse, BlurUploadResponse, GeminiAutoSubmitResponse, GeminiOpenBrowserResponse, GeminiSessionStatus, LicenseStatus, Preset, PresetCompareResponse, PresetRecommendResponse, PresetSyncStatus, PromptHealthResponse, PromptPreviewResponse, PromptRunStats, RenderJobStatus, RenderOptions, RuntimeHealth, StorageCleanupResponse, StorageStats, SubtitlePreviewStyleResponse, TitleLayoutPreviewResponse, TtsCloneVoice, TtsVoice, UpdateCheckResponse, UpdateLaunchResponse, ValidateJsonResponse } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api';
const USE_MOCK = import.meta.env.VITE_USE_MOCK_API === 'true';

const mockLocalization = { target_language: 'Tiếng Việt', target_market: 'Việt Nam', localization_level: 'medium' as const, rename_characters: true, adapt_culture: true, adapt_currency: true, adapt_units: true, adapt_company_names: false, adaptation_mode: 'localized' as const, narrator_persona: 'drama_storyteller' as const };

const mockPresets: Preset[] = [
  { id: 'mock-1', name: 'TikTok Viral 60s', description: 'Hook mạnh, nhịp nhanh.', rewrite_style: 'Viral', target_audience: 'Đại chúng', tone: 'Năng lượng cao', target_duration: '1-3 phút', retention_mode: 'Cực cao', hook_style: 'Cảnh đắt giá', clip_strategy: 'Chỉ các đoạn hay nhất', reuse_level: 'Thấp', content_density: 'Cao', ...mockLocalization, localization_level: 'heavy', narrator_persona: 'funny_friend', is_builtin: true, preset_schema_version: 1, prompt_template_version: 1, json_output_schema_version: 1 },
  { id: 'mock-2', name: 'Drama Kể Chuyện', description: 'Kể chuyện drama cuốn hút.', rewrite_style: 'Drama', target_audience: 'Đại chúng', tone: 'Hài hước', target_duration: '3-5 phút', retention_mode: 'Cao', hook_style: 'Cảnh đắt giá', clip_strategy: 'Giữ đầy đủ ngữ cảnh', reuse_level: 'Trung bình', content_density: 'Trung bình', ...mockLocalization, is_builtin: true, preset_schema_version: 1, prompt_template_version: 1, json_output_schema_version: 1 },
];

const mockJobs = new Map<string, { started: number }>();

export async function fetchPresets(): Promise<Preset[]> {
  if (USE_MOCK) return mockPresets;
  const res = await fetch(`${API_BASE}/presets`);
  if (!res.ok) throw new Error('Không tải được danh sách preset.');
  return res.json();
}

async function parseError(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) return data.detail.map((d: unknown) => {
      if (typeof d === 'string') return d;
      const loc = (d as Record<string, unknown>)?.loc as string[] | undefined;
      const msg = (d as Record<string, unknown>)?.msg as string | undefined;
      return loc ? `${loc.join('.')}: ${msg ?? ''}` : (msg ?? JSON.stringify(d));
    }).join(' | ');
    return data.detail ?? data.message ?? fallback;
  } catch {
    return fallback;
  }
}

export async function generatePrompt(payload: Record<string, unknown>): Promise<string> {
  if (USE_MOCK) return `Bạn là editor chuyên nghiệp. CẤU HÌNH NGÔN NGỮ & BẢN ĐỊA HÓA: target_language=${payload.target_language}, target_market=${payload.target_market}, localization_level=${payload.localization_level}, adaptation_mode=${payload.adaptation_mode}, narrator_persona=${payload.narrator_persona}. Hãy phân tích video ${(payload.youtube_url as string) || ''} và trả JSON EDL với metadata, rewrite_script, srt, video_segments[]. Return ONLY valid JSON.`;
  const res = await fetch(`${API_BASE}/generate-prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không tạo được prompt.'));
  const data = await res.json();
  return data.prompt;
}

export async function validateJson(payload: unknown): Promise<ValidateJsonResponse> {
  if (USE_MOCK) return { valid: Boolean(payload), errors: [] };
  const res = await fetch(`${API_BASE}/validate-json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể validate JSON.'));
  return res.json();
}

export async function uploadCookies(file: File): Promise<{ message: string; cookies_file_path: string }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/upload-cookies`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể upload cookies.txt.'));
  return res.json();
}

export async function createPreset(payload: Omit<Preset, 'id' | 'is_builtin'>): Promise<Preset> {
  if (USE_MOCK) return { ...payload, id: `mock-${Date.now()}`, is_builtin: false };
  const res = await fetch(`${API_BASE}/presets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể tạo preset.'));
  return res.json();
}

export async function updatePreset(id: string, payload: Omit<Preset, 'id' | 'is_builtin'>): Promise<Preset> {
  if (USE_MOCK) return { ...payload, id, is_builtin: false };
  const res = await fetch(`${API_BASE}/presets/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể cập nhật preset.'));
  return res.json();
}

export async function deletePreset(id: string): Promise<void> {
  if (USE_MOCK) return;
  const res = await fetch(`${API_BASE}/presets/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể xóa preset.'));
}

export async function renderVideo(payload: Record<string, unknown>): Promise<Record<string, string>> {
  const res = await fetch(`${API_BASE}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể render video.'));
  return res.json();
}

export async function startRenderJob(payload: Record<string, unknown>): Promise<{ job_id: string; status: string; message: string }> {
  if (USE_MOCK) {
    const job_id = `mock-job-${Date.now()}`;
    mockJobs.set(job_id, { started: Date.now() });
    return { job_id, status: 'queued', message: 'Mock render job đã bắt đầu.' };
  }
  const res = await fetch(`${API_BASE}/render-jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể bắt đầu render job.'));
  return res.json();
}

export async function fetchRenderJob(jobId: string): Promise<RenderJobStatus> {
  if (USE_MOCK) {
    const started = mockJobs.get(jobId)?.started ?? Date.now();
    const elapsed = Date.now() - started;
    if (elapsed < 3000) return { job_id: jobId, status: 'running', step: 'Download/Cut/Concat', message: 'Mock: đang tải và dựng video...', errors: [] };
    return { job_id: jobId, status: 'done', step: 'Export result', message: 'Mock render hoàn tất.', errors: [], result: { final_video_path: 'outputs/mock_final.mp4', final_subtitle_path: 'outputs/mock_subtitle.srt', render_plan_path: 'outputs/mock_render_plan.json', output_dir: 'outputs/mock' } };
  }
  const res = await fetch(`${API_BASE}/render-jobs/${jobId}`);
  if (!res.ok) throw new Error(await parseError(res, 'Không thể lấy trạng thái render job.'));
  return res.json();
}

export async function fetchPresetSyncStatus(): Promise<PresetSyncStatus> {
  const res = await fetch(`${API_BASE}/presets/sync-status`);
  if (!res.ok) throw new Error(await parseError(res, 'Không kiểm tra được preset sync status.'));
  return res.json();
}

export async function validatePresetConflicts(data: Record<string, unknown>): Promise<{ warnings: { field: string; message: string }[] }> {
  const res = await fetch(`${API_BASE}/presets/validate-conflicts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data }),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không validate được preset.'));
  return res.json();
}

export async function fetchPromptHealthScore(payload: Record<string, unknown>): Promise<PromptHealthResponse> {
  if (USE_MOCK) return { score: 85, level: 'excellent', warnings: [], strengths: ['Mock health score'], details: [] };
  const res = await fetch(`${API_BASE}/prompt/health-score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không tính được health score.'));
  return res.json();
}

export async function syncBuiltInPresets(): Promise<{ inserted: number; updated: number; status: PresetSyncStatus }> {
  const res = await fetch(`${API_BASE}/presets/sync`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không sync được built-in presets.'));
  return res.json();
}

export async function fetchRuntimeHealth(): Promise<RuntimeHealth> {
  const res = await fetch(`${API_BASE}/runtime/health`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được runtime health.'));
  return res.json();
}

export async function fetchLicenseStatus(): Promise<LicenseStatus> {
  const res = await fetch(`${API_BASE}/license/status`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được trạng thái license.'));
  return res.json();
}

export async function activateLicense(licenseKey: string): Promise<LicenseStatus> {
  const res = await fetch(`${API_BASE}/license/activate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ license_key: licenseKey }) });
  if (!res.ok) throw new Error(await parseError(res, 'Không kích hoạt được license.'));
  return res.json();
}

export async function clearLicense(): Promise<void> {
  const res = await fetch(`${API_BASE}/license/clear`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không xóa được license.'));
}

export async function fetchRenderJobs(): Promise<RenderJobStatus[]> {
  const res = await fetch(`${API_BASE}/render-jobs`);
  if (!res.ok) throw new Error(await parseError(res, 'Không thể lấy render history.'));
  return res.json();
}

export async function cancelRenderJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/render-jobs/${jobId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể hủy render job.'));
}

export async function fetchStorageStats(): Promise<StorageStats> {
  const res = await fetch(`${API_BASE}/storage/stats`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được thống kê dung lượng.'));
  return res.json();
}

export async function cleanupStorage(payload: { target: 'temp' | 'outputs' | 'all'; older_than_hours: number; dry_run: boolean }): Promise<StorageCleanupResponse> {
  const res = await fetch(`${API_BASE}/storage/cleanup`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!res.ok) throw new Error(await parseError(res, 'Không dọn dẹp được storage.'));
  return res.json();
}

export async function openOutputFolder(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}/open-folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
  if (!res.ok) throw new Error(await parseError(res, 'Không mở được thư mục output.'));
}

export function fileDownloadUrl(path: string): string {
  return `${API_BASE}/files/download?path=${encodeURIComponent(path)}`;
}

export function blurPreviewUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith('/api/')) return `${API_BASE.replace(/\/api$/, '')}${pathOrUrl}`;
  return `${API_BASE}/blur/preview?path=${encodeURIComponent(pathOrUrl)}`;
}

export async function uploadBlurVideo(file: File): Promise<BlurUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/blur/upload-video`, { method: 'POST', body: formData });
  if (!res.ok) throw new Error(await parseError(res, 'Không upload được video blur.'));
  return res.json();
}

export async function renderBlurVideo(payload: { video_path: string; regions: BlurRegion[] }): Promise<BlurRenderResponse> {
  const res = await fetch(`${API_BASE}/blur/render`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!res.ok) throw new Error(await parseError(res, 'Không render blur video được.'));
  return res.json();
}

export async function skipRenderJobBlur(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/render-jobs/${jobId}/blur/skip`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không bỏ qua blur được.'));
}

export async function applyRenderJobBlur(jobId: string, regions: BlurRegion[]): Promise<void> {
  const res = await fetch(`${API_BASE}/render-jobs/${jobId}/blur/apply`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ regions }) });
  if (!res.ok) throw new Error(await parseError(res, 'Không áp dụng blur được.'));
}

export async function fetchTtsStatus(): Promise<{ status: string; engine: string; message: string }> {
  const res = await fetch(`${API_BASE}/tts/status`);
  if (!res.ok) throw new Error(await parseError(res, 'Không kiểm tra được trạng thái TTS.'));
  return res.json();
}

export async function fetchTtsVoices(): Promise<{ engine: string; voices: TtsVoice[] }> {
  const res = await fetch(`${API_BASE}/tts/voices`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được danh sách giọng TTS.'));
  return res.json();
}

export async function fetchSavedCookies(): Promise<{ available: boolean; cookies_file_path?: string | null; uploaded_at?: number | null; file_size?: number | null }> {
  const res = await fetch(`${API_BASE}/app-settings/cookies`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được cookies đã lưu.'));
  return res.json();
}

export async function deleteSavedCookies(): Promise<void> {
  const res = await fetch(`${API_BASE}/app-settings/cookies`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await parseError(res, 'Không xóa được cookies đã lưu.'));
}

export async function fetchRenderPreferences(): Promise<{ subtitle_mode: string; render_done_bell: boolean; render_options: RenderOptions; updated_at?: number | null }> {
  const res = await fetch(`${API_BASE}/app-settings/render-preferences`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được render preferences.'));
  return res.json();
}

export async function saveRenderPreferences(payload: { subtitle_mode: string; render_done_bell: boolean; render_options: RenderOptions }): Promise<void> {
  const res = await fetch(`${API_BASE}/app-settings/render-preferences`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!res.ok) throw new Error(await parseError(res, 'Không lưu được render preferences.'));
}

export async function fetchTtsClones(): Promise<{ voices: TtsCloneVoice[] }> {
  const res = await fetch(`${API_BASE}/tts/clones`);
  if (!res.ok) throw new Error(await parseError(res, 'Không tải được cloned voices.'));
  return res.json();
}

export async function uploadTtsClone(file: File, name: string): Promise<{ message: string; voice: TtsCloneVoice }> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/tts/clone/upload?name=${encodeURIComponent(name)}`, { method: 'POST', body: formData });
  if (!res.ok) throw new Error(await parseError(res, 'Không clone giọng được.'));
  return res.json();
}

export async function previewTtsClone(cloneId: string, text: string, renderOptions: RenderOptions): Promise<{ message: string; preview_audio_path: string }> {
  const res = await fetch(`${API_BASE}/tts/clones/${cloneId}/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, render_options: renderOptions }) });
  if (!res.ok) throw new Error(await parseError(res, 'Không tạo preview clone voice được.'));
  return res.json();
}

export async function deleteTtsClone(cloneId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/tts/clones/${cloneId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await parseError(res, 'Không xóa cloned voice được.'));
}

export async function fetchTitleLayoutPreview(params: {
  render_options: RenderOptions;
  video_width: number;
  video_height: number;
}): Promise<TitleLayoutPreviewResponse> {
  const res = await fetch(`${API_BASE}/title/layout-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Title layout failed: ${res.statusText}`);
  return res.json();
}

export async function fetchPromptRunStats(since?: number): Promise<PromptRunStats> {
  const params = since !== undefined ? `?since=${since}` : '';
  const res = await fetch(`${API_BASE}/prompt/runs/stats${params}`, { method: 'GET' });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể lấy thống kê prompt.'));
  return res.json();
}

export async function fetchPresetRecommendations(params: {
  video_title?: string;
  youtube_url?: string;
}): Promise<PresetRecommendResponse> {
  const res = await fetch(`${API_BASE}/prompt/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể gợi ý preset.'));
  return res.json();
}

export async function fetchTtsVoicePreview(voiceId: string, text: string): Promise<{ message: string; preview_audio_path: string }> {
  const res = await fetch(`${API_BASE}/tts/voices/${voiceId}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ voice_id: voiceId, text }),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không tạo preview voice được.'));
  return res.json();
}

export function ttsAudioUrl(path: string): string {
  return `${API_BASE}/tts/audio?path=${encodeURIComponent(path)}`;
}

export async function fetchPromptPreview(payload: Record<string, unknown>, signal?: AbortSignal): Promise<PromptPreviewResponse> {
  if (USE_MOCK) return { preview_text: 'Mock preview...', full_length: 120, estimated_tokens: 46, sections: [{ title: 'Intent', start: 0, end: 60, excerpt: 'Mock excerpt' }] };
  const res = await fetch(`${API_BASE}/prompt/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không tạo được prompt preview.'));
  return res.json();
}

export async function fetchPresetCompare(left: string, right: string): Promise<PresetCompareResponse> {
  const res = await fetch(`${API_BASE}/presets/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ left_preset_id_or_name: left, right_preset_id_or_name: right }),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không so sánh được preset.'));
  return res.json();
}

export async function fetchSubtitleStylePreviews(payload: {
  styles?: string[];
  subtitle_font_size?: string;
  subtitle_position?: string;
  subtitle_text_align?: string;
  subtitle_outline?: boolean;
  subtitle_shadow?: boolean;
  subtitle_box?: boolean;
  sample_text?: string;
}, signal?: AbortSignal): Promise<SubtitlePreviewStyleResponse> {
  const res = await fetch(`${API_BASE}/subtitle/preview-style`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không tạo được preview subtitle.'));
  return res.json();
}

export async function checkForUpdates(): Promise<UpdateCheckResponse> {
  const res = await fetch(`${API_BASE}/update/check`);
  if (!res.ok) throw new Error(await parseError(res, 'Không thể kiểm tra cập nhật.'));
  return res.json();
}

export async function launchUpdater(): Promise<UpdateLaunchResponse> {
  const res = await fetch(`${API_BASE}/update/launch`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể khởi chạy trình cập nhật.'));
  return res.json();
}

export async function startAutoPipeline(payload: Record<string, unknown>): Promise<GeminiAutoSubmitResponse> {
  const res = await fetch(`${API_BASE}/gemini/auto-submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể khởi động auto pipeline.'));
  return res.json();
}

export async function startBatchAutoPipeline(payload: Record<string, unknown>): Promise<BatchProgress> {
  const res = await fetch(`${API_BASE}/gemini/batch-auto-submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể khởi động batch auto pipeline.'));
  return res.json();
}

export async function fetchBatchProgress(batchId: string): Promise<BatchProgress> {
  const res = await fetch(`${API_BASE}/gemini/batch/${batchId}`);
  if (!res.ok) throw new Error(await parseError(res, 'Không thể lấy trạng thái batch.'));
  return res.json();
}

export async function cancelBatch(batchId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/gemini/batch/${batchId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể hủy batch.'));
}

export async function cancelAutoPipeline(taskId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/gemini/auto-submit/cancel/${taskId}`, { method: 'POST' });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể hủy auto pipeline.'));
}

export function connectAutoPipelineWS(
  taskId: string,
  onProgress: (data: AutoPipelineProgress) => void,
  onComplete: () => void,
  onError: (error: string) => void,
): () => void {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}${API_BASE}/gemini/status/${taskId}`;
  const ws = new WebSocket(wsUrl);
  let closed = false;

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as AutoPipelineProgress;
      onProgress(data);
      if (data.status === 'done') onComplete();
      if (data.status === 'error') onError(data.error || data.message || 'Unknown error');
      if (data.status === 'done' || data.status === 'error') closed = true;
    } catch {
      onError('Failed to parse progress data');
      closed = true;
    }
  };

  ws.onerror = () => {
    if (!closed) onError('WebSocket connection error');
  };

  ws.onclose = () => {
    closed = true;
  };

  return () => {
    closed = true;
    ws.close();
  };
}

export async function openGeminiBrowser(userDataDir?: string): Promise<GeminiOpenBrowserResponse> {
  const res = await fetch(`${API_BASE}/gemini/open-browser`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: userDataDir ? JSON.stringify({ user_data_dir: userDataDir }) : undefined,
  });
  if (!res.ok) throw new Error(await parseError(res, 'Không thể mở trình duyệt Gemini.'));
  return res.json();
}

export async function fetchGeminiSessionStatus(): Promise<GeminiSessionStatus> {
  const res = await fetch(`${API_BASE}/gemini/session-status`);
  if (!res.ok) throw new Error(await parseError(res, 'Không thể kiểm tra trạng thái session.'));
  return res.json();
}
