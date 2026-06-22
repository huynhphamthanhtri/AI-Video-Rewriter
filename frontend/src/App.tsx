import { useEffect, useMemo, useRef, useState } from 'react';
import { Toaster, toast } from 'sonner';
import { Activity, Bell, CheckCircle2, Copy, Download, ExternalLink, FileJson, Film, FolderCog, KeyRound, Loader2, Play, Plus, Sparkles, Trash2, Upload, Wand2, XCircle } from 'lucide-react';
import { activateLicense, applyRenderJobBlur, blurPreviewUrl, cancelAutoPipeline, cancelRenderJob, checkForUpdates, cleanupStorage, clearLicense, connectAutoPipelineWS, createPreset, deletePreset, deleteSavedCookies, deleteTtsClone, fetchGeminiSessionStatus, fetchLicenseStatus, fetchPresets, fetchPromptHealthScore, fetchRenderJob, fetchRenderJobs, fetchRenderPreferences, fetchRuntimeHealth, fetchSavedCookies, fetchStorageStats, fetchTtsClones, fetchTtsStatus, fetchTtsVoicePreview, fetchTtsVoices, fileDownloadUrl, generatePrompt, launchUpdater, openGeminiBrowser, openOutputFolder, previewTtsClone, saveRenderPreferences, skipRenderJobBlur, startAutoPipeline, startRenderJob, syncBuiltInPresets, ttsAudioUrl, updatePreset, uploadCookies, uploadTtsClone, validateJson, validatePresetConflicts } from './api';
import { BlurRegionEditor, BlurRegionSidebar, BlurTool } from './components/BlurTool';
import { PresetCompareCard } from './components/PresetCompareCard';
import { PresetRecommendationCard } from './components/PresetRecommendationCard';
import { AutoPipelineProgress } from './components/AutoPipelineProgress';
import { PromptPreviewCard } from './components/PromptPreviewCard';
import { PromptTelemetryCard } from './components/PromptTelemetryCard';
import { Card, Pill, SectionTitle, Stat } from './components/common';
import { EdlInspector, EdlSummary } from './components/EdlInspector';
import { TitleTool } from './components/TitleTool';
import SubtitleGallery from './components/SubtitleGallery';
import { SubtitleStyleSelector } from './components/SubtitleStyleSelector';
import { TtsPanel } from './components/TtsPanel';
import { localizationSelectGroups, localizationSwitches, optionGroups, presetNames } from './constants/options';
import { geminiEdlSchema } from './schemas/geminiJson';
import type { AutoPipelineProgress as AutoPipelineProgressData, BlurRegion, GeminiEdlPayload, GeminiSessionStatus, LicenseStatus, OutputResolution, Preset, PresetSyncStatus, PromptForm, PromptHealthResponse, RenderJobStatus, RenderOptions, RenderQuality, RuntimeHealth, StorageCleanupResponse, StorageStats, SubtitleMode, TtsCloneVoice, TtsVoice, UpdateCheckResponse, VideoSegment, VerticalMode } from './types';
import type { BlurRegionLocal } from './components/BlurTool';
import { presetConstraints, presetIntent, presetStrategy } from './types';
import { downloadTextFile } from './utils/download';
import { fmt, parseClipTime, parseSrtTime } from './utils/time';

type StepState = 'idle' | 'running' | 'done' | 'error';
type PresetDraft = Omit<Preset, 'id' | 'is_builtin'>;
type AppTab = 'workflow' | 'edl' | 'blur' | 'title' | 'tts' | 'presets' | 'maintenance';
type PendingPresetRenderOptions = { presetName: string; options: Partial<RenderOptions>; diffs: { key: keyof RenderOptions; label: string; from: string; to: string }[] };

const CURRENT_PRESET_SCHEMA_VERSION = 1;
const CURRENT_PROMPT_TEMPLATE_VERSION = 1;
const CURRENT_JSON_OUTPUT_SCHEMA_VERSION = 1;

const localizationDefaults: Pick<PromptForm, 'target_language' | 'target_market' | 'localization_level' | 'rename_characters' | 'adapt_culture' | 'adapt_currency' | 'adapt_units' | 'adapt_company_names' | 'adaptation_mode' | 'narrator_persona'> = {
  target_language: 'Tiếng Việt',
  target_market: 'Việt Nam',
  localization_level: 'medium',
  rename_characters: true,
  adapt_culture: true,
  adapt_currency: true,
  adapt_units: true,
  adapt_company_names: true,
  adaptation_mode: 'localized',
  narrator_persona: 'neutral_narrator',
};

const initialForm: PromptForm = {
  source_mode: 'single',
  youtube_url: '',
  youtube_urls_text: '',
  ytdlp_cookies_file: '',
  preset_name: 'US COPS Documentary',
  rewrite_style: 'Điều tra',
  target_audience: 'Đại chúng',
  tone: 'Nghiêm túc',
  target_duration: '5-10 phút',
  retention_mode: 'Cao',
  hook_style: 'Cảnh đắt giá',
  clip_strategy: 'Giữ đầy đủ ngữ cảnh',
  reuse_level: 'Cao',
  content_density: 'Trung bình',
  ...localizationDefaults,
  rename_characters: false,
  adapt_company_names: false,
  adaptation_mode: 'faithful',
  narrator_persona: 'detective',
};

const emptyPreset: PresetDraft = {
  name: '',
  description: '',
  rewrite_style: 'Storytelling',
  target_audience: 'Đại chúng',
  tone: 'Thân thiện',
  target_duration: '3-5 phút',
  retention_mode: 'Cao',
  hook_style: 'Kể chuyện',
  clip_strategy: 'Giữ đầy đủ ngữ cảnh',
  reuse_level: 'Trung bình',
  content_density: 'Trung bình',
  ...localizationDefaults,
  preset_schema_version: 1,
  prompt_template_version: 1,
  json_output_schema_version: 1,
};

function presetToDraft(preset: Preset, name = preset.name): PresetDraft {
  return {
    name,
    description: preset.description,
    rewrite_style: preset.rewrite_style,
    target_audience: preset.target_audience,
    tone: preset.tone,
    target_duration: preset.target_duration,
    retention_mode: preset.retention_mode,
    hook_style: preset.hook_style,
    clip_strategy: preset.clip_strategy,
    reuse_level: preset.reuse_level,
    content_density: preset.content_density,
    target_language: preset.target_language,
    target_market: preset.target_market,
    localization_level: preset.localization_level,
    rename_characters: preset.rename_characters,
    adapt_culture: preset.adapt_culture,
    adapt_currency: preset.adapt_currency,
    adapt_units: preset.adapt_units,
    adapt_company_names: preset.adapt_company_names,
    adaptation_mode: preset.adaptation_mode,
    narrator_persona: preset.narrator_persona,
    preset_schema_version: preset.preset_schema_version ?? 1,
    prompt_template_version: preset.prompt_template_version ?? 1,
    json_output_schema_version: preset.json_output_schema_version ?? 1,
  };
}

const renderStepLabels = ['Kiểm tra JSON', 'Tải video', 'Cắt & ghép', 'Xuất video'];
const defaultRenderOptions: RenderOptions = { vertical_mode: 'none', render_quality: 'balanced', output_resolution: 'auto', render_stability: 'stable', video_encoder: 'auto', segment_fps: '60', blur_mode: 'none', tts_mode: 'none', tts_engine: 'vieneu_turbo', tts_language: 'auto', tts_persona: 'neutral', tts_voice_region: 'auto', tts_voice_gender: 'female', tts_voice_id: 'auto', tts_voice_mode: 'preset', tts_clone_voice_id: '', tts_emotion: 'natural', tts_fit_policy: 'segment_uniform', tts_max_speed: 1.5, tts_temperature: 0.4, tts_top_k: 50, tts_max_chars: 256, tts_apply_watermark: true, original_audio_mode: 'lower_fixed', original_audio_volume: 0.3, voiceover_volume: 1.0, title_mode: 'auto', title_text: '', title_style: 'yellow_highlight', title_font_size: 'auto', title_max_lines: 2, title_chars_per_line: 34, title_position: 'top', title_text_align: 'center', title_show_duration: 'full', title_intro_seconds: 5, title_badge_mode: 'none', title_badge_text: '', title_header_height: 0, title_safe_margin: 0, subtitle_style: 'default', subtitle_font_size: 'auto', subtitle_position: 'bottom', subtitle_text_align: 'center', subtitle_max_chars_per_line: 40, subtitle_outline: true, subtitle_shadow: false, subtitle_box: true, artifact_retention: 'smart', video_speed: 1.0 };

const presetRenderRecommendations: Record<string, Partial<RenderOptions>> = {
  'builtin-us-cops-documentary': { tts_mode: 'voiceover', tts_persona: 'news_anchor', tts_voice_region: 'vi_north', tts_voice_gender: 'female', tts_voice_id: 'auto', tts_voice_mode: 'preset', tts_emotion: 'storytelling', tts_fit_policy: 'segment_uniform', tts_max_speed: 1.15, original_audio_mode: 'lower_fixed', original_audio_volume: 0.15, voiceover_volume: 1.1, video_speed: 1.0, artifact_retention: 'smart', title_mode: 'auto', title_style: 'breaking_yellow', title_position: 'top', title_text_align: 'center', title_show_duration: 'full', title_badge_mode: 'auto' },
};

const renderOptionLabels: Partial<Record<keyof RenderOptions, string>> = { tts_mode: 'TTS voiceover', tts_persona: 'TTS persona', tts_voice_region: 'Vùng miền', tts_voice_gender: 'Giới tính', tts_voice_id: 'Giọng cụ thể', tts_voice_mode: 'Voice mode', tts_emotion: 'Emotion', tts_max_speed: 'Max speed', original_audio_mode: 'Audio gốc', original_audio_volume: 'Volume audio gốc', voiceover_volume: 'Volume voiceover', video_speed: 'Video speed', artifact_retention: 'Output files', title_mode: 'Title mode', title_style: 'Title style', title_position: 'Title position', title_text_align: 'Canh chữ title', title_show_duration: 'Thời lượng title', title_badge_mode: 'Title badge' };

function recommendedRenderOptionsForPreset(preset: Preset): Partial<RenderOptions> | null {
  return presetRenderRecommendations[preset.id] ?? presetRenderRecommendations[preset.name] ?? null;
}

function renderOptionValue(value: unknown) {
  if (typeof value === 'number') return value <= 2 ? `${Math.round(value * 100)}%` : String(value);
  if (typeof value === 'boolean') return value ? 'Bật' : 'Tắt';
  return String(value ?? '');
}

function buildRenderOptionDiffs(current: RenderOptions, next: Partial<RenderOptions>): PendingPresetRenderOptions['diffs'] {
  return (Object.entries(next) as [keyof RenderOptions, RenderOptions[keyof RenderOptions]][])
    .filter(([key, value]) => current[key] !== value)
    .map(([key, value]) => ({ key, label: renderOptionLabels[key] ?? String(key), from: renderOptionValue(current[key]), to: renderOptionValue(value) }));
}

function mergeRenderOptions(value: Partial<RenderOptions> | undefined): RenderOptions {
  return { ...defaultRenderOptions, ...(value ?? {}) };
}

function playRenderDoneBell() {
  const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) return;
  const ctx = new AudioContextCtor();
  void ctx.resume();
  const notes = [880, 1175, 1568, 1175];
  notes.forEach((freq, index) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime + index * 0.18);
    gain.gain.exponentialRampToValueAtTime(0.45, ctx.currentTime + index * 0.18 + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + index * 0.18 + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(ctx.currentTime + index * 0.18);
    osc.stop(ctx.currentTime + index * 0.18 + 0.18);
  });
  window.setTimeout(() => void ctx.close(), 1200);
}

function clampProgress(value: number | undefined) {
  return Math.max(0, Math.min(100, Math.round(value ?? 0)));
}

