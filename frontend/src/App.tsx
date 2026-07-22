import { useEffect, useRef, useState } from 'react';

import { Toaster, toast } from 'sonner';

import { Bell, Copy, Download, ExternalLink, Film, FolderOpen, KeyRound, Loader2, Play, Plus, Sparkles, Trash2, Upload, Wand2 } from 'lucide-react';

import { activateLicense, applyRenderJobBlur, blurPreviewUrl, cancelAutoPipeline, cancelBatch, checkForUpdates, cleanupFinalVideos, cleanupStorage, clearLicense, connectAutoPipelineWS, deleteSavedCookies, fetchAutoPipelineStatus, fetchBatchProgress, fetchFinalVideosPath, fetchGeminiModels, fetchGeminiSessionStatus, fetchLicenseStatus, fetchRenderJob, fetchRenderPreferences, fetchRuntimeHealth, fetchSavedCookies, fetchStorageStats, fetchTtsStatus, fetchTtsVoices, fileDownloadUrl, launchUpdater, openGeminiBrowser, openOutputFolder, saveRenderPreferences, skipRenderJobBlur, startAutoPipeline, startBatchAutoPipeline, startRenderJob, unbindLicenseDevice, uploadCookies } from './api';
import { BlurRegionEditor, BlurRegionSidebar, BlurTool } from './components/BlurTool';

import { AutoPipelineProgress } from './components/AutoPipelineProgress';

import { BatchPipelineProgress } from './components/BatchPipelineProgress';



import { Card, Pill, SectionTitle, Stat } from './components/common';

import { TitleTool } from './components/TitleTool';

import SubtitleGallery from './components/SubtitleGallery';

import { SubtitleStyleSelector } from './components/SubtitleStyleSelector';

import { TtsPanel } from './components/TtsPanel';
import { TtsStudioPanel } from './components/TtsStudioPanel';

import { targetLanguageOptions } from './constants/options';


import type { AutoPipelineProgress as AutoPipelineProgressData, BatchProgress, BlurRegion, GeminiEdlPayload, GeminiModelOption, GeminiModelsResponse, GeminiSessionStatus, GeminiThinkingMode, LicenseStatus, OutputResolution, PromptForm, RenderJobStatus, RenderOptions, RenderQuality, RuntimeHealth, StorageCleanupResponse, StorageStats, SubtitleMode, TtsVoice, UpdateCheckResponse, VerticalMode } from './types';
import type { BlurRegionLocal } from './components/BlurTool';

import { downloadTextFile } from './utils/download';



function isUuidJobId(value: unknown): value is string {

  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

}



type StepState = 'idle' | 'running' | 'done' | 'error';

type AppTab = 'workflow' | 'blur' | 'title' | 'tts' | 'tts-studio' | 'maintenance';



const initialForm: PromptForm = {

  source_mode: 'single',

  youtube_url: '',

  youtube_urls_text: '',

  ytdlp_cookies_file: '',

  target_language: 'Tiếng Việt',

  user_instruction: '',

};







const renderStepLabels = ['Chuẩn bị render', 'Tải video', 'Ghép nội dung', 'Xuất video'];

const defaultRenderOptions: RenderOptions = { vertical_mode: 'none', render_quality: 'balanced', output_resolution: 'auto', render_stability: 'stable', video_encoder: 'auto', segment_fps: '60', blur_mode: 'none', tts_mode: 'none', tts_engine: 'edge_tts', tts_persona: 'neutral', tts_voice_region: 'auto', tts_voice_gender: 'female', tts_voice_id: 'auto', tts_voice_mode: 'preset', tts_clone_voice_id: '', tts_emotion: 'natural', tts_fit_policy: 'segment_uniform', tts_max_speed: 1.5, tts_temperature: 0.4, tts_top_k: 50, tts_max_chars: 256, tts_apply_watermark: false, original_audio_mode: 'lower_fixed', original_audio_volume: 0.3, voiceover_volume: 1.0, title_mode: 'auto', title_text: '', title_style: 'yellow_highlight', title_font_size: 'auto', title_max_lines: 2, title_chars_per_line: 34, title_position: 'top', title_text_align: 'center', title_show_duration: 'full', title_intro_seconds: 5, title_badge_mode: 'none', title_badge_text: '', title_header_height: 0, title_safe_margin: 0, subtitle_style: 'default', subtitle_font_size: 'auto', subtitle_position: 'bottom', subtitle_text_align: 'center', subtitle_max_chars_per_line: 40, subtitle_outline: true, subtitle_shadow: false, subtitle_box: true, artifact_retention: 'smart', video_speed: 1.0 };

const languageVoiceDefaults: Record<string, { localePrefix: string; female: RenderOptions['tts_voice_id']; male: RenderOptions['tts_voice_id'] }> = {
  'Tiếng Việt': { localePrefix: 'vi-VN', female: 'vi-VN-HoaiMyNeural', male: 'vi-VN-NamMinhNeural' },
  English: { localePrefix: 'en-US', female: 'en-US-JennyNeural', male: 'en-US-GuyNeural' },
  German: { localePrefix: 'de-DE', female: 'de-DE-KatjaNeural', male: 'de-DE-ConradNeural' },
  Japanese: { localePrefix: 'ja-JP', female: 'ja-JP-NanamiNeural', male: 'ja-JP-KeitaNeural' },
  Spanish: { localePrefix: 'es-MX', female: 'es-MX-DaliaNeural', male: 'es-MX-JorgeNeural' },
  Korean: { localePrefix: 'ko-KR', female: 'ko-KR-SunHiNeural', male: 'ko-KR-InJoonNeural' },
};

function syncVoiceForLanguage(language: string, options: RenderOptions): RenderOptions {
  const defaults = languageVoiceDefaults[language];
  if (!defaults) return options;
  const currentVoice = options.tts_voice_id;
  if (currentVoice !== 'auto' && currentVoice.startsWith(defaults.localePrefix)) return options;
  const gender = options.tts_voice_gender === 'male' ? 'male' : 'female';
  return { ...options, tts_voice_gender: gender, tts_voice_id: defaults[gender] };
}


const renderOptionLabels: Partial<Record<keyof RenderOptions, string>> = { tts_mode: 'Giọng đọc', tts_persona: 'Cá tính giọng', tts_voice_region: 'Vùng miền', tts_voice_gender: 'Giới tính', tts_voice_id: 'Giọng cụ thể', tts_voice_mode: 'Chế độ giọng', tts_emotion: 'Cảm xúc', tts_max_speed: 'Tốc độ tối đa', original_audio_mode: 'Audio gốc', original_audio_volume: 'Âm lượng audio gốc', voiceover_volume: 'Âm lượng giọng đọc', video_speed: 'Tốc độ video', artifact_retention: 'File xuất ra', title_mode: 'Chế độ tiêu đề', title_style: 'Kiểu tiêu đề', title_position: 'Vị trí tiêu đề', title_text_align: 'Canh chữ tiêu đề', title_show_duration: 'Thời lượng tiêu đề', title_badge_mode: 'Huy hiệu tiêu đề' };



function renderOptionValue(value: unknown) {

  if (typeof value === 'number') return value <= 2 ? `${Math.round(value * 100)}%` : String(value);

  if (typeof value === 'boolean') return value ? 'Bật' : 'Tắt';

  return String(value ?? '');

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

  const segmentText = status?.total_segments ? `Đã xử lý ${status.completed_segments ?? 0}/${status.total_segments} đoạn` : 'Đang chờ thông tin đoạn';



  return <div className="render-status-card">

    <div className="flex items-center justify-between gap-3">

      <div>

        <p className="text-xs uppercase tracking-wider text-slate-500">Tiến trình dựng video</p>

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

    

  </div>;

}