function fmtEta(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return 'Đang ước tính';
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function fmtBytes(value: number | string | undefined) {
  const bytes = Number(value ?? 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function parseYoutubeUrls(text: string) {
  return text.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
}

function stripJsonCodeFence(text: string) {
  const cleaned = text.trim();
  const match = cleaned.match(/^```(?:json|JSON)?\s*([\s\S]*?)\s*```$/);
  return match ? match[1].trim() : cleaned;
}

function optionsWithCurrent<T extends string>(values: readonly T[], current: string) {
  return current && !values.includes(current as T) ? [current, ...values] : [...values];
}

const presetValueAliases: Record<string, string> = {
  '1-3 phut': '1-3 phút',
  '3-5 phut': '3-5 phút',
  '5-10 phut': '5-10 phút',
  '10-20 phut': '10-20 phút',
  'Canh dat gia': 'Cảnh đắt giá',
  'Gay soc': 'Gây sốc',
  'Chi cac doan hay nhat': 'Chỉ các đoạn hay nhất',
  'Trung binh': 'Trung bình',
};

function normalizePresetValue(value: string) {
  return presetValueAliases[value] ?? value;
}

function stepsFromProgress(status: RenderJobStatus): StepState[] {
  if (status.status === 'error') return ['done', 'done', 'error', 'idle'];
  if (status.status === 'cancelled') return ['done', 'error', 'idle', 'idle'];
  if (status.status === 'waiting_blur') return ['done', 'done', 'running', 'idle'];
  if (status.status === 'done') return ['done', 'done', 'done', 'done'];
  const progress = clampProgress(status.progress);
  return [
    progress >= 10 ? 'done' : 'running',
    progress >= 30 ? 'done' : progress >= 10 ? 'running' : 'idle',
    progress >= 82 ? 'done' : progress >= 30 ? 'running' : 'idle',
    progress >= 82 ? 'running' : 'idle',
  ];
}

function ProgressBar({ status }: { status: RenderJobStatus | null }) {
  const progress = clampProgress(status?.progress);
  const fillClass = status?.status === 'error' ? 'error' : status?.status === 'done' ? 'done' : '';
  const segmentText = status?.total_segments ? `Đã cắt ${status.completed_segments ?? 0}/${status.total_segments} segments` : 'Đang chờ thông tin segment';

  return <div className="render-status-card">
    <div className="flex items-center justify-between gap-3">
      <div>
        <p className="text-xs uppercase tracking-wider text-slate-500">Render progress</p>
        <h3 className="text-lg font-black text-white">{status?.step ?? 'Chưa bắt đầu'}</h3>
      </div>
      <div className="text-right text-3xl font-black text-cyan-200">{progress}%</div>
    </div>
    <div className="progress-track mt-4"><div className={`progress-fill ${fillClass}`} style={{ width: `${progress}%` }}/></div>
    <div className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
      <span>{status?.message ?? 'Nhấn Render để bắt đầu dựng video.'}</span>
      <span className="md:text-right">{segmentText}</span>
    </div>
    <div className="mt-4 grid gap-3 md:grid-cols-3">
      <div className="eta-box"><span>Đã chạy</span><b>{fmtEta(status?.elapsed_seconds)}</b></div>
      <div className="eta-box"><span>Còn khoảng</span><b>{status?.status === 'waiting_blur' ? 'Tạm dừng' : status?.status === 'done' ? '0:00' : fmtEta(status?.remaining_seconds)}</b></div>
      <div className="eta-box"><span>Tổng ước tính</span><b>{status?.status === 'waiting_blur' ? 'Chờ thao tác' : fmtEta(status?.estimated_total_seconds)}</b></div>
    </div>
    {status?.job_id && <p className="mt-2 break-all text-xs text-slate-500">Job: {status.job_id}</p>}
  </div>;
}

export function App() {
  const [form, setForm] = useState<PromptForm>(initialForm);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [prompt, setPrompt] = useState('');
  const [jsonText, setJsonText] = useState('');
  const [jsonPayload, setJsonPayload] = useState<GeminiEdlPayload | null>(null);
  const [jsonErrors, setJsonErrors] = useState<string[]>([]);
  const [jsonValid, setJsonValid] = useState(false);
  const [renderSteps, setRenderSteps] = useState<StepState[]>(['idle', 'idle', 'idle', 'idle']);
  const [renderStatus, setRenderStatus] = useState<RenderJobStatus | null>(null);
  const [renderHistory, setRenderHistory] = useState<RenderJobStatus[]>([]);
  const [isRendering, setIsRendering] = useState(false);
  const [subtitleMode, setSubtitleMode] = useState<SubtitleMode>('burn');
  const [renderOptions, setRenderOptions] = useState<RenderOptions>(defaultRenderOptions);
  const [renderDoneBell, setRenderDoneBell] = useState(true);
  const [presetDraft, setPresetDraft] = useState<PresetDraft>(emptyPreset);
  const [editingPresetId, setEditingPresetId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>('workflow');
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null);
  const [cleanupResult, setCleanupResult] = useState<StorageCleanupResponse | null>(null);
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [licenseStatus, setLicenseStatus] = useState<LicenseStatus | null>(null);
  const [presetSyncStatus, setPresetSyncStatus] = useState<PresetSyncStatus | null>(null);
  const [pendingPresetRenderOptions, setPendingPresetRenderOptions] = useState<PendingPresetRenderOptions | null>(null);
  const [promptHealth, setPromptHealth] = useState<PromptHealthResponse | null>(null);
  const [autoPipelineProgress, setAutoPipelineProgress] = useState<AutoPipelineProgressData | null>(null);
  const [isAutoPipelineRunning, setIsAutoPipelineRunning] = useState(false);
  const [geminiSessionStatus, setGeminiSessionStatus] = useState<GeminiSessionStatus | null>(null);
  const [isOpeningBrowser, setIsOpeningBrowser] = useState(false);
  const [chromeProfilePath, setChromeProfilePath] = useState(() => {
    try { return JSON.parse(localStorage.getItem('chromeProfilePath') || '""'); } catch { return ''; }
  });
  const disconnectAutoPipelineWS = useRef<(() => void) | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [autoRenderStatus, setAutoRenderStatus] = useState<RenderJobStatus | null>(null);
  const autoRenderJobIdRef = useRef<string | null>(null);
  const autoRenderPollCancelledRef = useRef(false);
  const autoRenderPollStartedRef = useRef(false);

  useEffect(() => { void loadPresets(); void loadRenderHistory(); void loadSavedCookies(); void loadRenderPreferences(); void loadLicenseStatus(); void loadGeminiSessionStatus(); }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void (async () => {
        const payload: Record<string, unknown> = {
          youtube_url: 'https://www.youtube.com/watch?v=placeholder',
          rewrite_style: form.rewrite_style,
          target_audience: form.target_audience,
          tone: form.tone,
          target_duration: form.target_duration,
          retention_mode: form.retention_mode,
          hook_style: form.hook_style,
          clip_strategy: form.clip_strategy,
          reuse_level: form.reuse_level,
          content_density: form.content_density,
          target_language: form.target_language,
          target_market: form.target_market,
          localization_level: form.localization_level,
          rename_characters: form.rename_characters,
          adapt_culture: form.adapt_culture,
          adapt_currency: form.adapt_currency,
          adapt_units: form.adapt_units,
          adapt_company_names: form.adapt_company_names,
          adaptation_mode: form.adaptation_mode,
          narrator_persona: form.narrator_persona,
        };
        try {
          setPromptHealth(await fetchPromptHealthScore(payload));
        } catch {
          setPromptHealth(null);
        }
      })();
    }, 500);
    return () => clearTimeout(timer);
  }, [form.rewrite_style, form.target_audience, form.tone, form.target_duration, form.retention_mode, form.hook_style, form.clip_strategy, form.reuse_level, form.content_density, form.target_language, form.target_market, form.localization_level, form.rename_characters, form.adapt_culture, form.adapt_currency, form.adapt_units, form.adapt_company_names, form.adaptation_mode, form.narrator_persona, form.preset_name]);

  async function loadPresets() {
    try { setPresets(await fetchPresets()); } catch { toast.error('Không tải được preset.'); }
  }

  async function loadStorageStats() {
    try { setStorageStats(await fetchStorageStats()); } catch { toast.error('Không tải được thống kê dung lượng.'); }
  }

  async function loadRuntimeHealth() {
    try {
      const health = await fetchRuntimeHealth();
      setRuntimeHealth(health);
      setPresetSyncStatus(health.preset_sync_status);
    } catch {
      toast.error('Không tải được runtime health.');
    }
  }

  async function loadLicenseStatus() {
    try { setLicenseStatus(await fetchLicenseStatus()); } catch { toast.error('Không tải được trạng thái license.'); }
  }

  async function activateLicenseFromUi(licenseKey: string) {
    try {
      const status = await activateLicense(licenseKey);
      setLicenseStatus(status);
      toast.success(status.message || 'Kích hoạt license thành công.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không kích hoạt được license.');
    }
  }

  async function clearLicenseFromUi() {
    try {
      await clearLicense();
      await loadLicenseStatus();
      toast.success('Đã xóa license local.');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không xóa được license.');
    }
  }

  async function loadGeminiSessionStatus() {
    try {
      const status = await fetchGeminiSessionStatus();
      setGeminiSessionStatus(status);
    } catch {
      // Non-critical
    }
  }

  async function handleOpenGeminiBrowser() {
    try {
      setIsOpeningBrowser(true);
      const path = chromeProfilePath.trim() || undefined;
      const res = await openGeminiBrowser(path);
      toast.success(res.message);
      if (path) {
        localStorage.setItem('chromeProfilePath', JSON.stringify(path));
      }
      // Always-on useEffect line 403 polls every 5s — no duplicate needed
      void loadGeminiSessionStatus();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không mở được trình duyệt');
    } finally {
      setIsOpeningBrowser(false);
    }
  }

  useEffect(() => {
    const interval = setInterval(() => void loadGeminiSessionStatus(), 5000);
    return () => { clearInterval(interval); autoRenderPollCancelledRef.current = true; };
  }, []);

  async function pollAutoRenderJob(jobId: string) {
    autoRenderPollCancelledRef.current = false;
    const initial = { job_id: jobId, status: 'queued', step: 'Auto Render', message: 'Pipeline hoàn tất, đang chờ render...', progress: 0, completed_segments: 0, total_segments: null, started_at: null, updated_at: null, elapsed_seconds: null, estimated_total_seconds: null, remaining_seconds: null, result: null, errors: [] } satisfies RenderJobStatus;
    setAutoRenderStatus(initial);
    setRenderStatus(initial);
    setRenderSteps(stepsFromProgress(initial));
    setIsRendering(true);
    while (!autoRenderPollCancelledRef.current) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      if (autoRenderPollCancelledRef.current) break;
      try {
        const status = await fetchRenderJob(jobId);
        if (autoRenderPollCancelledRef.current) break;
        setAutoRenderStatus(status);
        setRenderStatus(status);
        setRenderSteps(stepsFromProgress(status));
        if (status.status === 'done') {
          setIsRendering(false);
          toast.success('Render hoàn tất!');
          if (renderDoneBell) playRenderDoneBell();
          const originalTitle = document.title;
          document.title = 'Render xong!';
          window.setTimeout(() => { document.title = originalTitle; }, 8000);
          break;
        }
        if (status.status === 'cancelled') { setIsRendering(false); toast.warning('Render đã bị hủy'); break; }
        if (status.status === 'error') { setIsRendering(false); toast.error(status.message); break; }
      } catch {
        // network error, continue polling
      }
    }
  }

  async function syncBuiltinsFromUi() {
    try {
      const result = await syncBuiltInPresets();
      setPresetSyncStatus(result.status);
      await loadPresets();
      toast.success(`Đã sync built-in presets: ${result.inserted} thêm, ${result.updated} cập nhật.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không sync được built-in presets.');
    }
  }

  async function loadRenderHistory() {
    try { setRenderHistory(await fetchRenderJobs()); } catch { toast.error('Không tải được render history.'); }
  }

  async function loadSavedCookies() {
    try {
      const saved = await fetchSavedCookies();
      if (saved.available && saved.cookies_file_path) updateForm('ytdlp_cookies_file', saved.cookies_file_path);
    } catch {
      // Keep cookies optional; do not block app startup.
    }
  }

  async function loadRenderPreferences() {
    try {
      const saved = await fetchRenderPreferences();
      setSubtitleMode((saved.subtitle_mode as SubtitleMode) || 'burn');
      setRenderDoneBell(saved.render_done_bell ?? true);
      setRenderOptions(mergeRenderOptions(saved.render_options));
    } catch {
      // Defaults are safe if preferences are unavailable.
    }
  }

  const allPresetNames = useMemo(() => Array.from(new Set([...presetNames, ...presets.map(p => p.name)])), [presets]);
  const hasVideoSource = Boolean(form.youtube_url || jsonPayload?.sources?.length);
  const canRender = Boolean((subtitleMode === 'srt_only' || hasVideoSource) && jsonPayload && jsonValid && !isRendering);
  const edlStats = useMemo(() => {
    if (!jsonPayload) return null;
    const subDur = jsonPayload.srt.reduce((a, s) => a + Math.max(0, parseSrtTime(s.end) - parseSrtTime(s.start)), 0);
    const segDur = jsonPayload.video_segments.reduce((a, s) => a + Math.max(0, parseClipTime(s.source_end) - parseClipTime(s.source_start)), 0);
    return { subDur, segDur };
  }, [jsonPayload]);

  const updateForm = (key: keyof PromptForm, value: string | boolean) => setForm(prev => ({ ...prev, [key]: value }));

  function applyPreset(name: string) {
    updateForm('preset_name', name);
    const p = presets.find(x => x.name === name);
    if (!p) return;
    setForm({
      youtube_url: form.youtube_url,
      source_mode: form.source_mode,
      youtube_urls_text: form.youtube_urls_text,
      ytdlp_cookies_file: form.ytdlp_cookies_file,
      preset_name: p.name,
      rewrite_style: normalizePresetValue(p.rewrite_style),
      target_audience: normalizePresetValue(p.target_audience),
      tone: normalizePresetValue(p.tone),
      target_duration: normalizePresetValue(p.target_duration),
      retention_mode: normalizePresetValue(p.retention_mode),
      hook_style: normalizePresetValue(p.hook_style),
      clip_strategy: normalizePresetValue(p.clip_strategy),
      reuse_level: normalizePresetValue(p.reuse_level),
      content_density: normalizePresetValue(p.content_density),
      target_language: p.target_language,
      target_market: p.target_market,
      localization_level: p.localization_level,
      rename_characters: p.rename_characters,
      adapt_culture: p.adapt_culture,
      adapt_currency: p.adapt_currency,
      adapt_units: p.adapt_units,
      adapt_company_names: p.adapt_company_names,
      adaptation_mode: p.adaptation_mode,
      narrator_persona: p.narrator_persona,
    });
    const recommended = recommendedRenderOptionsForPreset(p);
    if (recommended) {
      const diffs = buildRenderOptionDiffs(renderOptions, recommended);
      if (diffs.length) setPendingPresetRenderOptions({ presetName: p.name, options: recommended, diffs });
      else toast.success('Preset đã khớp với render/TTS settings đề xuất.');
    }
  }

  function applyPendingPresetRenderOptions() {
    if (!pendingPresetRenderOptions) return;
    setRenderOptions(prev => ({ ...prev, ...pendingPresetRenderOptions.options }));
    toast.success(`Đã áp dụng render/TTS settings cho ${pendingPresetRenderOptions.presetName}.`);
    setPendingPresetRenderOptions(null);
  }

  async function handleGeneratePrompt() {
    try {
      const urls = form.source_mode === 'multi'
        ? parseYoutubeUrls(form.youtube_urls_text).map(u => u.startsWith('http') ? u : `https://${u}`)
        : [form.youtube_url.trim()].filter(Boolean).map(u => u.startsWith('http') ? u : `https://${u}`);
      if (!urls.length) return toast.error('Vui lòng nhập ít nhất một link YouTube');

      const conflictRes = await validatePresetConflicts(form as unknown as Record<string, unknown>);
      for (const w of conflictRes.warnings) {
        toast.warning(w.message);
      }

      const generated = await generatePrompt({ ...form, youtube_url: urls[0], youtube_urls: urls, source_mode: form.source_mode } as unknown as Record<string, unknown>);
      setPrompt(generated);
      toast.success('Đã tạo prompt Gemini');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không tạo được prompt');
    }
  }

  async function handleAutoPipeline() {
    try {
      autoRenderPollCancelledRef.current = true;
      autoRenderJobIdRef.current = null;
      setAutoRenderStatus(null);

      const urls = form.source_mode === 'multi'
        ? parseYoutubeUrls(form.youtube_urls_text).map(u => u.startsWith('http') ? u : `https://${u}`)
        : [form.youtube_url.trim()].filter(Boolean).map(u => u.startsWith('http') ? u : `https://${u}`);
      if (!urls.length) return toast.error('Vui lòng nhập ít nhất một link YouTube');

      const conflictRes = await validatePresetConflicts(form as unknown as Record<string, unknown>);
      for (const w of conflictRes.warnings) {
        toast.warning(w.message);
      }

      setIsAutoPipelineRunning(true);
      setAutoPipelineProgress({
        task_id: '',
        step: 'init',
        status: 'running',
        message: 'Đang khởi tạo...',
        detail: null,
        result: null,
        error: null,
      });

      const formPayload = { ...form, youtube_url: urls[0], youtube_urls: urls, source_mode: form.source_mode };
      const renderPayload = {
        render_options: renderOptions,
        subtitle_mode: subtitleMode,
        ytdlp_cookies_file: form.ytdlp_cookies_file || undefined,
      };

      const userDataDir = chromeProfilePath.trim() || undefined;
      const res = await startAutoPipeline({ form_data: formPayload, ...renderPayload, user_data_dir: userDataDir });
      setAutoPipelineProgress((prev: AutoPipelineProgressData | null) => prev ? { ...prev, task_id: res.task_id } : null);
      setPrompt(res.prompt_text);

      autoRenderPollStartedRef.current = false;
      disconnectAutoPipelineWS.current = connectAutoPipelineWS(
        res.task_id,
        (data: AutoPipelineProgressData) => {
          setAutoPipelineProgress(data);
          if (data.result?.job_id) {
            const jobId = String(data.result.job_id);
            const isNew = autoRenderJobIdRef.current !== jobId;
            autoRenderJobIdRef.current = jobId;
            if (isNew) toast.success(`Render job đã được tạo: ${jobId}`);
            if (!autoRenderPollStartedRef.current) {
              autoRenderPollStartedRef.current = true;
              void pollAutoRenderJob(jobId);
            }
          }
        },
        () => {
          setIsAutoPipelineRunning(false);
          setAutoPipelineProgress((prev: AutoPipelineProgressData | null) => prev ? { ...prev, status: 'done', step: 'complete', message: 'Pipeline hoàn tất!' } : null);
          void loadRenderHistory();
          const jobId = autoRenderJobIdRef.current;
          if (jobId) {
            if (!autoRenderPollStartedRef.current) {
              autoRenderPollStartedRef.current = true;
              void pollAutoRenderJob(jobId);
            }
            toast.success('Auto pipeline hoàn tất! Đang chờ render...');
          } else {
            toast.success('Auto pipeline hoàn tất!');
          }
        },
        (error: string) => {
          setIsAutoPipelineRunning(false);
          setAutoPipelineProgress((prev: AutoPipelineProgressData | null) => prev ? { ...prev, status: 'error', step: 'error', message: error, error } : null);
          toast.error(`Pipeline thất bại: ${error}`);
        },
      );
    } catch (e) {
      setIsAutoPipelineRunning(false);
      setAutoPipelineProgress(null);
      toast.error(e instanceof Error ? e.message : 'Không khởi động được auto pipeline');
    }
  }

  function handleCancelAutoPipeline() {
    const taskId = autoPipelineProgress?.task_id;
    if (!taskId) return;
    autoRenderPollCancelledRef.current = true;
    autoRenderPollStartedRef.current = false;
    autoRenderJobIdRef.current = null;
    disconnectAutoPipelineWS.current?.();
    setAutoPipelineProgress(null);
    setAutoRenderStatus(null);
    setIsAutoPipelineRunning(false);
    setIsRendering(false);
    cancelAutoPipeline(taskId).catch(() => {});
    toast.warning('Đã hủy auto pipeline');
  }

  function parseClientJson(text = jsonText) {
    const cleaned = stripJsonCodeFence(text);
    const parsed = JSON.parse(cleaned);
    const result = geminiEdlSchema.safeParse(parsed);
    if (!result.success) throw new Error(result.error.issues.map(i => `${i.path.join('.')}: ${i.message}`).join(' | '));
    if (cleaned !== text.trim()) setJsonText(cleaned);
    return parsed as GeminiEdlPayload;
  }

  async function handleValidate() {
    try {
      const parsed = parseClientJson();
      setJsonPayload(parsed);
      const res = await validateJson(parsed);
      if (res.fixed_payload) {
        setJsonText(JSON.stringify(res.fixed_payload, null, 2));
        setJsonPayload(res.fixed_payload);
      }
      setJsonValid(res.valid);
      setJsonErrors([...(res.errors ?? []), ...(res.warnings ?? [])]);
      res.valid ? toast.success(res.warnings?.length ? 'JSON hợp lệ, đã áp dụng auto-fix' : 'JSON EDL hợp lệ') : toast.error('JSON có lỗi');
    } catch (e) {
      setJsonValid(false);
      setJsonErrors([e instanceof Error ? e.message : 'JSON không hợp lệ']);
      toast.error('Validate client-side thất bại');
    }
  }

  function applyEdlPayload(payload: GeminiEdlPayload) {
    setJsonPayload(payload);
    setJsonText(JSON.stringify(payload, null, 2));
    setJsonValid(false);
    toast.success('Đã cập nhật JSON EDL. Hãy validate lại trước khi render.');
  }

  async function applyAndValidateEdlPayload(payload: GeminiEdlPayload) {
    try {
      setJsonPayload(payload);
      setJsonText(JSON.stringify(payload, null, 2));
      const res = await validateJson(payload);
      const nextPayload = res.fixed_payload ?? payload;
      setJsonPayload(nextPayload);
      setJsonText(JSON.stringify(nextPayload, null, 2));
      setJsonValid(res.valid);
      setJsonErrors([...(res.errors ?? []), ...(res.warnings ?? [])]);
      res.valid ? toast.success(res.warnings?.length ? 'Đã apply, validate hợp lệ và áp dụng auto-fix' : 'Đã apply và validate hợp lệ') : toast.error('EDL sau khi chỉnh còn lỗi');
    } catch (e) {
      setJsonValid(false);
      setJsonErrors([e instanceof Error ? e.message : 'Validate EDL thất bại']);
      toast.error('Validate EDL thất bại');
    }
  }

  async function handleFile(file: File) {
    if (file.size > 50 * 1024 * 1024) return toast.error('File vượt quá 50MB');
    const text = await file.text();
    const cleaned = stripJsonCodeFence(text);
    setJsonText(cleaned);
    try { setJsonPayload(parseClientJson(cleaned)); toast.success('Đã đọc JSON'); } catch { toast.warning('Đã tải file, cần kiểm tra schema'); }
  }

  async function handleCookieUpload(file: File) {
    if (!file.name.toLowerCase().endsWith('.txt')) return toast.error('Vui lòng chọn file cookies.txt');
    try {
      const res = await uploadCookies(file);
      updateForm('ytdlp_cookies_file', res.cookies_file_path);
      toast.success('Đã lưu cookies.txt');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload cookies thất bại');
    }
  }

  async function handleClearCookies() {
    try {
      await deleteSavedCookies();
      updateForm('ytdlp_cookies_file', '');
      toast.success('Đã xóa cookies đã lưu');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không xóa được cookies đã lưu');
    }
  }

  async function handleRender() {
    if (subtitleMode !== 'srt_only' && !form.youtube_url && !jsonPayload?.sources?.length) return toast.error('Vui lòng nhập YouTube URL hoặc dùng JSON có sources[]');
    if (!jsonPayload || !jsonValid) return toast.error('Vui lòng validate JSON hợp lệ trước');
    setIsRendering(true);
    setRenderSteps(['running', 'idle', 'idle', 'idle']);
    setRenderStatus({ job_id: '', status: 'queued', step: 'Render request', message: 'Đang gửi yêu cầu render...', progress: 0, completed_segments: 0, total_segments: jsonPayload.video_segments.length, errors: [] });

    try {
      await saveRenderPreferences({ subtitle_mode: subtitleMode, render_done_bell: renderDoneBell, render_options: renderOptions });
      const job = await startRenderJob({ youtube_url: subtitleMode === 'srt_only' ? undefined : form.youtube_url || undefined, ytdlp_cookies_file: form.ytdlp_cookies_file || undefined, gemini_json: jsonPayload, burn_subtitle: subtitleMode === 'burn', subtitle_mode: subtitleMode, render_options: renderOptions });
      toast.success(`Đã bắt đầu job ${job.job_id}`);
      void loadRenderHistory();
      for (;;) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const status = await fetchRenderJob(job.job_id);
        setRenderStatus(status);
        setRenderSteps(stepsFromProgress(status));
        if (status.status === 'done') {
          toast.success('Render hoàn tất');
          if (renderDoneBell) playRenderDoneBell();
          const originalTitle = document.title;
          document.title = 'Render xong!';
          window.setTimeout(() => { document.title = originalTitle; }, 8000);
          break;
        }
        if (status.status === 'cancelled') { toast.warning('Render đã bị hủy'); break; }
        if (status.status === 'error') { toast.error(status.message); break; }
      }
    } catch (e) {
      setRenderSteps(s => s.map(x => x === 'running' ? 'error' : x));
      toast.error(e instanceof Error ? e.message : 'Render thất bại');
    } finally {
      setIsRendering(false);
      void loadRenderHistory();
    }
  }

  async function handleCancelRenderJob(jobId: string) {
    try {
      await cancelRenderJob(jobId);
      toast.success('Đã gửi yêu cầu hủy render job');
      await loadRenderHistory();
      if (renderStatus?.job_id === jobId) setRenderStatus(await fetchRenderJob(jobId));
      } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không hủy được render job');
    }
  }

  async function handleSkipBlurReview(jobId: string) {
    try {
      await skipRenderJobBlur(jobId);
      toast.success('Đã bỏ qua blur, job sẽ tiếp tục xuất final');
      setRenderStatus(await fetchRenderJob(jobId));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không bỏ qua blur được');
    }
  }

  async function savePreset() {
    try {
      if (editingPresetId) await updatePreset(editingPresetId, presetDraft);
      else await createPreset(presetDraft);
      toast.success(editingPresetId ? 'Đã cập nhật preset' : 'Đã tạo preset');
      setPresetDraft(emptyPreset);
      setEditingPresetId(null);
      await loadPresets();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không lưu được preset');
    }
  }

  async function clonePreset(preset: Preset) {
    try {
      await createPreset(presetToDraft(preset, `${preset.name} - Copy`));
      toast.success('Đã nhân bản preset thành preset cá nhân');
      await loadPresets();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không nhân bản được preset');
    }
  }

  function cancelPresetEdit() {
    setPresetDraft(emptyPreset);
    setEditingPresetId(null);
  }

  async function runCleanup(target: 'temp' | 'outputs' | 'all', olderThanHours: number, dryRun: boolean) {
    try {
      const result = await cleanupStorage({ target, older_than_hours: olderThanHours, dry_run: dryRun });
      setCleanupResult(result);
      if (dryRun) toast.success(`Tìm thấy ${result.matched_count} mục có thể dọn`);
      else toast.success(`Đã dọn ${result.deleted_count} mục, giải phóng ${fmtBytes(result.freed_bytes)}`);
      await loadStorageStats();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Cleanup thất bại');
    }
  }

  return <div className="min-h-screen bg-[#070B18] text-slate-100">
    <Toaster richColors position="top-right"/>
    {pendingPresetRenderOptions && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-2xl rounded-3xl border border-white/10 bg-[#0B1020] p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between gap-3"><div><h2 className="text-xl font-black">Áp dụng TTS/render settings?</h2><p className="mt-1 text-sm text-slate-400">Preset <b>{pendingPresetRenderOptions.presetName}</b> có cấu hình đề xuất. Prompt fields đã được áp dụng, còn TTS/render sẽ chỉ đổi nếu bạn xác nhận.</p></div><button className="btn-mini" onClick={() => setPendingPresetRenderOptions(null)}>Đóng</button></div>
        <div className="max-h-72 overflow-auto rounded-2xl border border-white/10 bg-slate-950/50 p-3 text-sm">
          {pendingPresetRenderOptions.diffs.map(diff => <div className="grid gap-2 border-b border-white/5 py-2 last:border-b-0 md:grid-cols-[1fr_1fr_1fr]" key={String(diff.key)}><b>{diff.label}</b><span className="text-slate-400">{diff.from}</span><span className="text-cyan-200">{diff.to}</span></div>)}
        </div>
        <div className="mt-5 flex flex-wrap justify-end gap-2"><button className="btn-secondary" onClick={() => setPendingPresetRenderOptions(null)}>Không áp dụng</button><button className="btn-primary" onClick={applyPendingPresetRenderOptions}>Áp dụng settings đề xuất</button></div>
      </div>
    </div>}
    <main className="mx-auto max-w-7xl space-y-6 p-5">
      <header className="panel flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div className="flex items-center gap-3"><div className="logo"><Sparkles size={24}/></div><div><h1 className="text-2xl font-black">AI Video Rewriter & Video Rebuilder</h1><p className="text-sm text-slate-400">EDL shot-based editing, Gemini JSON, async render progress</p></div></div>
        <Pill tone={renderStatus?.status === 'done' ? 'green' : renderStatus?.status === 'error' || renderStatus?.status === 'cancelled' ? 'red' : isRendering ? 'yellow' : 'cyan'}>{renderStatus?.status ?? 'idle'}</Pill>
      </header>

      <div className="panel flex flex-wrap gap-2">
        <button className={activeTab === 'workflow' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('workflow')}>Workflow dựng video</button>
        <button className={activeTab === 'edl' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('edl')}>EDL Inspector</button>
        <button className={activeTab === 'blur' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('blur')}>Blur Tool</button>
        <button className={activeTab === 'title' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('title')}>Title Tool</button>
        <button className={activeTab === 'tts' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('tts')}>Voiceover / TTS</button>
        <button className={activeTab === 'presets' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('presets')}>Quản lý Preset</button>
        <button className={activeTab === 'maintenance' ? 'btn-primary' : 'btn-secondary'} onClick={() => { setActiveTab('maintenance'); void loadStorageStats(); void loadRuntimeHealth(); void loadLicenseStatus(); }}>Bảo trì</button>
      </div>

      {activeTab === 'workflow' ? <div className="grid gap-6 xl:grid-cols-[1.2fr_.8fr]">
        <div className="space-y-6">
          <Card><SectionTitle icon={Wand2} title="1. Tạo Prompt cho Gemini" desc="Nhập link YouTube và cấu hình prompt"/>
            <label className="label">Chế độ nguồn video</label>
            <select className="select-ghost" value={form.source_mode} onChange={e => updateForm('source_mode', e.target.value)}><option value="single">1 link YouTube</option><option value="multi">Nhiều link YouTube</option></select>
            {form.source_mode === 'single' ? <div className="mt-4"><label className="label">Link YouTube</label><input className="input" value={form.youtube_url} onChange={e => updateForm('youtube_url', e.target.value)} placeholder="https://www.youtube.com/watch?v=..."/></div> : <div className="mt-4"><label className="label">Danh sách link YouTube, mỗi dòng một link</label><textarea className="textarea min-h-[130px]" value={form.youtube_urls_text} onChange={e => { updateForm('youtube_urls_text', e.target.value); const first = parseYoutubeUrls(e.target.value)[0] ?? ''; updateForm('youtube_url', first); }} placeholder={'https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...'}/></div>}
            <PresetRecommendationCard youtubeUrl={form.youtube_url} onApplyPreset={applyPreset} />
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div><div className="mb-1 flex items-center justify-between gap-2"><label className="label mb-0">Preset</label><button className="btn-mini" onClick={() => setActiveTab('presets')}>Quản lý</button></div><select className="select-ghost" value={form.preset_name} onChange={e => applyPreset(e.target.value)}>{allPresetNames.map(name => <option key={name} value={name}>{name}</option>)}</select></div>
              {Object.entries(optionGroups).map(([key, cfg]) => { const current = String(form[key as keyof PromptForm] ?? ''); return <div key={key}><label className="label">{cfg.label}</label><select className="select-ghost" value={current} onChange={e => updateForm(key as keyof PromptForm, e.target.value)}>{optionsWithCurrent(cfg.values, current).map(v => <option key={v} value={v}>{v}</option>)}</select></div>; })}
            </div>
            <LocalizationFields data={form} onChange={(key, value) => updateForm(key as keyof PromptForm, value)}/>
            <PresetPreview form={form} presets={presets}/>
            <PromptPreviewCard formFields={form} />
            <PromptHealthCard health={promptHealth}/>
            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-2">
                <input className="input flex-1" type="text" placeholder="Path Chrome profile (VD: C:\Users\huynh\AppData\Local\Google\Chrome\User Data)"
                  value={chromeProfilePath} onChange={e => setChromeProfilePath(e.target.value)}/>
                <span className="text-xs text-slate-400 shrink-0 cursor-help" title="Đóng Chrome trước khi dùng profile thật. Để trống nếu muốn login thủ công.">ⓘ</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn-primary" onClick={handleGeneratePrompt} disabled={isAutoPipelineRunning}><Wand2 size={18}/>Tạo prompt</button>
                <button className="btn-secondary" onClick={handleOpenGeminiBrowser} disabled={isOpeningBrowser}>
                  <ExternalLink size={18}/>{isOpeningBrowser ? 'Đang mở...' : 'Mở trình duyệt Gemini'}
                </button>
                <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  geminiSessionStatus?.exists ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'
                }`} title={geminiSessionStatus?.path || 'Chưa có session'}>
                  <span className={`h-1.5 w-1.5 rounded-full ${geminiSessionStatus?.exists ? 'bg-green-500' : 'bg-gray-400'}`}/>
                  {geminiSessionStatus?.exists ? 'Đã đăng nhập' : 'Chưa login'}
                </span>
                <button className="btn-primary" style={{ background: 'linear-gradient(135deg, #7c3aed, #a855f7)' }} onClick={handleAutoPipeline} disabled={isAutoPipelineRunning}>
                  <ExternalLink size={18}/>Auto Pipeline
                </button>
              </div>
            </div>
            {autoPipelineProgress && !autoRenderStatus && (
              <AutoPipelineProgress progress={autoPipelineProgress} onCancel={handleCancelAutoPipeline} />
            )}
            {autoRenderStatus && (
              ['queued', 'running', 'error', 'cancelled'].includes(autoRenderStatus.status)
                ? <ProgressBar status={autoRenderStatus} />
                : autoRenderStatus.status === 'done'
                ? <RenderResultPanel result={autoRenderStatus.result!} />
                : null
            )}
            {prompt && !isAutoPipelineRunning && <div className="mt-4"><div className="mb-2 flex items-center justify-between"><label className="label mb-0">Prompt Gemini</label><button className="btn-mini" onClick={() => navigator.clipboard.writeText(prompt)}><Copy size={14}/>Copy</button></div><textarea className="textarea min-h-[260px]" value={prompt} readOnly/></div>}
            <PromptTelemetryCard />
          </Card>

          <Card><SectionTitle icon={FileJson} title="2. Kiểm tra JSON EDL" desc="Paste hoặc upload JSON Gemini trả về"/>
            <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={e => { const file = e.target.files?.[0]; if (file) void handleFile(file); e.currentTarget.value = ''; }}/>
            <div className="mb-3 flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => fileRef.current?.click()}><Upload size={16}/>Upload JSON</button><button className="btn-primary" onClick={handleValidate}><CheckCircle2 size={16}/>Validate JSON</button></div>
            <textarea className="textarea min-h-[360px]" value={jsonText} onChange={e => setJsonText(e.target.value)} placeholder="Dán JSON EDL tại đây..."/>
            <div className="mt-3 flex flex-wrap items-center gap-2">{jsonValid ? <Pill tone="green">JSON hợp lệ</Pill> : <Pill tone="yellow">Chưa hợp lệ</Pill>}{jsonErrors.map(err => <Pill key={err} tone="red">{err}</Pill>)}</div>
          </Card>
        </div>

        <div className="space-y-6">
          <RenderPanel canRender={canRender} isRendering={isRendering} steps={renderSteps} status={renderStatus} history={renderHistory} cookiesFile={form.ytdlp_cookies_file} subtitleMode={subtitleMode} renderOptions={renderOptions} renderDoneBell={renderDoneBell} jsonPayload={jsonPayload} onRenderDoneBellChange={setRenderDoneBell} onSubtitleModeChange={setSubtitleMode} onRenderOptionsChange={setRenderOptions} onCookieUpload={handleCookieUpload} onClearCookies={handleClearCookies} onRender={handleRender} onRefreshHistory={loadRenderHistory} onCancelJob={handleCancelRenderJob} onOpenBlurReview={() => setActiveTab('blur')} onOpenTitleTool={() => setActiveTab('title')} onOpenTtsPanel={() => setActiveTab('tts')} onSkipBlurReview={handleSkipBlurReview}/>
          <EdlSummary payload={jsonPayload} stats={edlStats} onOpen={() => setActiveTab('edl')}/>
        </div>
      </div> : activeTab === 'edl' ? <div className="mx-auto max-w-7xl"><EdlInspector payload={jsonPayload} onApply={applyEdlPayload} onApplyAndValidate={applyAndValidateEdlPayload}/></div> : activeTab === 'blur' ? <div className="mx-auto max-w-7xl"><BlurTool reviewJob={renderStatus?.status === 'waiting_blur' ? renderStatus : null} onAfterReviewDecision={async () => { if (renderStatus?.job_id) setRenderStatus(await fetchRenderJob(renderStatus.job_id)); }}/></div> : activeTab === 'title' ? <div className="mx-auto max-w-7xl"><TitleTool renderOptions={renderOptions} jsonPayload={jsonPayload} onRenderOptionsChange={setRenderOptions}/></div> : activeTab === 'tts' ? <div className="mx-auto max-w-5xl"><TtsPanel renderOptions={renderOptions} onRenderOptionsChange={setRenderOptions}/></div> : activeTab === 'presets' ? <div className="mx-auto max-w-5xl space-y-6">
            <PresetManager presets={presets} draft={presetDraft} setDraft={setPresetDraft} editingId={editingPresetId} setEditingId={setEditingPresetId} onSave={savePreset} onCancel={cancelPresetEdit} onClone={clonePreset} onDelete={async (preset: Preset) => { await deletePreset(preset.id); await loadPresets(); }}/>
            <PresetCompareCard presets={presets} />
          </div> : <div className="mx-auto max-w-5xl"><MaintenancePanel stats={storageStats} cleanupResult={cleanupResult} runtimeHealth={runtimeHealth} presetSyncStatus={presetSyncStatus} licenseStatus={licenseStatus} onRefresh={() => { void loadStorageStats(); void loadRuntimeHealth(); void loadLicenseStatus(); }} onSyncBuiltins={syncBuiltinsFromUi} onCleanup={runCleanup} onActivateLicense={activateLicenseFromUi} onClearLicense={clearLicenseFromUi}/></div>}
    </main>
  </div>;
}

function LocalizationFields({ data, onChange }: { data: Record<string, unknown>; onChange: (key: string, value: string | boolean) => void }) {
  return <div className="mt-5 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4"><h3 className="mb-3 font-bold">NGÔN NGỮ & BẢN ĐỊA HÓA</h3><div className="grid gap-3 md:grid-cols-2">{Object.entries(localizationSelectGroups).map(([key, cfg]) => <div className="select-card" key={key}><label className="mb-2 block text-sm font-semibold">{cfg.label}</label><select className="select-ghost" value={String(data[key] ?? '')} onChange={e => onChange(key, e.target.value)}>{cfg.values.map(v => typeof v === 'string' ? <option key={v} value={v}>{v}</option> : <option key={v.value} value={v.value}>{v.label}</option>)}</select></div>)}</div><div className="mt-4 grid gap-2 md:grid-cols-2">{localizationSwitches.map(([key, label]) => <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm" key={key}><input type="checkbox" checked={Boolean(data[key])} onChange={e => onChange(key, e.target.checked)}/>{label}</label>)}</div></div>;
}

function PresetPreview({ form, presets }: { form: PromptForm; presets: Preset[] }) {
  const p = presets.find(x => x.name === form.preset_name);
  if (!p) return null;
  const intent = presetIntent(p);
  const strategy = presetStrategy(p);
  const constraints = presetConstraints(p);
  const versionOutdated = p.preset_schema_version < CURRENT_PRESET_SCHEMA_VERSION || p.prompt_template_version < CURRENT_PROMPT_TEMPLATE_VERSION || p.json_output_schema_version < CURRENT_JSON_OUTPUT_SCHEMA_VERSION;
  return <div className="mt-5 rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
    <h3 className="mb-3 flex items-center gap-2 font-bold">🎬 Preset: {p.name}</h3>
    {versionOutdated && <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">⚠️ Preset này đang ở phiên bản cũ. Hãy duplicate và cập nhật để có kết quả tốt nhất.</div>}
    <div className="grid gap-3 text-sm md:grid-cols-3">
      <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Intent</div>
        <div className="space-y-1">
          <div><span className="text-slate-400">Style:</span> {intent.rewrite_style}</div>
          <div><span className="text-slate-400">Audience:</span> {intent.target_audience}</div>
          <div><span className="text-slate-400">Tone:</span> {intent.tone}</div>
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Strategy</div>
        <div className="space-y-1">
          <div><span className="text-slate-400">Hook:</span> {strategy.hook_style}</div>
          <div><span className="text-slate-400">Clip:</span> {strategy.clip_strategy}</div>
          <div><span className="text-slate-400">Pacing:</span> {strategy.retention_mode}</div>
          <div><span className="text-slate-400">Reuse:</span> {strategy.reuse_level}</div>
          <div><span className="text-slate-400">Density:</span> {strategy.content_density}</div>
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Constraints</div>
        <div className="space-y-1">
          <div><span className="text-slate-400">Duration:</span> {constraints.target_duration}</div>
          <div><span className="text-slate-400">Lang:</span> {constraints.target_language}</div>
          <div><span className="text-slate-400">Market:</span> {constraints.target_market}</div>
          <div><span className="text-slate-400">Localize:</span> {constraints.localization_level}</div>
          <div><span className="text-slate-400">Persona:</span> {constraints.narrator_persona}</div>
        </div>
      </div>
    </div>
  </div>;
}

const healthLevelStyles: Record<string, string> = {
  excellent: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  good: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
  risky: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  weak: 'border-red-500/30 bg-red-500/10 text-red-300',
};

const healthLevelLabels: Record<string, string> = {
  excellent: 'Xuất sắc',
  good: 'Tốt',
  risky: 'Cần cân nhắc',
  weak: 'Yếu',
};

function PromptHealthCard({ health }: { health: PromptHealthResponse | null }) {
  if (!health) return null;
  const borderStyle = healthLevelStyles[health.level] ?? healthLevelStyles.weak;
  const label = healthLevelLabels[health.level] ?? 'Không xác định';
  const [showDetails, setShowDetails] = useState(false);
  return <div className={`mt-5 rounded-2xl border p-4 ${borderStyle}`}>
    <div className="mb-3 flex items-center justify-between">
      <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider">Điểm sức khỏe Prompt</h3>
      <div className="flex items-center gap-2">
        <span className="text-2xl font-black">{health.score}</span>
        <span className="rounded-md px-2 py-0.5 text-xs font-semibold uppercase" style={{ backgroundColor: 'rgba(0,0,0,0.3)' }}>{label}</span>
      </div>
    </div>
    {health.strengths.length > 0 && <div className="mb-2 space-y-1">{health.strengths.map((s, i) => <div key={i} className="flex items-start gap-2 text-sm"><span className="mt-0.5 shrink-0">✅</span><span>{s}</span></div>)}</div>}
    {health.warnings.length > 0 && <div className="space-y-1">{health.warnings.map((w, i) => <div key={i} className="flex items-start gap-2 text-sm"><span className="mt-0.5 shrink-0">⚠️</span><span>{w}</span></div>)}</div>}
    {health.details && health.details.length > 0 && (
      <>
        <button
          className="mt-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? 'Ẩn' : 'Xem'} chi tiết điểm số ({health.details.length} yếu tố)
        </button>
        {showDetails && (
          <div className="mt-3 overflow-x-auto rounded-xl border border-white/10 bg-slate-950/40">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/10 text-left text-slate-500">
                  <th className="px-3 py-2">Yếu tố</th>
                  <th className="px-3 py-2">Giá trị</th>
                  <th className="px-3 py-2">Tác động</th>
                  <th className="px-3 py-2">Lý do</th>
                </tr>
              </thead>
              <tbody>
                {health.details.map((d, i) => (
                  <tr key={i} className="border-b border-white/5 last:border-b-0">
                    <td className="px-3 py-1.5 font-medium text-slate-200">{d.label}</td>
                    <td className="px-3 py-1.5 text-slate-300">{d.value}</td>
                    <td className={`px-3 py-1.5 font-semibold ${d.impact > 0 ? 'text-emerald-400' : d.impact < 0 ? 'text-red-400' : 'text-slate-400'}`}>
                      {d.impact > 0 ? `+${d.impact}` : d.impact}
                    </td>
                    <td className="px-3 py-1.5 text-slate-400">{d.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    )}
  </div>;
}

function RenderPanel({ canRender, isRendering, steps, status, history, cookiesFile, subtitleMode, renderOptions, renderDoneBell, jsonPayload, onRenderDoneBellChange, onSubtitleModeChange, onRenderOptionsChange, onCookieUpload, onClearCookies, onRender, onRefreshHistory, onCancelJob, onOpenBlurReview, onOpenTitleTool, onOpenTtsPanel, onSkipBlurReview }: { canRender: boolean; isRendering: boolean; steps: StepState[]; status: RenderJobStatus | null; history: RenderJobStatus[]; cookiesFile: string; subtitleMode: SubtitleMode; renderOptions: RenderOptions; renderDoneBell: boolean; jsonPayload: GeminiEdlPayload | null; onRenderDoneBellChange: (value: boolean) => void; onSubtitleModeChange: (value: SubtitleMode) => void; onRenderOptionsChange: (value: RenderOptions) => void; onCookieUpload: (file: File) => void; onClearCookies: () => void; onRender: () => void; onRefreshHistory: () => void; onCancelJob: (jobId: string) => void; onOpenBlurReview: () => void; onOpenTitleTool: () => void; onOpenTtsPanel: () => void; onSkipBlurReview: (jobId: string) => void }) {
  const cookieInputRef = useRef<HTMLInputElement>(null);
  const [ttsStatus, setTtsStatus] = useState<{ status: string; message: string } | null>(null);
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);

  useEffect(() => { void fetchTtsStatus().then(setTtsStatus).catch(() => setTtsStatus({ status: 'error', message: 'Không kiểm tra được trạng thái TTS.' })); void fetchTtsVoices().then(data => setTtsVoices(data.voices)).catch(() => setTtsVoices([])); }, []);
  const updateOptions = (patch: Partial<RenderOptions>) => onRenderOptionsChange({ ...renderOptions, ...patch });
  return <Card><SectionTitle icon={Film} title="3. Dựng video" desc="Render async có thanh tiến trình %"/>
    <ProgressBar status={status}/>
    <div className="mt-4 space-y-3">{renderStepLabels.map((label, index) => <div className="step" key={label}><span className={`dot ${steps[index]}`}/><div><b>{label}</b><p>{steps[index] === 'idle' ? 'Chưa thực hiện' : steps[index] === 'running' ? 'Đang xử lý' : steps[index] === 'done' ? 'Hoàn thành' : 'Lỗi'}</p></div></div>)}</div>
    <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">
      <h3 className="mb-3 font-bold">Render Options</h3>
      <div className="grid gap-3">
        <div><label className="label">Subtitle output</label><select className="select-ghost" value={subtitleMode} onChange={e => onSubtitleModeChange(e.target.value as SubtitleMode)}><option value="burn">Xuất video + burn subtitle + file SRT</option><option value="none">Xuất video + file SRT, không burn subtitle</option><option value="srt_only">Chỉ xuất file SRT, không dựng video</option></select></div>
        <div><label className="label">Blur Review</label><select className="select-ghost" value={renderOptions.blur_mode} onChange={e => updateOptions({ blur_mode: e.target.value as RenderOptions['blur_mode'] })}><option value="none">Không blur - render thẳng final</option><option value="review">Dừng để chọn vùng blur trước khi burn subtitle/final</option></select></div>
        <TitleOverlayOptions renderOptions={renderOptions} jsonPayload={jsonPayload} onChange={updateOptions} onOpenTitleTool={onOpenTitleTool}/>
        <SubtitleStyleSelector renderOptions={renderOptions} onChange={updateOptions}/>
        <SubtitleGallery renderOptions={renderOptions} onChange={updateOptions}/>
        <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="font-bold">Voiceover / TTS</h4>{ttsStatus && <Pill tone={ttsStatus.status === 'ready' ? 'green' : 'yellow'}>{ttsStatus.status === 'ready' ? 'TTS ready' : 'TTS chưa cài'}</Pill>}</div>{ttsStatus && <p className="mb-3 text-xs text-slate-400">{ttsStatus.message}</p>}<div className="grid gap-3"><div><label className="label">TTS voiceover</label><select className="select-ghost" value={renderOptions.tts_mode} onChange={e => updateOptions({ tts_mode: e.target.value as RenderOptions['tts_mode'] })}><option value="none">Tắt TTS</option><option value="voiceover">Bật VieNeu Turbo đọc theo srt[]</option></select></div>{renderOptions.tts_mode === 'voiceover' && <button className="btn-secondary w-full" onClick={onOpenTtsPanel}>Mở TTS Panel để tuỳ chỉnh giọng đọc</button>}</div></div>
        <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm"><input type="checkbox" checked={renderDoneBell} onChange={e => onRenderDoneBellChange(e.target.checked)}/>Bật chuông lớn khi render xong</label>
        <div><label className="label">Output files</label><select className="select-ghost" value={renderOptions.artifact_retention} onChange={e => updateOptions({ artifact_retention: e.target.value as RenderOptions['artifact_retention'] })}><option value="smart">Smart cleanup - giữ debug cần thiết, xóa video trung gian lớn</option><option value="keep_all">Keep all files - giữ mọi file để debug sâu</option></select></div>
        <div><label className="label">Render stability</label><select className="select-ghost" value={renderOptions.render_stability} onChange={e => updateOptions({ render_stability: e.target.value as RenderOptions['render_stability'] })}><option value="fast">Fast - nhanh hơn</option><option value="stable">Stable - khuyến nghị</option><option value="max_quality">Max Quality - đẹp hơn</option></select></div>
        <div><label className="label">Hardware acceleration</label><select className="select-ghost" value={renderOptions.video_encoder} onChange={e => updateOptions({ video_encoder: e.target.value as RenderOptions['video_encoder'] })}><option value="auto">Auto - ưu tiên GPU</option><option value="cpu">CPU only</option><option value="nvenc">NVIDIA NVENC</option><option value="qsv">Intel Quick Sync</option><option value="amf">AMD AMF</option></select></div>
        <div><label className="label">Segment FPS</label><select className="select-ghost" value={renderOptions.segment_fps} onChange={e => updateOptions({ segment_fps: e.target.value as RenderOptions['segment_fps'] })}><option value="auto">Auto</option><option value="30">30fps</option><option value="60">60fps - sports/highlights</option></select></div>
        <div><label className="label">Tỉ lệ đầu ra</label><select className="select-ghost" value={renderOptions.vertical_mode} onChange={e => updateOptions({ vertical_mode: e.target.value as VerticalMode })}><option value="none">Giữ nguyên ngang</option><option value="blur_fit">Dọc 9:16 - Nền blur + video vuông 1:1</option><option value="center_crop">Dọc 9:16 - Center crop</option></select></div>
        <div className="grid gap-3 md:grid-cols-2">
          <div><label className="label">Chất lượng render</label><select className="select-ghost" value={renderOptions.render_quality} onChange={e => updateOptions({ render_quality: e.target.value as RenderQuality })}><option value="fast">Fast - nhanh, file nhỏ</option><option value="balanced">Balanced - mặc định</option><option value="high">High - chất lượng cao</option></select></div>
          <div><label className="label">Độ phân giải</label><select className="select-ghost" value={renderOptions.output_resolution} onChange={e => updateOptions({ output_resolution: e.target.value as OutputResolution })}><option value="auto">Auto / Original</option><option value="720p">720p</option><option value="1080p">1080p</option></select></div>
        </div>
        <div><label className="label">Tốc độ video</label><select className="select-ghost" value={renderOptions.video_speed} onChange={e => updateOptions({ video_speed: Number(e.target.value) })}><option value={1.0}>1.0x — Bình thường</option><option value={1.1}>1.1x — Hơi nhanh</option><option value={1.2}>1.2x — Nhanh hơn</option><option value={1.3}>1.3x — Nhanh</option><option value={1.5}>1.5x — Rất nhanh</option></select><p className="mt-1 text-xs text-slate-400">Tăng tốc video cuối bằng setpts+atempo, giữ nguyên pitch. Áp dụng sau khi burn subtitle.</p></div>
      </div>
    </div>
    <div className="mt-4 rounded-2xl border border-yellow-500/20 bg-yellow-500/10 p-4"><h3 className="mb-2 font-bold">Cookies YouTube cho yt-dlp</h3><p className="mb-3 text-xs text-slate-400">Dùng khi YouTube yêu cầu xác minh đăng nhập.</p><input ref={cookieInputRef} type="file" accept=".txt,text/plain" hidden onChange={e => { const file = e.target.files?.[0]; if (file) onCookieUpload(file); e.currentTarget.value = ''; }}/><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => cookieInputRef.current?.click()}><Upload size={16}/>Chọn cookies.txt</button>{cookiesFile && <button className="btn-secondary" onClick={onClearCookies}>Xóa cookies</button>}</div>{cookiesFile && <p className="mt-2 break-all text-xs text-emerald-300">Đã upload: {cookiesFile}</p>}</div>
    {!canRender && <p className="mt-3 text-xs text-yellow-300">Cần JSON đã validate hợp lệ. Nếu dựng video, cần thêm YouTube URL hoặc JSON có sources[].</p>}
    <button className="btn-primary mt-4 w-full" disabled={!canRender} onClick={onRender}>{isRendering ? <Loader2 className="animate-spin" size={18}/> : <Play size={18}/>} {subtitleMode === 'srt_only' ? 'Xuất SRT' : 'Render video'}</button>
    {status?.status === 'waiting_blur' && <BlurReviewEntry status={status} onOpen={onOpenBlurReview} onSkip={onSkipBlurReview}/>} 
    {status?.result && status.status !== 'waiting_blur' && <RenderResultPanel result={status.result}/>} 
    <RenderHistoryPanel jobs={history} onRefresh={onRefreshHistory} onCancel={onCancelJob}/>
  </Card>;
}

function TitleOverlayOptions({ renderOptions, jsonPayload, onChange, onOpenTitleTool }: { renderOptions: RenderOptions; jsonPayload: GeminiEdlPayload | null; onChange: (patch: Partial<RenderOptions>) => void; onOpenTitleTool: () => void }) {
  const rawTitle = renderOptions.title_mode === 'custom' ? renderOptions.title_text : jsonPayload?.metadata.video_title || 'Title preview từ metadata.video_title';
  const maxLines = Math.max(1, Math.min(3, Number(renderOptions.title_max_lines) || 2));
  const charsPerLine = Math.max(16, Math.min(60, Number(renderOptions.title_chars_per_line) || 34));
  const ratio = renderOptions.vertical_mode === 'none' ? '16:9' : '9:16';
  return <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="font-bold">Auto Title Overlay</h4><Pill tone={renderOptions.title_mode === 'none' ? 'yellow' : 'green'}>{renderOptions.title_mode === 'none' ? 'Off' : `${ratio} workspace`}</Pill></div>
    <div className="grid gap-3">
      <div><label className="label">Title overlay</label><select className="select-ghost" value={renderOptions.title_mode} onChange={e => onChange({ title_mode: e.target.value as RenderOptions['title_mode'] })}><option value="auto">Auto from JSON title</option><option value="custom">Custom title</option><option value="none">Off</option></select></div>
      <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3 text-xs text-slate-400">
        <p className="line-clamp-2 text-slate-300">{renderOptions.title_mode === 'none' ? 'Title overlay đang tắt.' : rawTitle}</p>
        <p className="mt-2">Style: {renderOptions.title_style} · Align: {renderOptions.title_text_align} · Badge: {renderOptions.title_badge_mode} · {renderOptions.title_show_duration === 'full' ? 'Full video' : `${renderOptions.title_intro_seconds}s intro`}</p>
        <p className="mt-1">Font: {renderOptions.title_font_size} · {maxLines} dòng · {charsPerLine} ký tự/dòng · Position: {renderOptions.title_position}</p>
      </div>
      <button className="btn-secondary w-full" onClick={onOpenTitleTool}>Mở Title Tool để preview đúng tỉ lệ</button>
    </div>
  </div>;
}


function BlurReviewEntry({ status, onOpen, onSkip }: { status: RenderJobStatus; onOpen: () => void; onSkip: (jobId: string) => void }) {
  return <div className="mt-4 rounded-2xl border border-yellow-500/30 bg-yellow-500/10 p-4"><div className="flex items-start gap-3"><Bell size={20} className="mt-0.5 flex-shrink-0 text-yellow-400"/><div className="min-w-0 flex-1"><h3 className="font-bold text-yellow-100">Đang chờ Blur Review</h3><p className="mt-1 text-sm text-slate-300">Video trung gian đã được tạo đúng tỉ lệ output.</p><p className="mt-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2 text-sm font-medium text-yellow-200"><Bell size={14} className="-mt-0.5 mr-1 inline"/>Mở workspace lớn để chọn vùng blur chính xác hơn, hoặc bỏ qua nếu không cần.</p><div className="mt-4 flex flex-wrap gap-2"><button className="btn-primary" onClick={onOpen}>Mở Blur Review Workspace</button><button className="btn-secondary" onClick={() => onSkip(status.job_id)}>Không blur, tiếp tục xuất final</button></div></div></div></div>;
}

function RenderHistoryPanel({ jobs, onRefresh, onCancel }: { jobs: RenderJobStatus[]; onRefresh: () => void; onCancel: (jobId: string) => void }) {
  return <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm"><div className="mb-3 flex items-center justify-between gap-2"><b>Render History</b><button className="btn-mini" onClick={onRefresh}>Refresh</button></div>{jobs.length === 0 ? <p className="text-slate-500">Chưa có job render.</p> : <div className="max-h-64 space-y-2 overflow-auto pr-1">{jobs.map(job => <div className="rounded-xl border border-white/10 bg-[#070B18] p-3" key={job.job_id}><div className="flex flex-wrap items-center justify-between gap-2"><Pill tone={job.status === 'done' ? 'green' : job.status === 'error' || job.status === 'cancelled' ? 'red' : 'yellow'}>{job.status}</Pill><span className="text-xs text-slate-500">{clampProgress(job.progress)}%</span></div><p className="mt-2 font-semibold text-slate-200">{job.step}</p><p className="text-xs text-slate-400">{job.message}</p><p className="mt-1 break-all text-[11px] text-slate-600">{job.job_id}</p>{(job.status === 'queued' || job.status === 'running') && <button className="btn-mini danger mt-2" onClick={() => onCancel(job.job_id)}>Hủy job</button>}</div>)}</div>}</div>;
}

function BlurReviewPanel({ status }: { status: RenderJobStatus }) {
  const [regions, setRegions] = useState<BlurRegionLocal[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const previewPath = status.result?.pre_blur_video_path || '';

  function stripIds(r: BlurRegionLocal[]): BlurRegion[] {
    return r.map(({ id: _, ...rest }) => rest);
  }

  async function skip() {
    try {
      setSubmitting(true);
      await skipRenderJobBlur(status.job_id);
      toast.success('Đã bỏ qua blur, job sẽ tiếp tục xuất final');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không bỏ qua blur được');
    } finally {
      setSubmitting(false);
    }
  }

  async function apply() {
    if (!regions.length) return toast.error('Vui lòng tạo ít nhất một vùng blur hoặc chọn bỏ qua');
    try {
      setSubmitting(true);
      await applyRenderJobBlur(status.job_id, stripIds(regions));
      toast.success('Đã gửi vùng blur, job sẽ tiếp tục xuất final');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không gửi vùng blur được');
    } finally {
      setSubmitting(false);
    }
  }

  return <div className="mt-4 rounded-2xl border border-yellow-500/30 bg-yellow-500/10 p-4"><h3 className="mb-2 font-bold text-yellow-100">Blur Review</h3><p className="mb-4 text-sm text-slate-300">Video đã được cắt/ghép/chuyển tỉ lệ. Hãy chọn vùng cần làm mờ trước khi burn subtitle hoặc xuất final.</p>{previewPath && <div className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]"><BlurRegionEditor videoUrl={blurPreviewUrl(previewPath)} regions={regions} selected={selected} locked={new Set()} onChange={setRegions} onSelect={(id) => setSelected(id !== null ? new Set([id]) : new Set())} onToggleLock={() => {}} onCurrentTimeChange={setCurrentTime}/><BlurRegionSidebar regions={regions} selected={selected} locked={new Set()} onChange={setRegions} onSelect={(id) => setSelected(id !== null ? new Set([id]) : new Set())} onToggleLock={() => {}} currentTime={currentTime}/></div>}<div className="mt-4 flex flex-wrap gap-2"><button className="btn-secondary" disabled={submitting} onClick={skip}>Không blur, tiếp tục xuất final</button><button className="btn-primary" disabled={submitting || !regions.length} onClick={apply}>Áp dụng blur và tiếp tục</button></div></div>;
}

function RenderResultPanel({ result }: { result: Record<string, string> }) {
  const openFolder = async () => {
    try { await openOutputFolder(result.output_dir || result.final_video_path); toast.success('Đã mở thư mục output'); } catch (e) { toast.error(e instanceof Error ? e.message : 'Không mở được thư mục'); }
  };
  const copyPath = async (value: string) => { await navigator.clipboard.writeText(value); toast.success('Đã copy path'); };
  return <div className="mt-4 space-y-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm"><b>Render Result</b>
    {result.final_video_path && <p className="break-all">Video: {result.final_video_path}</p>}<p className="break-all">SRT: {result.final_subtitle_path}</p>
    <div className="grid gap-2 md:grid-cols-2"><Stat label="Encoder" value={result.video_encoder_label || result.video_encoder || 'N/A'}/><Stat label="Output" value={`${result.output_codec || 'N/A'} ${result.output_fps || ''}`}/><Stat label="Resolution" value={result.output_resolution_actual || 'N/A'}/><Stat label="File size" value={fmtBytes(result.output_file_size_bytes)}/><Stat label="Source" value={`${result.source_codec || 'N/A'} ${result.source_fps || ''}`}/><Stat label="Duration" value={result.output_duration_seconds ? fmt(Number(result.output_duration_seconds)) : 'N/A'}/>{result.tts_plan_path && <Stat label="TTS warnings" value={result.tts_warning_count || '0'}/>}<Stat label="Output cleanup" value={`${result.artifact_retention || 'smart'} · ${result.cleaned_artifact_count || '0'} files`}/></div>
    <div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={openFolder}>Mở thư mục output</button>{result.final_video_path && <a className="btn-secondary" href={fileDownloadUrl(result.final_video_path)}><Download size={16}/>Tải video</a>}<a className="btn-secondary" href={fileDownloadUrl(result.final_subtitle_path)}><Download size={16}/>Tải SRT</a><a className="btn-secondary" href={fileDownloadUrl(result.render_plan_path)}><Download size={16}/>Tải render plan</a>{result.voiceover_path && <a className="btn-secondary" href={fileDownloadUrl(result.voiceover_path)}><Download size={16}/>Tải voiceover</a>}{result.tts_plan_path && <a className="btn-secondary" href={fileDownloadUrl(result.tts_plan_path)}><Download size={16}/>Tải TTS plan</a>}<button className="btn-secondary" onClick={() => copyPath(result.final_video_path || result.final_subtitle_path)}><Copy size={16}/>Copy path</button><button className="btn-secondary" onClick={() => downloadTextFile('render_result.txt', JSON.stringify(result, null, 2))}><Download size={16}/>Tải thông tin</button></div>
  </div>;
}

function LegacyEdlSummary({ payload, stats, onOpen }: { payload: GeminiEdlPayload | null; stats: { subDur: number; segDur: number } | null; onOpen: () => void }) {
  if (!payload) return <Card><SectionTitle icon={Activity} title="EDL Summary" desc="Chưa có JSON hợp lệ"/><p className="empty">Validate JSON để xem/tinh chỉnh EDL.</p></Card>;
  const warnings = payload.video_segments.filter(seg => {
    const vd = parseClipTime(seg.source_end) - parseClipTime(seg.source_start);
    const sub = payload.srt.filter(s => s.index >= seg.subtitle_start && s.index <= seg.subtitle_end);
    const sd = sub.reduce((a, s) => a + parseSrtTime(s.end) - parseSrtTime(s.start), 0);
    const words = sub.map(s => s.text).join(' ').split(/\s+/).filter(Boolean).length;
    return Math.abs(vd - sd) > 2 || vd > 8 || words / Math.max(vd, 1) > 3.2;
  }).length;
  return <Card><SectionTitle icon={Activity} title="EDL Summary" desc="Tổng quan nhanh trước khi render"/>
    <div className="grid gap-3 md:grid-cols-4"><Stat label="Sources" value={`${payload.sources?.length ?? 1}`}/><Stat label="Segments" value={`${payload.video_segments.length}`}/><Stat label="Warnings" value={`${warnings}`}/><Stat label="Duration" value={`${fmt(stats?.subDur ?? 0)} / ${fmt(stats?.segDur ?? 0)}`}/></div>
    <button className="btn-secondary mt-4 w-full" onClick={onOpen}>Mở EDL Inspector để kiểm tra/chỉnh segment</button>
  </Card>;
}

function LegacyEdlInspector({ payload, onApply, onApplyAndValidate }: { payload: GeminiEdlPayload | null; onApply: (payload: GeminiEdlPayload) => void; onApplyAndValidate: (payload: GeminiEdlPayload) => void }) {
  const [draft, setDraft] = useState<GeminiEdlPayload | null>(payload);
  const [selectedId, setSelectedId] = useState<number | null>(payload?.video_segments[0]?.segment_id ?? null);
  useEffect(() => {
    setDraft(payload ? JSON.parse(JSON.stringify(payload)) as GeminiEdlPayload : null);
    setSelectedId(payload?.video_segments[0]?.segment_id ?? null);
  }, [payload]);
  if (!draft) return <Card><SectionTitle icon={Activity} title="EDL Inspector" desc="Chưa có JSON hợp lệ"/><p className="empty">Paste/upload JSON, validate, rồi quay lại tab này để kiểm tra EDL.</p></Card>;
  const ordered = [...draft.video_segments].sort((a, b) => a.order - b.order);
  const selected = ordered.find(seg => seg.segment_id === selectedId) ?? ordered[0];
  const draftStats = {
    subDur: draft.srt.reduce((a, s) => a + Math.max(0, parseSrtTime(s.end) - parseSrtTime(s.start)), 0),
    segDur: draft.video_segments.reduce((a, s) => a + Math.max(0, parseClipTime(s.source_end) - parseClipTime(s.source_start)), 0),
  };
  const hasChanges = JSON.stringify(payload) !== JSON.stringify(draft);
  const total = Math.max(1, ordered.reduce((sum, seg) => sum + Math.max(0, parseClipTime(seg.source_end) - parseClipTime(seg.source_start)), 0));
  const updateSegment = (segmentId: number, patch: Partial<VideoSegment>) => setDraft(current => current ? { ...current, video_segments: current.video_segments.map(seg => seg.segment_id === segmentId ? { ...seg, ...patch } : seg) } : current);
  const shiftSegment = (seg: VideoSegment, delta: number) => {
    const start = Math.max(0, parseClipTime(seg.source_start) + delta);
    const end = Math.max(start + 0.1, parseClipTime(seg.source_end) + delta);
    updateSegment(seg.segment_id, { source_start: legacySecondsToClip(start), source_end: legacySecondsToClip(end) });
  };
  const trimToSubtitle = (seg: VideoSegment) => {
    const sub = draft.srt.filter(s => s.index >= seg.subtitle_start && s.index <= seg.subtitle_end);
    const sd = sub.reduce((a, s) => a + parseSrtTime(s.end) - parseSrtTime(s.start), 0);
    updateSegment(seg.segment_id, { source_end: legacySecondsToClip(parseClipTime(seg.source_start) + sd) });
  };
  return <Card><SectionTitle icon={Activity} title="EDL Inspector" desc="Kiểm tra timeline và chỉnh segment trước khi render"/>
    <div className="mb-4 flex flex-wrap gap-2">{hasChanges ? <Pill tone="yellow">Có thay đổi chưa apply</Pill> : <Pill tone="green">Đồng bộ với JSON</Pill>}<button className="btn-mini" onClick={() => { setDraft(payload ? JSON.parse(JSON.stringify(payload)) as GeminiEdlPayload : null); setSelectedId(payload?.video_segments[0]?.segment_id ?? null); }}>Reset từ JSON</button></div>
    <div className="grid gap-3 md:grid-cols-4"><Stat label="Sources" value={`${draft.sources?.length ?? 1}`}/><Stat label="Subtitle" value={`${draft.srt.length}`}/><Stat label="Segment" value={`${draft.video_segments.length}`}/><Stat label="Duration" value={`${fmt(draftStats.subDur)} / ${fmt(draftStats.segDur)}`}/></div>
    <div className="mt-5 overflow-hidden rounded-2xl border border-white/10 bg-slate-950/50 p-3"><div className="flex h-10 w-full overflow-hidden rounded-xl bg-slate-900">{ordered.map(seg => { const vd = Math.max(0.1, parseClipTime(seg.source_end) - parseClipTime(seg.source_start)); const sub = draft.srt.filter(s => s.index >= seg.subtitle_start && s.index <= seg.subtitle_end); const sd = sub.reduce((a, s) => a + parseSrtTime(s.end) - parseSrtTime(s.start), 0); const warn = Math.abs(vd - sd) > 2 || vd > 8; return <button key={seg.segment_id} title={`#${seg.order} ${fmt(vd)}`} onClick={() => setSelectedId(seg.segment_id)} className={`${selected?.segment_id === seg.segment_id ? 'bg-violet-400' : warn ? 'bg-yellow-500' : 'bg-cyan-500'} border-r border-slate-950 text-center text-[10px] font-bold text-slate-950`} style={{ width: `${(vd / total) * 100}%` }}>{seg.order}</button>; })}</div></div>
    <div className="mt-5 grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
      <div className="max-h-[620px] space-y-3 overflow-auto pr-2">{ordered.map(seg => { const vd = parseClipTime(seg.source_end) - parseClipTime(seg.source_start); const sub = draft.srt.filter(s => s.index >= seg.subtitle_start && s.index <= seg.subtitle_end); const sd = sub.reduce((a, s) => a + parseSrtTime(s.end) - parseSrtTime(s.start), 0); const warn = Math.abs(vd - sd) > 2 || vd > 8; return <button className={`edl-row w-full text-left ${selected?.segment_id === seg.segment_id ? 'border-cyan-400/70' : ''}`} key={seg.segment_id} onClick={() => setSelectedId(seg.segment_id)}><div className="flex items-center justify-between"><b>#{seg.order} Segment {seg.segment_id}</b><Pill tone={warn ? 'yellow' : 'green'}>{warn ? 'Cần kiểm tra' : 'Ổn'}</Pill></div><p className="mt-2 text-sm text-slate-300">{seg.scene_description}</p><p className="mt-2 text-xs text-slate-500">Video {fmt(vd)} | SRT {fmt(sd)}</p></button>; })}</div>
      {selected && <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4"><h3 className="mb-4 text-lg font-bold">Edit Segment #{selected.order}</h3><div className="grid gap-3 md:grid-cols-2"><div><label className="label">Source ID</label><input className="input" value={selected.source_id ?? 'source_1'} onChange={e => updateSegment(selected.segment_id, { source_id: e.target.value })}/></div><div><label className="label">Importance score</label><input className="input" type="number" min={0} max={100} value={selected.importance_score} onChange={e => updateSegment(selected.segment_id, { importance_score: Number(e.target.value) })}/></div><div><label className="label">Source start</label><input className="input" value={selected.source_start} onChange={e => updateSegment(selected.segment_id, { source_start: e.target.value })}/></div><div><label className="label">Source end</label><input className="input" value={selected.source_end} onChange={e => updateSegment(selected.segment_id, { source_end: e.target.value })}/></div><div><label className="label">Subtitle start</label><input className="input" type="number" value={selected.subtitle_start} onChange={e => updateSegment(selected.segment_id, { subtitle_start: Number(e.target.value) })}/></div><div><label className="label">Subtitle end</label><input className="input" type="number" value={selected.subtitle_end} onChange={e => updateSegment(selected.segment_id, { subtitle_end: Number(e.target.value) })}/></div></div><div className="mt-3"><label className="label">Scene description</label><textarea className="textarea min-h-[90px]" value={selected.scene_description} onChange={e => updateSegment(selected.segment_id, { scene_description: e.target.value })}/></div><div className="mt-3 rounded-xl border border-white/10 bg-[#070B18] p-3 text-sm"><b>SRT text</b><p className="mt-2 text-slate-300">{draft.srt.filter(s => s.index >= selected.subtitle_start && s.index <= selected.subtitle_end).map(s => s.text).join(' ')}</p></div><div className="mt-4 flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => shiftSegment(selected, -0.5)}>Shift -0.5s</button><button className="btn-secondary" onClick={() => shiftSegment(selected, 0.5)}>Shift +0.5s</button><button className="btn-secondary" onClick={() => trimToSubtitle(selected)}>Trim theo SRT</button></div></div>}
    </div>
    <div className="mt-5 flex flex-wrap gap-2"><button className="btn-primary" onClick={() => onApplyAndValidate(draft)}>Apply & Validate</button><button className="btn-secondary" onClick={() => onApply(draft)}>Chỉ apply vào JSON</button></div>
  </Card>;
}

function legacySecondsToClip(value: number) {
  const safe = Math.max(0, value);
  const totalMs = Math.round(safe * 1000);
  const ms = totalMs % 1000;
  const totalSeconds = Math.floor(totalMs / 1000);
  const seconds = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3600);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function MaintenancePanel({ stats, cleanupResult, runtimeHealth, presetSyncStatus, licenseStatus, onRefresh, onSyncBuiltins, onCleanup, onActivateLicense, onClearLicense }: { stats: StorageStats | null; cleanupResult: StorageCleanupResponse | null; runtimeHealth: RuntimeHealth | null; presetSyncStatus: PresetSyncStatus | null; licenseStatus: LicenseStatus | null; onRefresh: () => void; onSyncBuiltins: () => void; onCleanup: (target: 'temp' | 'outputs' | 'all', olderThanHours: number, dryRun: boolean) => void; onActivateLicense: (licenseKey: string) => void; onClearLicense: () => void }) {
  const [target, setTarget] = useState<'temp' | 'outputs' | 'all'>('temp');
  const [olderThanHours, setOlderThanHours] = useState(24);
  const [licenseKey, setLicenseKey] = useState('');
  const [updateState, setUpdateState] = useState<'idle' | 'checking' | 'up_to_date' | 'available' | 'error'>('idle');
  const [updateData, setUpdateData] = useState<UpdateCheckResponse | null>(null);
  const [updateError, setUpdateError] = useState('');
  const [launched, setLaunched] = useState(false);
  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false);
  const handleCheckUpdate = async () => {
    setUpdateState('checking');
    setUpdateError('');
    try {
      const data = await checkForUpdates();
      setUpdateData(data);
      setUpdateState(data.update_available ? 'available' : 'up_to_date');
    } catch (err) {
      setUpdateError(err instanceof Error ? err.message : 'Lỗi không xác định.');
      setUpdateState('error');
    }
  };
  const handleLaunchUpdater = async () => {
    setShowUpdateConfirm(false);
    try {
      const data = await launchUpdater();
      setLaunched(true);
      if (data.message) toast.success(data.message);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Không thể mở trình cập nhật.');
    }
  };
  const copyHardwareId = async () => {
    if (!licenseStatus?.hardware_id) return;
    await navigator.clipboard.writeText(licenseStatus.hardware_id);
    toast.success('Đã copy Hardware ID.');
  };
  return <Card><SectionTitle icon={Trash2} title="Bảo trì" desc="Theo dõi dung lượng và dọn file temp/output cũ"/>
    <div className="mb-5 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 font-bold"><KeyRound size={18}/>License</h3><button className="btn-mini" onClick={onRefresh}>Refresh</button></div>
      <div className="grid gap-3 md:grid-cols-4"><Stat label="Status" value={licenseStatus?.status ?? 'N/A'}/><Stat label="Plan" value={licenseStatus?.plan ?? 'N/A'}/><Stat label="Enforcement" value={licenseStatus?.enforcement ? 'ON' : 'OFF'}/><Stat label="Expires" value={licenseStatus?.expires_at ? new Date(licenseStatus.expires_at).toLocaleString() : licenseStatus?.plan === 'lifetime' ? 'Lifetime' : 'N/A'}/></div>
      <p className="mt-3 text-sm text-slate-200">{licenseStatus?.message ?? 'Chưa tải trạng thái license.'}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm"><span className="text-slate-400">Hardware ID:</span><b className="tracking-widest text-cyan-100">{licenseStatus?.hardware_id ?? 'N/A'}</b><button className="btn-mini" onClick={copyHardwareId}><Copy size={14}/>Copy</button></div>
      {licenseStatus?.customer_name && <p className="mt-2 text-xs text-slate-400">Customer: {licenseStatus.customer_name} {licenseStatus.customer_email ? `(${licenseStatus.customer_email})` : ''}</p>}
      <div className="mt-4 grid gap-3"><label className="label">Paste license key</label><textarea className="textarea min-h-[96px]" placeholder="MRTRIS-V1-..." value={licenseKey} onChange={e => setLicenseKey(e.target.value)}/><div className="flex flex-wrap gap-2"><button className="btn-primary" onClick={() => onActivateLicense(licenseKey)} disabled={!licenseKey.trim()}>Activate</button><button className="btn-secondary" onClick={() => setLicenseKey('')}>Clear input</button><button className="btn-secondary" onClick={() => { if (confirm('Xóa license local trên máy này?')) onClearLicense(); }}>Clear local license</button></div></div>
    </div>
    <div className="mb-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">Runtime Health</h3><button className="btn-mini" onClick={onRefresh}>Refresh</button></div>
      <div className="grid gap-3 md:grid-cols-4"><Stat label="Backend PID" value={`${runtimeHealth?.pid ?? 'N/A'}`}/><Stat label="Started" value={runtimeHealth?.backend_started_at ? new Date(runtimeHealth.backend_started_at * 1000).toLocaleTimeString() : 'N/A'}/><Stat label="TTS" value={runtimeHealth?.tts_status?.status ?? 'N/A'}/><Stat label="Encoder" value={runtimeHealth?.video_encoder_auto_result?.label ?? runtimeHealth?.video_encoder_auto_result?.error ?? 'N/A'}/></div>
      <p className="mt-3 break-all text-xs text-slate-500">Python: {runtimeHealth?.python_executable ?? 'N/A'}</p>
    </div>
    <div className="mb-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 font-bold"><Download size={18}/>Phiên bản & Cập nhật</h3><button className="btn-mini" onClick={handleCheckUpdate} disabled={updateState === 'checking'}>{updateState === 'checking' ? 'Đang kiểm tra...' : 'Kiểm tra cập nhật'}</button></div>
      {updateState === 'checking' && <p className="text-sm text-slate-300">Đang kiểm tra...</p>}
      {updateState === 'idle' && <p className="text-sm text-slate-400">Nhấn "Kiểm tra cập nhật" để kiểm tra phiên bản mới.</p>}
      {updateState === 'up_to_date' && <div><div className="grid gap-3 md:grid-cols-2"><Stat label="Phiên bản hiện tại" value={updateData?.local_version ?? 'N/A'}/><Stat label="Kênh" value={updateData?.channel ?? 'N/A'}/></div><p className="mt-2 text-sm text-green-400">{updateData?.message}</p></div>}
      {updateState === 'available' && <div><div className="grid gap-3 md:grid-cols-2"><Stat label="Phiên bản hiện tại" value={updateData?.local_version ?? 'N/A'}/><Stat label="Phiên bản mới nhất" value={updateData?.remote_version ?? 'N/A'}/></div><p className="mt-2 text-sm text-amber-400">{updateData?.message}</p>{updateData && updateData.notes && updateData.notes.length > 0 && <div className="mt-2 max-h-24 overflow-auto rounded-xl border border-white/10 bg-slate-950/60 p-2 text-xs text-slate-300">{updateData.notes.map((note: string, i: number) => <p key={i} className="mb-1">• {note}</p>)}</div>}<div className="mt-3 flex flex-wrap items-center gap-2"><button className="btn-primary" onClick={() => setShowUpdateConfirm(true)} disabled={launched}>{launched ? 'Đã mở' : 'Mở trình cập nhật'}</button>{launched && <span className="text-xs text-slate-300">Trình cập nhật đã mở. Ứng dụng sẽ tự đóng, cập nhật và khởi động lại.</span>}</div>{showUpdateConfirm && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowUpdateConfirm(false)}><div className="mx-4 w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl" onClick={e => e.stopPropagation()}><h3 className="mb-3 text-lg font-bold">Cập nhật và khởi động lại?</h3><p className="mb-6 text-sm text-slate-300">MrTris_AUTO sẽ tự đóng, cập nhật lên bản mới nhất, rồi khởi động lại. Hãy lưu công việc đang làm trước khi tiếp tục.</p><div className="flex justify-end gap-3"><button className="btn-secondary" onClick={() => setShowUpdateConfirm(false)}>Hủy</button><button className="btn-primary" onClick={handleLaunchUpdater}>Cập nhật ngay</button></div></div></div>}</div>}
      {updateState === 'error' && <p className="text-sm text-red-400">Kiểm tra thất bại: {updateError}</p>}
    </div>
    <div className="mb-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold">Preset DB Sync</h3><button className="btn-mini" onClick={onSyncBuiltins}>Sync built-in presets</button></div>
      <div className="grid gap-3 md:grid-cols-4"><Stat label="Status" value={presetSyncStatus?.in_sync ? 'In sync' : 'Needs sync'}/><Stat label="Expected" value={`${presetSyncStatus?.expected_count ?? 0}`}/><Stat label="DB builtins" value={`${presetSyncStatus?.db_builtin_count ?? 0}`}/><Stat label="Outdated" value={`${presetSyncStatus?.outdated.length ?? 0}`}/></div>
      {presetSyncStatus && !presetSyncStatus.in_sync && <div className="mt-3 max-h-40 overflow-auto rounded-xl border border-yellow-500/20 bg-yellow-500/10 p-3 text-xs text-yellow-100">{presetSyncStatus.missing.map(item => <p key={`m-${item.id}`}>Missing: {item.name}</p>)}{presetSyncStatus.outdated.map(item => <p key={`o-${item.id}`}>Outdated: {item.name} ({item.fields.join(', ')})</p>)}{presetSyncStatus.extra_builtin_ids.map(id => <p key={`e-${id}`}>Extra builtin id: {id}</p>)}</div>}
    </div>
    <div className="grid gap-3 md:grid-cols-4"><Stat label="Outputs" value={fmtBytes(stats?.outputs_size_bytes)}/><Stat label="Temp" value={fmtBytes(stats?.temp_size_bytes)}/><Stat label="Output items" value={`${stats?.outputs_count ?? 0}`}/><Stat label="Temp items" value={`${stats?.temp_count ?? 0}`}/></div>
    <div className="mt-5 grid gap-3 md:grid-cols-3"><div><label className="label">Target</label><select className="select-ghost" value={target} onChange={e => setTarget(e.target.value as typeof target)}><option value="temp">Temp</option><option value="outputs">Outputs</option><option value="all">All</option></select></div><div><label className="label">Cũ hơn</label><select className="select-ghost" value={olderThanHours} onChange={e => setOlderThanHours(Number(e.target.value))}><option value={1}>1 giờ</option><option value={6}>6 giờ</option><option value={24}>24 giờ</option><option value={168}>7 ngày</option><option value={720}>30 ngày</option></select></div><div className="flex items-end gap-2"><button className="btn-secondary" onClick={onRefresh}>Refresh</button><button className="btn-secondary" onClick={() => onCleanup(target, olderThanHours, true)}>Xem trước</button><button className="btn-primary" onClick={() => { if (confirm('Bạn chắc chắn muốn xóa các file cũ đã chọn?')) onCleanup(target, olderThanHours, false); }}>Dọn dẹp</button></div></div>
    {cleanupResult && <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm"><b>{cleanupResult.dry_run ? 'Dry run' : 'Cleanup result'}</b><div className="mt-3 grid gap-2 md:grid-cols-3"><Stat label="Matched" value={`${cleanupResult.matched_count}`}/><Stat label="Deleted" value={`${cleanupResult.deleted_count}`}/><Stat label="Freed" value={fmtBytes(cleanupResult.freed_bytes)}/></div>{cleanupResult.items.length > 0 && <div className="mt-3 max-h-52 overflow-auto text-xs text-slate-400">{cleanupResult.items.map(item => <p className="break-all" key={item}>{item}</p>)}</div>}</div>}
  </Card>;
}

function PresetManager({ presets, draft, setDraft, editingId, setEditingId, onSave, onCancel, onClone, onDelete }: { presets: Preset[]; draft: PresetDraft; setDraft: (draft: PresetDraft) => void; editingId: string | null; setEditingId: (id: string | null) => void; onSave: () => void; onCancel: () => void; onClone: (preset: Preset) => void; onDelete: (preset: Preset) => void }) {
  const editingPreset = presets.find(p => p.id === editingId);
  const updateDraft = <K extends keyof PresetDraft>(key: K, value: PresetDraft[K]) => setDraft({ ...draft, [key]: value });
  const selectField = (key: keyof PresetDraft, label: string, values: readonly string[]) => {
    const current = String(draft[key] ?? '');
    return <div><label className="label">{label}</label><select className="select-ghost" value={current} onChange={e => updateDraft(key, e.target.value as never)}>{optionsWithCurrent(values, current).map(v => <option key={v} value={v}>{v}</option>)}</select></div>;
  };
  return <Card><SectionTitle icon={FolderCog} title="Quản lý Preset" desc="Tạo, sửa, nhân bản và xóa preset cá nhân"/>
    {editingPreset && <div className="mb-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-3 text-sm"><b>Đang sửa:</b> {editingPreset.name}</div>}
    <div className="grid gap-3">
      <div><label className="label">Tên preset</label><input className="input" placeholder="Tên preset" value={draft.name} onChange={e => updateDraft('name', e.target.value)}/></div>
      <div><label className="label">Mô tả</label><textarea className="textarea min-h-[90px]" placeholder="Mô tả preset" value={draft.description} onChange={e => updateDraft('description', e.target.value)}/></div>
      <div className="grid gap-3 md:grid-cols-2">
        {selectField('rewrite_style', optionGroups.rewrite_style.label, optionGroups.rewrite_style.values)}
        {selectField('target_audience', optionGroups.target_audience.label, optionGroups.target_audience.values)}
        {selectField('tone', optionGroups.tone.label, optionGroups.tone.values)}
        {selectField('target_duration', optionGroups.target_duration.label, optionGroups.target_duration.values)}
        {selectField('retention_mode', optionGroups.retention_mode.label, optionGroups.retention_mode.values)}
        {selectField('hook_style', optionGroups.hook_style.label, optionGroups.hook_style.values)}
        {selectField('clip_strategy', optionGroups.clip_strategy.label, optionGroups.clip_strategy.values)}
        {selectField('reuse_level', optionGroups.reuse_level.label, optionGroups.reuse_level.values)}
        {selectField('content_density', optionGroups.content_density.label, optionGroups.content_density.values)}
        {selectField('target_language', localizationSelectGroups.target_language.label, localizationSelectGroups.target_language.values)}
        {selectField('target_market', localizationSelectGroups.target_market.label, localizationSelectGroups.target_market.values)}
        <div><label className="label">Mức localize</label><select className="select-ghost" value={draft.localization_level} onChange={e => updateDraft('localization_level', e.target.value as PresetDraft['localization_level'])}><option value="none">Không localize</option><option value="light">Nhẹ</option><option value="medium">Trung bình</option><option value="heavy">Mạnh</option></select></div>
        <div><label className="label">Chế độ chuyển thể</label><select className="select-ghost" value={draft.adaptation_mode} onChange={e => updateDraft('adaptation_mode', e.target.value as PresetDraft['adaptation_mode'])}><option value="faithful">Giữ sát bản gốc</option><option value="localized">Bản địa hóa</option><option value="inspired">Lấy cảm hứng</option></select></div>
        <div><label className="label">Persona người kể</label><select className="select-ghost" value={draft.narrator_persona} onChange={e => updateDraft('narrator_persona', e.target.value as PresetDraft['narrator_persona'])}>{localizationSelectGroups.narrator_persona.values.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}</select></div>
      </div>
      <div className="grid gap-2 md:grid-cols-2">{localizationSwitches.map(([key, label]) => <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm" key={key}><input type="checkbox" checked={Boolean(draft[key])} onChange={e => updateDraft(key, e.target.checked)}/>{label}</label>)}</div>
      <div className="flex flex-wrap gap-2"><button className="btn-primary" onClick={onSave}><Plus size={18}/>{editingId ? 'Lưu cập nhật preset' : 'Tạo preset mới'}</button>{editingId && <button className="btn-secondary" onClick={onCancel}>Hủy sửa</button>}</div>
    </div>
    <div className="mt-5 space-y-3">{presets.map(p => <div className="preset-row" key={p.id}><div><b>{p.name}</b><p>{p.description}</p><Pill tone={p.is_builtin ? 'violet' : 'cyan'}>{p.is_builtin ? 'Mặc định' : 'Cá nhân'}</Pill></div><div className="flex flex-wrap gap-2"><button className="btn-mini" onClick={() => { setEditingId(p.id); setDraft(presetToDraft(p)); }} disabled={p.is_builtin}>Sửa</button>{p.is_builtin && <button className="btn-mini" onClick={() => onClone(p)}>Nhân bản</button>}<button className="btn-mini danger" disabled={p.is_builtin} onClick={() => onDelete(p)}><XCircle size={14}/>Xóa</button></div></div>)}</div>
  </Card>;
}