export function App() {

  const [form, setForm] = useState<PromptForm>(initialForm);

  const [jsonText, setJsonText] = useState('');

  const [jsonPayload, setJsonPayload] = useState<GeminiEdlPayload | null>(null);

  const [jsonErrors, setJsonErrors] = useState<string[]>([]);

  const [jsonValid, setJsonValid] = useState(false);

  const [renderSteps, setRenderSteps] = useState<StepState[]>(['idle', 'idle', 'idle', 'idle']);

  const [renderStatus, setRenderStatus] = useState<RenderJobStatus | null>(null);



  const [isRendering, setIsRendering] = useState(false);

  const [subtitleMode, setSubtitleMode] = useState<SubtitleMode>('none');

  const [renderOptions, setRenderOptions] = useState<RenderOptions>(defaultRenderOptions);

  const [renderDoneBell, setRenderDoneBell] = useState(true);

  const [activeTab, setActiveTab] = useState<AppTab>('workflow');

  const [storageStats, setStorageStats] = useState<StorageStats | null>(null);

  const [updateAvailable, setUpdateAvailable] = useState<UpdateCheckResponse | null>(null);
  const updateToastShownRef = useRef(false);

  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);

  const [licenseStatus, setLicenseStatus] = useState<LicenseStatus | null>(null);

  const [autoPipelineProgress, setAutoPipelineProgress] = useState<AutoPipelineProgressData | null>(null);

  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null);

  const [isAutoPipelineRunning, setIsAutoPipelineRunning] = useState(false);


  const [geminiSessionStatus, setGeminiSessionStatus] = useState<GeminiSessionStatus | null>(null);

  const [geminiUserDataDir, setGeminiUserDataDir] = useState<string | null>(null);
  const [geminiThinkingMode, setGeminiThinkingMode] = useState<GeminiThinkingMode>('extended');
  const [geminiModel, setGeminiModel] = useState('gemini-3.6-flash');
  const [geminiModelOptions, setGeminiModelOptions] = useState<GeminiModelOption[]>([]);

  const [isOpeningBrowser, setIsOpeningBrowser] = useState(false);
  const disconnectAutoPipelineWS = useRef<(() => void) | null>(null);

  const [autoRenderStatus, setAutoRenderStatus] = useState<RenderJobStatus | null>(null);

  const autoRenderJobIdRef = useRef<string | null>(null);

  const autoRenderPollCancelledRef = useRef(false);

  const autoRenderPollStartedRef = useRef(false);

  const batchPollCancelledRef = useRef(false);

  const [finalVideosPath, setFinalVideosPath] = useState<string | null>(null);

  useEffect(() => {
    void loadSavedCookies();
    void loadRenderPreferences();
    void loadLicenseStatus();
    void loadGeminiSessionStatus();
    void fetchGeminiModels().then((r: GeminiModelsResponse) => {
      setGeminiModelOptions(r.models);
      setGeminiModel(r.default_model);
    }).catch(() => {});
    void fetchFinalVideosPath().then(setFinalVideosPath).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    checkForUpdates()
      .then(data => {
        if (cancelled || !data.update_available) return;
        setUpdateAvailable(data);
        if (!updateToastShownRef.current) {
          updateToastShownRef.current = true;
          toast.info(`Có phiên bản mới ${data.remote_version}`, {
            action: { label: 'Xem chi tiết', onClick: () => setActiveTab('maintenance') },
            duration: 8000,
          });
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  async function loadStorageStats() {

    try { setStorageStats(await fetchStorageStats()); } catch { toast.error('Không tải được thống kê dung lượng.'); }

  }



  async function loadRuntimeHealth() {

    try {

      const health = await fetchRuntimeHealth();

      setRuntimeHealth(health);

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



  async function unbindLicenseFromUi() {

    if (!confirm('Hủy liên kết thiết bị này khỏi license hiện tại?')) return;

    try {

      await unbindLicenseDevice();

      await loadLicenseStatus();

      toast.success('Đã hủy liên kết thiết bị.');

    } catch (e) {

      toast.error(e instanceof Error ? e.message : 'Không hủy liên kết thiết bị được.');

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

      const res = await openGeminiBrowser();

      setGeminiUserDataDir(res.user_data_dir ?? null);

      toast.success(res.message);
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

    return () => { clearInterval(interval); autoRenderPollCancelledRef.current = true; batchPollCancelledRef.current = true; };

  }, []);



  async function pollBatchProgress(batchId: string) {

    batchPollCancelledRef.current = false;

    while (!batchPollCancelledRef.current) {

      await new Promise(resolve => setTimeout(resolve, 2000));

      if (batchPollCancelledRef.current) break;

      try {

        const next = await fetchBatchProgress(batchId);

        if (batchPollCancelledRef.current) break;

        setBatchProgress(next);

        if (next.status === 'done') {

          setIsAutoPipelineRunning(false);

          toast.success('Xử lý hàng loạt hoàn tất!');

          if (renderDoneBell) playRenderDoneBell();

          break;

        }

        if (next.status === 'cancelled') {

          setIsAutoPipelineRunning(false);

          toast.warning('Batch đã bị hủy');

          break;

        }

        if (next.status === 'error') {

          setIsAutoPipelineRunning(false);

          toast.error(next.error || 'Batch thất bại');

          break;

        }

      } catch {

        // Keep polling through transient network errors.

      }

    }

  }



  async function pollAutoPipelineStatus(taskId: string) {

    autoRenderPollCancelledRef.current = false;

    while (!autoRenderPollCancelledRef.current) {

      await new Promise(resolve => setTimeout(resolve, 2000));

      if (autoRenderPollCancelledRef.current) break;

      try {

        const data = await fetchAutoPipelineStatus(taskId);

        if (autoRenderPollCancelledRef.current) break;

        setAutoPipelineProgress(data);



        if (data.status === 'done') {

          setIsAutoPipelineRunning(false);

          const rawJobId = data.result?.job_id;

          const jobId = isUuidJobId(rawJobId) ? rawJobId : null;

          if (jobId) {

            autoRenderJobIdRef.current = jobId;

            toast.success('Auto pipeline hoàn tất! Đang chờ render...');

            if (!autoRenderPollStartedRef.current) {

              autoRenderPollStartedRef.current = true;

              void pollAutoRenderJob(jobId);

            }

          } else {

            toast.success('Auto pipeline hoàn tất!');

          }

          break;

        }



        if (data.status === 'error') {

          setIsAutoPipelineRunning(false);

          toast.error(data.error || data.message || 'Pipeline thất bại.');

          break;

        }



        if (data.result?.job_id) {

          const rawJobId = data.result.job_id;

          const jobId = isUuidJobId(rawJobId) ? rawJobId : null;

          if (jobId) {

            const isNew = autoRenderJobIdRef.current !== jobId;

            autoRenderJobIdRef.current = jobId;

            if (isNew) toast.success(`Render job đã được tạo: ${jobId}`);

            if (!autoRenderPollStartedRef.current) {

              autoRenderPollStartedRef.current = true;

              void pollAutoRenderJob(jobId);

            }

          }

        }

      } catch {

        // Keep polling through transient network errors

      }

    }

  }



  async function pollAutoRenderJob(jobId: string) {

    autoRenderPollCancelledRef.current = false;

    const initial = { job_id: jobId, status: 'queued', step: 'Dựng video tự động', message: 'Pipeline hoàn tất, đang chờ render...', progress: 0, completed_segments: 0, total_segments: null, started_at: null, updated_at: null, elapsed_seconds: null, estimated_total_seconds: null, remaining_seconds: null, result: null, errors: [] } satisfies RenderJobStatus;

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



  const hasVideoSource = Boolean(form.youtube_url || jsonPayload?.sources?.length);

  const canRender = Boolean((subtitleMode === 'srt_only' || hasVideoSource) && jsonPayload && jsonValid && !isRendering);

  const updateForm = (key: keyof PromptForm, value: string | boolean) => setForm(prev => ({ ...prev, [key]: value }));

  const updateTargetLanguage = (language: string) => {
    setForm(prev => ({ ...prev, target_language: language }));
    setRenderOptions(prev => syncVoiceForLanguage(language, prev));
  };





  async function handleAutoPipeline() {

    try {

      disconnectAutoPipelineWS.current?.();

      autoRenderPollCancelledRef.current = true;

      autoRenderJobIdRef.current = null;

      setAutoRenderStatus(null);

      setBatchProgress(null);

      batchPollCancelledRef.current = true;



      const urls = form.source_mode === 'multi'

        ? parseYoutubeUrls(form.youtube_urls_text).map(u => u.startsWith('http') ? u : `https://${u}`)

        : [form.youtube_url.trim()].filter(Boolean).map(u => u.startsWith('http') ? u : `https://${u}`);

      if (!urls.length) return toast.error('Vui lòng nhập ít nhất một link YouTube');



      if (urls.length > 1) {

        setIsAutoPipelineRunning(true);

        setAutoPipelineProgress(null);

        const formPayload = { ...form, youtube_url: urls[0], youtube_urls: urls, source_mode: 'multi' };

        const batch = await startBatchAutoPipeline({

          form_data: formPayload,

          render_options: renderOptions,

          subtitle_mode: subtitleMode,

          ytdlp_cookies_file: form.ytdlp_cookies_file || undefined,

          user_data_dir: geminiUserDataDir || undefined,
          headless: true,
          gemini_thinking_mode: geminiThinkingMode,
          gemini_model: geminiModel,

        });

        setBatchProgress(batch);

        toast.success(`Đã bắt đầu batch ${batch.total_items} video`);

        void pollBatchProgress(batch.batch_id);

        return;

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

        states: [{ step: 'init', label: 'Khởi tạo', status: 'running', start_ts: Date.now(), end_ts: null }],

      });



      const formPayload = { ...form, youtube_url: urls[0], youtube_urls: urls, source_mode: form.source_mode };

      const renderPayload = {

        render_options: renderOptions,

        subtitle_mode: subtitleMode,

        ytdlp_cookies_file: form.ytdlp_cookies_file || undefined,

        user_data_dir: geminiUserDataDir || undefined,
      };



      const res = await startAutoPipeline({ form_data: formPayload, ...renderPayload, headless: true, gemini_thinking_mode: geminiThinkingMode, gemini_model: geminiModel });

      setAutoPipelineProgress((prev: AutoPipelineProgressData | null) => prev ? { ...prev, task_id: res.task_id } : null);





      autoRenderPollStartedRef.current = false;

      autoRenderJobIdRef.current = null;

      void pollAutoPipelineStatus(res.task_id);

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

    setAutoPipelineProgress(null);

    setAutoRenderStatus(null);

    setIsAutoPipelineRunning(false);

    setIsRendering(false);

    cancelAutoPipeline(taskId).catch(() => {});

    toast.warning('Đã hủy auto pipeline');

  }



  function handleCancelBatchPipeline() {

    const batchId = batchProgress?.batch_id;

    if (!batchId) return;

    batchPollCancelledRef.current = true;

    cancelBatch(batchId).catch(() => {});

    setBatchProgress(prev => prev ? { ...prev, status: 'cancelled', ended_at: Date.now() / 1000, items: prev.items.map(item => item.status === 'pending' || item.status === 'running' ? { ...item, status: 'cancelled', ended_at: Date.now() / 1000 } : item) } : null);

    setIsAutoPipelineRunning(false);

    disconnectAutoPipelineWS.current?.();

    setAutoPipelineProgress(null);

    toast.warning('Đã hủy batch auto pipeline');

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

    setRenderStatus({ job_id: '', status: 'queued', step: 'Gửi yêu cầu dựng video', message: 'Đang gửi yêu cầu render...', progress: 0, completed_segments: 0, total_segments: jsonPayload.video_segments.length, errors: [] });



    try {

      await saveRenderPreferences({ subtitle_mode: subtitleMode, render_done_bell: renderDoneBell, render_options: renderOptions });

      const job = await startRenderJob({ youtube_url: subtitleMode === 'srt_only' ? undefined : form.youtube_url || undefined, ytdlp_cookies_file: form.ytdlp_cookies_file || undefined, user_data_dir: geminiUserDataDir || undefined, gemini_json: jsonPayload, burn_subtitle: subtitleMode === 'burn', subtitle_mode: subtitleMode, render_options: renderOptions });
      toast.success(`Đã bắt đầu job ${job.job_id}`);

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



  async function runFullCleanup() {

    try {

      const result = await cleanupStorage({ target: "all", older_than_hours: 0, dry_run: false });

      toast.success(`Đã dọn ${result.deleted_count} mục, giải phóng ${fmtBytes(result.freed_bytes)}`);

      await loadStorageStats();

    } catch (e) {

      toast.error(e instanceof Error ? e.message : 'Dọn dẹp thất bại');

    }

  }

  if (licenseStatus === null) {
    return <div className="min-h-screen bg-[#070B18] text-slate-100">
      <Toaster richColors position="top-right"/>
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="animate-spin" size={32} />
      </div>
    </div>;
  }

  if (licenseStatus.enforcement && !licenseStatus.licensed) {
    return <div className="min-h-screen bg-[#070B18] text-slate-100">
      <Toaster richColors position="top-right"/>
      <LicenseGate licenseStatus={licenseStatus} onActivate={activateLicenseFromUi} onRefresh={loadLicenseStatus}/>
    </div>;
  }

  return <div className="min-h-screen bg-[#070B18] text-slate-100">

    <Toaster richColors position="top-right"/>
    <main className="mx-auto max-w-7xl space-y-6 p-5">
      <header className="panel flex flex-col justify-between gap-4 md:flex-row md:items-center">

        <div className="flex items-center gap-3"><div className="logo"><Sparkles size={24}/></div><div><h1 className="text-2xl font-black">AI Video Rewriter & Video Rebuilder</h1><p className="text-sm text-slate-400">Tự động phân tích, tái cấu trúc và dựng video từ link YouTube</p></div></div>

        <Pill tone={renderStatus?.status === 'done' ? 'green' : renderStatus?.status === 'error' || renderStatus?.status === 'cancelled' ? 'red' : isRendering ? 'yellow' : 'cyan'}>{renderStatus?.status ?? 'idle'}</Pill>

      </header>



      <div className="panel flex flex-wrap gap-2">

        <button className={activeTab === 'workflow' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('workflow')}>Làm video</button>

        <button className={activeTab === 'blur' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('blur')}>Làm mờ</button>

        <button className={activeTab === 'title' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('title')}>Tiêu đề</button>

        <button className={activeTab === 'tts' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('tts')}>Giọng đọc</button>

        <button className={activeTab === 'tts-studio' ? 'btn-primary' : 'btn-secondary'} onClick={() => setActiveTab('tts-studio')}>TTS Studio</button>

        <button className={`relative ${activeTab === 'maintenance' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => { setActiveTab('maintenance'); void loadStorageStats(); void loadRuntimeHealth(); void loadLicenseStatus(); }}>Bảo trì{updateAvailable && <span className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-green-500 text-[10px] font-bold text-white shadow-sm">!</span>}</button>

      </div>

      {activeTab === 'workflow' && finalVideosPath && (
        <div className="mb-4 flex items-center justify-end">
          <button className="btn-ghost flex items-center gap-1.5 text-sm" onClick={() => { openOutputFolder(finalVideosPath); }}>
            <FolderOpen size={16}/> Mở thư mục video đã xuất
          </button>
        </div>
      )}

      {activeTab === 'workflow' ? <div className="grid gap-6 xl:grid-cols-[1.2fr_.8fr]">
        <div className="space-y-6">

          <Card><SectionTitle icon={Wand2} title="1. Thiết lập remake" desc="Nhập link, chọn phong cách và xác minh Gemini nếu cần"/>

            <label className="label">Chế độ nguồn video</label>

            <select className="select-ghost" value={form.source_mode} onChange={e => updateForm('source_mode', e.target.value)}><option value="single">1 link YouTube</option><option value="multi">Nhiều link YouTube</option></select>

            {form.source_mode === 'single' ? <div className="mt-4"><label className="label">Link YouTube</label><input className="input" value={form.youtube_url} onChange={e => updateForm('youtube_url', e.target.value)} placeholder="https://www.youtube.com/watch?v=..."/></div> : <div className="mt-4"><label className="label">Danh sách link YouTube, mỗi dòng một link</label><textarea className="textarea min-h-[130px]" value={form.youtube_urls_text} onChange={e => { updateForm('youtube_urls_text', e.target.value); const first = parseYoutubeUrls(e.target.value)[0] ?? ''; updateForm('youtube_url', first); }} placeholder={'https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...'}/></div>}

            <div className="mt-4"><label className="label">Hướng dẫn thêm cho Gemini (không bắt buộc)</label>
              <p className="mt-1 text-xs text-slate-400">Gợi ý: độ dài mong muốn (vd: 60-90s, 3-5 phút), giọng kể (vd: hài hước/kịch tính/phóng sự/cảm xúc), đối tượng mục tiêu (vd: giới trẻ/người mới/chuyên gia).</p>
              <textarea className="textarea min-h-[80px]" value={form.user_instruction} onChange={e => updateForm('user_instruction', e.target.value)} placeholder="Ví dụ: Video 90 giây, giọng kể kịch tính, đối tượng là người mới bắt đầu."/></div>
            <div className="mt-4"><label className="label">Ngôn ngữ output</label>

              <select className="select-ghost" value={form.target_language} onChange={e => updateTargetLanguage(e.target.value)}>{targetLanguageOptions.map(v => <option key={v} value={v}>{v}</option>)}</select></div>

            <div className="mt-4 flex flex-wrap items-center gap-2">

                <button className="btn-secondary" onClick={handleOpenGeminiBrowser} disabled={isOpeningBrowser || geminiSessionStatus?.browser_open === true}>

                  <ExternalLink size={18}/>{isOpeningBrowser ? 'Đang mở...' : geminiSessionStatus?.browser_open ? 'Gemini đang mở' : geminiSessionStatus?.has_auth_cookies && geminiSessionStatus?.needs_login === false ? 'Mở Gemini để xác minh' : 'Mở trình duyệt Gemini'}

                </button>

                {(() => {

                  const s = geminiSessionStatus;

                  let label: string;

                  let dot: string;

                  let bg: string;

                  let textColor: string;

                  if (s?.browser_open && !s?.live_checked) {

                    label = 'Đang kiểm tra';

                    dot = 'bg-sky-500'; bg = 'bg-sky-100'; textColor = 'text-sky-800';

                  } else if (s?.live_checked && s?.exists && !s?.needs_login) {

                    label = 'Đã đăng nhập';

                    dot = 'bg-green-500'; bg = 'bg-green-100'; textColor = 'text-green-800';

                  } else if (s?.has_auth_cookies && s?.needs_login === false && !s?.browser_open) {

                    label = 'Có session đã lưu';

                    dot = 'bg-amber-500'; bg = 'bg-amber-100'; textColor = 'text-amber-800';

                  } else if (s?.live_checked && s?.needs_login) {

                    label = 'Session hết hạn';

                    dot = 'bg-red-500'; bg = 'bg-red-100'; textColor = 'text-red-800';

                  } else if (s?.session_file_exists && !s?.has_auth_cookies) {

                    label = 'Session lỗi';

                    dot = 'bg-red-500'; bg = 'bg-red-100'; textColor = 'text-red-800';

                  } else {

                    label = 'Chưa login';

                    dot = 'bg-gray-400'; bg = 'bg-gray-100'; textColor = 'text-gray-500';

}

function LicenseGate({ licenseStatus, onActivate, onRefresh }: { licenseStatus: LicenseStatus; onActivate: (licenseKey: string) => void; onRefresh: () => void }) {
  const [licenseKey, setLicenseKey] = useState('');
  const copyHardwareId = async () => {
    if (!licenseStatus?.hardware_id) return;
    await navigator.clipboard.writeText(licenseStatus.hardware_id);
    toast.success('Đã copy Hardware ID.');
  };
  return <div className="flex min-h-screen items-center justify-center p-4">
    <div className="w-full max-w-md rounded-2xl border border-cyan-500/20 bg-slate-900/80 p-8 shadow-2xl backdrop-blur">
      <div className="mb-6 text-center">
        <Sparkles size={36} className="mx-auto text-cyan-400"/>
        <h1 className="mt-4 text-2xl font-black">MrTris_AUTO</h1>
        <p className="mt-1 text-sm text-slate-400">AI Video Rewriter & Video Rebuilder</p>
      </div>
      <div className="mb-6 rounded-xl border border-yellow-500/20 bg-yellow-500/10 p-4 text-center text-sm font-medium text-yellow-200">
        {licenseStatus.message}
      </div>
      <div className="mb-4 flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
        <span className="text-slate-400">Hardware ID:</span>
        <b className="flex-1 tracking-widest text-cyan-100">{licenseStatus.hardware_id}</b>
        <button className="btn-mini" onClick={copyHardwareId}><Copy size={14}/>Sao chép</button>
      </div>
      <div className="space-y-3">
        <label className="label">Nhập license key</label>
        <textarea className="textarea min-h-[80px]" placeholder="Nhập license key, ví dụ TESTADMIN1" value={licenseKey} onChange={e => setLicenseKey(e.target.value)}/>
        <div className="flex gap-2">
          <button className="btn-primary flex-1" onClick={() => onActivate(licenseKey)} disabled={!licenseKey.trim()}>Kích hoạt</button>
          <button className="btn-secondary" onClick={onRefresh}>Làm mới</button>
        </div>
      </div>
    </div>
  </div>;
}



                  const title = s?.message || s?.path || 'Chưa có session';

                  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${bg} ${textColor}`} title={title}>

                    <span className={`h-1.5 w-1.5 rounded-full ${dot}`}/>

                    {label}

                  </span>;

                })()}

                <div className="flex items-center gap-2 text-xs text-slate-300">
                  <span>Model</span>
                  <select className="select-ghost h-8 py-1 text-xs" value={geminiModel} onChange={e => setGeminiModel(e.target.value)} disabled={isAutoPipelineRunning || !geminiModelOptions.length}>
                    {geminiModelOptions.map(m => (
                      <option key={m.key} value={m.key}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-300">
                  <span>Thinking</span>
                  <select className="select-ghost h-8 py-1 text-xs" value={geminiThinkingMode} onChange={e => setGeminiThinkingMode(e.target.value as GeminiThinkingMode)} disabled={isAutoPipelineRunning}>
                    <option value="extended">Mở rộng / Extended</option>
                    <option value="standard">Tiêu chuẩn / Standard</option>
                  </select>
                </div>

                <button className="btn-primary" style={{ background: 'linear-gradient(135deg, #7c3aed, #a855f7)' }} onClick={handleAutoPipeline} disabled={isAutoPipelineRunning}>

                  <ExternalLink size={18}/>Bắt đầu remake

                </button>

              </div>

            {autoPipelineProgress && (

              <AutoPipelineProgress progress={autoPipelineProgress} onCancel={handleCancelAutoPipeline} />

            )}

            {batchProgress && (

              <BatchPipelineProgress progress={batchProgress} onCancel={handleCancelBatchPipeline} />

            )}

            {autoRenderStatus && ['queued', 'running'].includes(autoRenderStatus.status) && autoPipelineProgress && (

              <button className="btn-mini danger w-full" onClick={handleCancelAutoPipeline}>

                Hủy xử lý tự động

              </button>

            )}

          </Card>



        </div>



        <div className="space-y-6">

          <RenderPanel canRender={canRender} isRendering={isRendering} steps={renderSteps} status={renderStatus} cookiesFile={form.ytdlp_cookies_file} subtitleMode={subtitleMode} renderOptions={renderOptions} renderDoneBell={renderDoneBell} jsonPayload={jsonPayload} finalVideosPath={finalVideosPath} onRenderDoneBellChange={setRenderDoneBell} onSubtitleModeChange={setSubtitleMode} onRenderOptionsChange={setRenderOptions} onCookieUpload={handleCookieUpload} onClearCookies={handleClearCookies} onRender={handleRender} onOpenBlurReview={() => setActiveTab('blur')} onOpenTitleTool={() => setActiveTab('title')} onOpenTtsPanel={() => setActiveTab('tts')} onSkipBlurReview={handleSkipBlurReview}/>

        </div>

      </div> : activeTab === 'blur' ? <div className="mx-auto max-w-7xl"><BlurTool reviewJob={renderStatus?.status === 'waiting_blur' ? renderStatus : null} onAfterReviewDecision={async () => { if (renderStatus?.job_id) setRenderStatus(await fetchRenderJob(renderStatus.job_id)); }}/></div> : activeTab === 'title' ? <div className="mx-auto max-w-7xl"><TitleTool renderOptions={renderOptions} jsonPayload={jsonPayload} onRenderOptionsChange={setRenderOptions}/></div> : activeTab === 'tts' ? <div className="mx-auto max-w-5xl"><TtsPanel renderOptions={renderOptions} onRenderOptionsChange={setRenderOptions}/></div> : activeTab === 'tts-studio' ? <div className="mx-auto max-w-5xl"><TtsStudioPanel /></div> : <div className="mx-auto max-w-5xl"><MaintenancePanel stats={storageStats} licenseStatus={licenseStatus} initialUpdateData={updateAvailable} onRefresh={() => { void loadStorageStats(); void loadLicenseStatus(); }} onCleanup={runFullCleanup} onActivateLicense={activateLicenseFromUi} onClearLicense={clearLicenseFromUi} onUnbindLicense={unbindLicenseFromUi}/></div>}
    </main>

  </div>;

}


function RenderPanel({ canRender, isRendering, steps, status, cookiesFile, subtitleMode, renderOptions, renderDoneBell, jsonPayload, finalVideosPath, onRenderDoneBellChange, onSubtitleModeChange, onRenderOptionsChange, onCookieUpload, onClearCookies, onRender, onOpenBlurReview, onOpenTitleTool, onOpenTtsPanel, onSkipBlurReview }: { canRender: boolean; isRendering: boolean; steps: StepState[]; status: RenderJobStatus | null; cookiesFile: string; subtitleMode: SubtitleMode; renderOptions: RenderOptions; renderDoneBell: boolean; jsonPayload: GeminiEdlPayload | null; finalVideosPath: string | null; onRenderDoneBellChange: (value: boolean) => void; onSubtitleModeChange: (value: SubtitleMode) => void; onRenderOptionsChange: (value: RenderOptions) => void; onCookieUpload: (file: File) => void; onClearCookies: () => void; onRender: () => void; onOpenBlurReview: () => void; onOpenTitleTool: () => void; onOpenTtsPanel: () => void; onSkipBlurReview: (jobId: string) => void }) {

  const cookieInputRef = useRef<HTMLInputElement>(null);

  const [ttsStatus, setTtsStatus] = useState<{ status: string; message: string } | null>(null);

  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);



  useEffect(() => { void fetchTtsStatus().then(setTtsStatus).catch(() => setTtsStatus({ status: 'error', message: 'Không kiểm tra được trạng thái TTS.' })); void fetchTtsVoices().then(data => setTtsVoices(data.voices)).catch(() => setTtsVoices([])); }, []);

  const updateOptions = (patch: Partial<RenderOptions>) => onRenderOptionsChange({ ...renderOptions, ...patch });

  return <Card><SectionTitle icon={Film} title="2. Dựng video" desc="Dựng video và theo dõi tiến trình"/>

    <ProgressBar status={status}/>

    <div className="mt-4 space-y-3">{renderStepLabels.map((label, index) => <div className="step" key={label}><span className={`dot ${steps[index]}`}/><div><b>{label}</b><p>{steps[index] === 'idle' ? 'Chưa thực hiện' : steps[index] === 'running' ? 'Đang xử lý' : steps[index] === 'done' ? 'Hoàn thành' : 'Lỗi'}</p></div></div>)}</div>

    <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">

      <h3 className="mb-3 font-bold">Tùy chọn dựng video</h3>

      <div className="grid gap-3">

        <div><label className="label">Phụ đề</label><select className="select-ghost" value={subtitleMode} onChange={e => onSubtitleModeChange(e.target.value as SubtitleMode)}><option value="burn">Xuất video có phụ đề + file SRT</option><option value="none">Xuất video + file SRT, không gắn phụ đề</option><option value="srt_only">Chỉ xuất file SRT</option></select></div>

        <div><label className="label">Làm mờ</label><select className="select-ghost" value={renderOptions.blur_mode} onChange={e => updateOptions({ blur_mode: e.target.value as RenderOptions['blur_mode'] })}><option value="none">Không làm mờ, dựng video luôn</option><option value="review">Dừng để chọn vùng cần làm mờ trước khi xuất video</option></select></div>

        <TitleOverlayOptions renderOptions={renderOptions} jsonPayload={jsonPayload} onChange={updateOptions} onOpenTitleTool={onOpenTitleTool}/>

        <SubtitleStyleSelector renderOptions={renderOptions} onChange={updateOptions}/>

        <SubtitleGallery renderOptions={renderOptions} onChange={updateOptions}/>

        <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="font-bold">Giọng đọc / TTS</h4>{ttsStatus && <Pill tone={ttsStatus.status === 'ready' ? 'green' : 'yellow'}>{ttsStatus.status === 'ready' ? 'Sẵn sàng' : 'TTS chưa cài'}</Pill>}</div>{ttsStatus && <p className="mb-3 text-xs text-slate-400">{ttsStatus.message}</p>}<div className="grid gap-3"><div><label className="label">Giọng đọc tự động</label><select className="select-ghost" value={renderOptions.tts_mode} onChange={e => updateOptions({ tts_mode: e.target.value as RenderOptions['tts_mode'] })}><option value="none">Tắt TTS</option><option value="voiceover">Bật giọng đọc theo phụ đề</option></select></div>{renderOptions.tts_mode === 'voiceover' && <button className="btn-secondary w-full" onClick={onOpenTtsPanel}>Mở phần Giọng đọc để tùy chỉnh</button>}</div></div>
        <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm"><input type="checkbox" checked={renderDoneBell} onChange={e => onRenderDoneBellChange(e.target.checked)}/>Bật âm báo khi dựng xong</label>

        <div><label className="label">File xuất ra</label><select className="select-ghost" value={renderOptions.artifact_retention} onChange={e => updateOptions({ artifact_retention: e.target.value as RenderOptions['artifact_retention'] })}><option value="smart">Tự động dọn - giữ file cần thiết, xóa video tạm lớn</option><option value="keep_all">Giữ tất cả file - dùng khi cần kiểm tra lỗi</option></select></div>

        <div><label className="label">Độ ổn định</label><select className="select-ghost" value={renderOptions.render_stability} onChange={e => updateOptions({ render_stability: e.target.value as RenderOptions['render_stability'] })}><option value="fast">Nhanh - thời gian xử lý ngắn hơn</option><option value="stable">Ổn định - khuyến nghị</option><option value="max_quality">Chất lượng cao nhất</option></select></div>

        <div><label className="label">Tăng tốc phần cứng</label><select className="select-ghost" value={renderOptions.video_encoder} onChange={e => updateOptions({ video_encoder: e.target.value as RenderOptions['video_encoder'] })}><option value="auto">Tự động - ưu tiên GPU</option><option value="cpu">Chỉ dùng CPU</option><option value="nvenc">NVIDIA NVENC</option><option value="qsv">Intel Quick Sync</option><option value="amf">AMD AMF</option></select></div>

        <div><label className="label">FPS đoạn video</label><select className="select-ghost" value={renderOptions.segment_fps} onChange={e => updateOptions({ segment_fps: e.target.value as RenderOptions['segment_fps'] })}><option value="auto">Tự động</option><option value="30">30fps</option><option value="60">60fps - thể thao / highlight</option></select></div>

        <div><label className="label">Tỉ lệ đầu ra</label><select className="select-ghost" value={renderOptions.vertical_mode} onChange={e => updateOptions({ vertical_mode: e.target.value as VerticalMode })}><option value="none">Giữ nguyên ngang</option><option value="blur_fit">Dọc 9:16 - Nền mờ + video vuông 1:1</option><option value="center_crop">Dọc 9:16 - Cắt giữa</option></select></div>

        <div className="grid gap-3 md:grid-cols-2">

          <div><label className="label">Chất lượng render</label><select className="select-ghost" value={renderOptions.render_quality} onChange={e => updateOptions({ render_quality: e.target.value as RenderQuality })}><option value="fast">Nhanh - file nhỏ</option><option value="balanced">Cân bằng - mặc định</option><option value="high">Cao - chất lượng tốt hơn</option></select></div>

          <div><label className="label">Độ phân giải</label><select className="select-ghost" value={renderOptions.output_resolution} onChange={e => updateOptions({ output_resolution: e.target.value as OutputResolution })}><option value="auto">Tự động / gốc</option><option value="720p">720p</option><option value="1080p">1080p</option></select></div>

        </div>

        <div><label className="label">Tốc độ video</label><select className="select-ghost" value={renderOptions.video_speed} onChange={e => updateOptions({ video_speed: Number(e.target.value) })}><option value={1.0}>1.0x — Bình thường</option><option value={1.1}>1.1x — Hơi nhanh</option><option value={1.2}>1.2x — Nhanh hơn</option><option value={1.3}>1.3x — Nhanh</option><option value={1.5}>1.5x — Rất nhanh</option></select><p className="mt-1 text-xs text-slate-400">Tăng tốc video cuối, giữ nguyên cao độ giọng. Áp dụng sau khi gắn phụ đề.</p></div>

      </div>

    </div>

    <div className="mt-4 rounded-2xl border border-yellow-500/20 bg-yellow-500/10 p-4"><h3 className="mb-2 font-bold">Cookies YouTube cho yt-dlp</h3><p className="mb-3 text-xs text-slate-400">Dùng khi YouTube yêu cầu xác minh đăng nhập.</p><input ref={cookieInputRef} type="file" accept=".txt,text/plain" hidden onChange={e => { const file = e.target.files?.[0]; if (file) onCookieUpload(file); e.currentTarget.value = ''; }}/><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => cookieInputRef.current?.click()}><Upload size={16}/>Chọn cookies.txt</button>{cookiesFile && <button className="btn-secondary" onClick={onClearCookies}>Xóa cookies</button>}</div>{cookiesFile && <p className="mt-2 break-all text-xs text-emerald-300">Đã upload: {cookiesFile}</p>}</div>

    {!canRender && <p className="mt-3 text-xs text-yellow-300">Cần JSON đã validate hợp lệ. Nếu dựng video, cần thêm YouTube URL hoặc JSON có sources[].</p>}

    <button className="btn-primary mt-4 w-full" disabled={!canRender} onClick={onRender}>{isRendering ? <Loader2 className="animate-spin" size={18}/> : <Play size={18}/>} {subtitleMode === 'srt_only' ? 'Xuất SRT' : 'Dựng video'}</button>

    {status?.status === 'waiting_blur' && <BlurReviewEntry status={status} onOpen={onOpenBlurReview} onSkip={onSkipBlurReview}/>} 

    {status?.result && status.status !== 'waiting_blur' && <RenderResultPanel finalVideosPath={finalVideosPath}/>} 

  </Card>;

}



function TitleOverlayOptions({ renderOptions, jsonPayload, onChange, onOpenTitleTool }: { renderOptions: RenderOptions; jsonPayload: GeminiEdlPayload | null; onChange: (patch: Partial<RenderOptions>) => void; onOpenTitleTool: () => void }) {

  const rawTitle = renderOptions.title_mode === 'custom' ? renderOptions.title_text : jsonPayload?.metadata.video_title || 'Xem trước tiêu đề từ dữ liệu video';

  const maxLines = Math.max(1, Math.min(3, Number(renderOptions.title_max_lines) || 2));

  const charsPerLine = Math.max(16, Math.min(60, Number(renderOptions.title_chars_per_line) || 34));

  const ratio = renderOptions.vertical_mode === 'none' ? '16:9' : '9:16';

  const titleStyleLabels: Record<string, string> = { breaking_yellow: 'Tin nóng + vàng', yellow_highlight: 'Nền vàng nổi bật', dark_badge: 'Nền tối', clean_white: 'Chữ trắng đơn giản' };
  const titleAlignLabels: Record<string, string> = { left: 'Trái', center: 'Giữa', right: 'Phải' };
  const titleBadgeLabels: Record<string, string> = { none: 'Không dùng', auto: 'Tự động', custom: 'Tùy chỉnh' };
  const titleFontLabels: Record<string, string> = { auto: 'Tự động', small: 'Nhỏ', medium: 'Vừa', large: 'Lớn' };
  const titlePosLabels: Record<string, string> = { top: 'Trên', upper_third: '1/3 phía trên', center: 'Giữa', bottom: 'Dưới' };

  return <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">

    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="font-bold">Tiêu đề tự động</h4><Pill tone={renderOptions.title_mode === 'none' ? 'yellow' : 'green'}>{renderOptions.title_mode === 'none' ? 'Tắt' : `${ratio}`}</Pill></div>

    <div className="grid gap-3">

      <div><label className="label">Tiêu đề</label><select className="select-ghost" value={renderOptions.title_mode} onChange={e => onChange({ title_mode: e.target.value as RenderOptions['title_mode'] })}><option value="auto">Tự động từ dữ liệu video</option><option value="custom">Tiêu đề tùy chỉnh</option><option value="none">Tắt</option></select></div>

      <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3 text-xs text-slate-400">

        <p className="line-clamp-2 text-slate-300">{renderOptions.title_mode === 'none' ? 'Lớp phủ tiêu đề đang tắt.' : rawTitle}</p>

        <p className="mt-2">Kiểu: {titleStyleLabels[renderOptions.title_style] ?? renderOptions.title_style} · Canh: {titleAlignLabels[renderOptions.title_text_align] ?? renderOptions.title_text_align} · Huy hiệu: {titleBadgeLabels[renderOptions.title_badge_mode] ?? renderOptions.title_badge_mode} · {renderOptions.title_show_duration === 'full' ? 'Toàn video' : `${renderOptions.title_intro_seconds}s đầu`}</p>

        <p className="mt-1">Cỡ chữ: {titleFontLabels[renderOptions.title_font_size] ?? renderOptions.title_font_size} · {maxLines} dòng · {charsPerLine} ký tự/dòng · Vị trí: {titlePosLabels[renderOptions.title_position] ?? renderOptions.title_position}</p>

      </div>

      <button className="btn-secondary w-full" onClick={onOpenTitleTool}>Mở phần Tiêu đề để xem trước đúng tỉ lệ</button>

    </div>

  </div>;

}





function BlurReviewEntry({ status, onOpen, onSkip }: { status: RenderJobStatus; onOpen: () => void; onSkip: (jobId: string) => void }) {

  return <div className="mt-4 rounded-2xl border border-yellow-500/30 bg-yellow-500/10 p-4"><div className="flex items-start gap-3"><Bell size={20} className="mt-0.5 flex-shrink-0 text-yellow-400"/><div className="min-w-0 flex-1"><h3 className="font-bold text-yellow-100">Đang chờ chọn vùng làm mờ</h3><p className="mt-1 text-sm text-slate-300">Video xem trước đã được tạo đúng tỉ lệ.</p><p className="mt-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2 text-sm font-medium text-yellow-200"><Bell size={14} className="-mt-0.5 mr-1 inline"/>Mở trình chỉnh làm mờ để chọn vùng chính xác hơn, hoặc bỏ qua nếu không cần.</p><div className="mt-4 flex flex-wrap gap-2"><button className="btn-primary" onClick={onOpen}>Mở trình chỉnh làm mờ</button><button className="btn-secondary" onClick={() => onSkip(status.job_id)}>Không làm mờ, tiếp tục xuất video</button></div></div></div></div>;

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



  return <div className="mt-4 rounded-2xl border border-yellow-500/30 bg-yellow-500/10 p-4"><h3 className="mb-2 font-bold text-yellow-100">Chọn vùng làm mờ</h3><p className="mb-4 text-sm text-slate-300">Video đã được cắt/ghép/chuyển tỉ lệ. Hãy chọn vùng cần làm mờ trước khi gắn phụ đề hoặc xuất video.</p>{previewPath && <div className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]"><BlurRegionEditor videoUrl={blurPreviewUrl(previewPath)} regions={regions} selected={selected} locked={new Set()} onChange={setRegions} onSelect={(id) => setSelected(id !== null ? new Set([id]) : new Set())} onToggleLock={() => {}} onCurrentTimeChange={setCurrentTime}/><BlurRegionSidebar regions={regions} selected={selected} locked={new Set()} onChange={setRegions} onSelect={(id) => setSelected(id !== null ? new Set([id]) : new Set())} onToggleLock={() => {}} currentTime={currentTime}/></div>}<div className="mt-4 flex flex-wrap gap-2"><button className="btn-secondary" disabled={submitting} onClick={skip}>Không làm mờ, tiếp tục xuất video</button><button className="btn-primary" disabled={submitting || !regions.length} onClick={apply}>Áp dụng làm mờ và tiếp tục</button></div></div>;

}



function RenderResultPanel({ finalVideosPath }: { finalVideosPath: string | null }) {


  const openFolder = async () => {


    if (!finalVideosPath) { toast.error('Không tìm thấy thư mục video đã xuất.'); return; }


    try { await openOutputFolder(finalVideosPath); toast.success('Đã mở thư mục video'); } catch (e) { toast.error(e instanceof Error ? e.message : 'Không mở được thư mục'); }


  };


  return <button className="btn-primary mt-4 w-full" onClick={openFolder}><FolderOpen size={18}/> Mở danh sách video đã edit</button>;


}

function MaintenancePanel({ stats, licenseStatus, initialUpdateData, onRefresh, onCleanup, onActivateLicense, onClearLicense, onUnbindLicense }: { stats: StorageStats | null; licenseStatus: LicenseStatus | null; initialUpdateData: UpdateCheckResponse | null; onRefresh: () => void; onCleanup: () => void; onActivateLicense: (licenseKey: string) => void; onClearLicense: () => void; onUnbindLicense: () => void }) {
  const [licenseKey, setLicenseKey] = useState('');

  const [updateState, setUpdateState] = useState<'idle' | 'checking' | 'up_to_date' | 'available' | 'error'>('idle');

  const [updateData, setUpdateData] = useState<UpdateCheckResponse | null>(null);

  const [updateError, setUpdateError] = useState('');

  const [launched, setLaunched] = useState(false);

  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false);

  useEffect(() => {
    if (initialUpdateData && updateState === 'idle') {
      setUpdateData(initialUpdateData);
      setUpdateState('available');
    }
  }, [initialUpdateData, updateState]);

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


  return <Card><SectionTitle icon={Trash2} title="Bảo trì" desc="Theo dõi dung lượng và dọn dẹp project"/>

    <div className="mb-5 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 font-bold"><KeyRound size={18}/>License</h3><button className="btn-mini" onClick={onRefresh}>Làm mới</button></div>

      <div className="grid gap-3 md:grid-cols-4"><Stat label="Trạng thái" value={licenseStatus?.status ?? 'N/A'}/><Stat label="Gói" value={licenseStatus?.plan ?? 'N/A'}/><Stat label="Áp dụng" value={licenseStatus?.enforcement ? 'ON' : 'OFF'}/><Stat label="Hết hạn" value={licenseStatus?.expires_at ? new Date(licenseStatus.expires_at).toLocaleString() : licenseStatus?.plan === 'lifetime' ? 'Vĩnh viễn' : 'N/A'}/></div>

      <p className="mt-3 text-sm text-slate-200">{licenseStatus?.message ?? 'Chưa tải trạng thái license.'}</p>
      {licenseStatus?.cache_status === 'offline' && <p className="mt-2 text-sm text-amber-300">Đang dùng cache license offline. Hãy kết nối mạng trong vòng 2 ngày để xác thực lại.</p>}

      {licenseStatus?.customer_name && <p className="mt-2 text-xs text-slate-400">Khách hàng: {licenseStatus.customer_name} {licenseStatus.customer_email ? `(${licenseStatus.customer_email})` : ''}</p>}

      <div className="mt-4 grid gap-3"><label className="label">Nhập license key</label><textarea className="textarea min-h-[96px]" placeholder="Nhập license key, ví dụ TESTADMIN1" value={licenseKey} onChange={e => setLicenseKey(e.target.value)}/><div className="flex flex-wrap gap-2"><button className="btn-primary" onClick={() => onActivateLicense(licenseKey)} disabled={!licenseKey.trim()}>Kích hoạt</button><button className="btn-secondary" onClick={() => setLicenseKey('')}>Xóa nội dung</button><button className="btn-secondary" disabled={!licenseStatus?.licensed} onClick={onUnbindLicense}>Gỡ liên kết thiết bị</button><button className="btn-secondary" onClick={() => { if (confirm('Xóa license trên máy này?')) onClearLicense(); }}>Xóa license trên máy</button></div></div>
    </div>

    <div className="mb-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4">

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 font-bold"><Download size={18}/>Phiên bản & Cập nhật</h3><button className="btn-mini" onClick={handleCheckUpdate} disabled={updateState === 'checking'}>{updateState === 'checking' ? 'Đang kiểm tra...' : 'Kiểm tra cập nhật'}</button></div>

      {updateState === 'checking' && <p className="text-sm text-slate-300">Đang kiểm tra...</p>}

      {updateState === 'idle' && <p className="text-sm text-slate-400">Nhấn "Kiểm tra cập nhật" để kiểm tra phiên bản mới.</p>}

      {updateState === 'up_to_date' && <div><div className="grid gap-3 md:grid-cols-2"><Stat label="Phiên bản hiện tại" value={updateData?.local_version ?? 'N/A'}/><Stat label="Kênh" value={updateData?.channel ?? 'N/A'}/></div><p className="mt-2 text-sm text-green-400">{updateData?.message}</p></div>}

      {updateState === 'available' && <div><div className="grid gap-3 md:grid-cols-2"><Stat label="Phiên bản hiện tại" value={updateData?.local_version ?? 'N/A'}/><Stat label="Phiên bản mới nhất" value={updateData?.remote_version ?? 'N/A'}/></div><p className="mt-2 text-sm text-amber-400">{updateData?.message}</p>{updateData && updateData.notes && updateData.notes.length > 0 && <div className="mt-2 max-h-24 overflow-auto rounded-xl border border-white/10 bg-slate-950/60 p-2 text-xs text-slate-300">{updateData.notes.map((note: string, i: number) => <p key={i} className="mb-1">• {note}</p>)}</div>}<div className="mt-3 flex flex-wrap items-center gap-2"><button className="btn-primary" onClick={() => setShowUpdateConfirm(true)} disabled={launched}>{launched ? 'Đã mở' : 'Mở trình cập nhật'}</button>{launched && <span className="text-xs text-slate-300">Trình cập nhật đã mở. Ứng dụng sẽ tự đóng, cập nhật và khởi động lại.</span>}</div>{showUpdateConfirm && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowUpdateConfirm(false)}><div className="mx-4 w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl" onClick={e => e.stopPropagation()}><h3 className="mb-3 text-lg font-bold">Cập nhật và khởi động lại?</h3><p className="mb-6 text-sm text-slate-300">MrTris_AUTO sẽ tự đóng, cập nhật lên bản mới nhất, rồi khởi động lại. Hãy lưu công việc đang làm trước khi tiếp tục.</p><div className="flex justify-end gap-3"><button className="btn-secondary" onClick={() => setShowUpdateConfirm(false)}>Hủy</button><button className="btn-primary" onClick={handleLaunchUpdater}>Cập nhật ngay</button></div></div></div>}</div>}

      {updateState === 'error' && <p className="text-sm text-red-400">Kiểm tra thất bại: {updateError}</p>}

    </div>

    <div className="grid gap-3 md:grid-cols-4"><Stat label="Video đầu ra" value={fmtBytes(stats?.outputs_size_bytes)}/><Stat label="Tạm thời" value={fmtBytes(stats?.temp_size_bytes)}/><Stat label="Số file đầu ra" value={`${stats?.outputs_count ?? 0}`}/><Stat label="Số file tạm" value={`${stats?.temp_count ?? 0}`}/></div>

    <div className="mt-5"><button className="btn-primary w-full justify-center py-3 text-base" onClick={() => { if (confirm('Dọn dẹp tất cả dữ liệu tạm và video đầu ra cũ? Video cuối cùng sẽ được giữ nguyên.')) onCleanup(); }}><Trash2 size={18}/> Dọn dẹp</button></div>

  </Card>;

}






function LicenseGate({ licenseStatus, onActivate, onRefresh }: { licenseStatus: LicenseStatus; onActivate: (licenseKey: string) => void; onRefresh: () => void }) {
  const [licenseKey, setLicenseKey] = useState('');
  const copyHardwareId = async () => {
    if (!licenseStatus?.hardware_id) return;
    await navigator.clipboard.writeText(licenseStatus.hardware_id);
    toast.success('Đã copy Hardware ID.');
  };
  return <div className="flex min-h-screen items-center justify-center p-4">
    <div className="w-full max-w-md rounded-2xl border border-cyan-500/20 bg-slate-900/80 p-8 shadow-2xl backdrop-blur">
      <div className="mb-6 text-center">
        <Sparkles size={36} className="mx-auto text-cyan-400"/>
        <h1 className="mt-4 text-2xl font-black">MrTris_AUTO</h1>
        <p className="mt-1 text-sm text-slate-400">AI Video Rewriter & Video Rebuilder</p>
      </div>
      <div className="mb-6 rounded-xl border border-yellow-500/20 bg-yellow-500/10 p-4 text-center text-sm font-medium text-yellow-200">
        {licenseStatus.message}
      </div>
      <div className="mb-4 flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
        <span className="text-slate-400">Hardware ID:</span>
        <b className="flex-1 tracking-widest text-cyan-100">{licenseStatus.hardware_id}</b>
        <button className="btn-mini" onClick={copyHardwareId}><Copy size={14}/>Sao chép</button>
      </div>
      <div className="space-y-3">
        <label className="label">Nhập license key</label>
        <textarea className="textarea min-h-[80px]" placeholder="Nhập license key, ví dụ TESTADMIN1" value={licenseKey} onChange={e => setLicenseKey(e.target.value)}/>
        <div className="flex gap-2">
          <button className="btn-primary flex-1" onClick={() => onActivate(licenseKey)} disabled={!licenseKey.trim()}>Kích hoạt</button>
          <button className="btn-secondary" onClick={onRefresh}>Làm mới</button>
        </div>
      </div>
    </div>
  </div>;
}
