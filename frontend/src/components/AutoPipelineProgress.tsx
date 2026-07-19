import { CheckCircle2, Loader2, XCircle, ExternalLink, LogIn, FolderOpen } from 'lucide-react';
import { toast } from 'sonner';
import type { AutoPipelineProgress } from '../types';
import { fetchFinalVideosPath, openOutputFolder } from '../api';

const PASS1_STEPS = new Set([
  'init',
  'init_browser',
  'navigate_gemini',
  'checking_login',
  'wait_login',
  'analyzing_source',
  'submitting_prompt',
  'waiting_response',
  'validating_analysis',
]);

const PASS2_STEPS = new Set([
  'building_final_prompt',
  'scouting_timeline',
  'analyzing_chapter',
  'auditing_coverage',
  'planning_duration',
  'assembling_story',
  'generating_chunk',
  'merging_final',
  'auditing_alignment',
  'repairing_chunk',
  'extracting_json',
  'validating',
  'auto_retry',
  'cleanup_gemini',
  'submitting_prompt',
  'waiting_response',
]);

const PHASES = [
  { key: 'pass1' as const, label: 'Remake nội dung', sublabel: '' },
  { key: 'pass2' as const, label: 'Xử lý nội dung', sublabel: '' },
  { key: 'done' as const, label: 'Xử lý xong', sublabel: '' },
];

function sanitizeMessage(msg: string | null | undefined): string {
  if (!msg) return '';
  return msg
    .replace(/Chromium/gi, '')
    .replace(/Playwright/gi, '')
    .replace(/\bJSON\b/gi, '')
    .replace(/\bprompt\b/gi, '')
    .trim();
}

type PhaseKey = 'pass1' | 'pass2' | 'done';

function getCurrentPhaseKey(progress: AutoPipelineProgress): PhaseKey {
  const status = progress.status;
  if (status === 'done') return 'done';

  const hasPass2Started = PASS2_STEPS.has(progress.step)
    || progress.states?.some(s => PASS2_STEPS.has(s.step) && !PASS1_STEPS.has(s.step));
  if (hasPass2Started) return 'pass2';

  return 'pass1';
}

function getPhaseStatus(
  progress: AutoPipelineProgress,
  phaseKey: PhaseKey,
): 'running' | 'done' | 'error' | 'pending' {
  const currentPhaseKey = getCurrentPhaseKey(progress);
  const status = progress.status;

  if (phaseKey === 'pass1') {
    const pass1Error = progress.states?.some(s => PASS1_STEPS.has(s.step) && s.status === 'error');
    if (pass1Error && currentPhaseKey === 'pass1') return 'error';
    if (currentPhaseKey === 'pass2' || currentPhaseKey === 'done') return 'done';
    if (currentPhaseKey === 'pass1') return status === 'running' ? 'running' : 'done';
    return 'pending';
  }

  if (phaseKey === 'pass2') {
    const pass2Error = status === 'error' && currentPhaseKey === 'pass2';
    if (pass2Error) return 'error';
    if (currentPhaseKey === 'done') return 'done';
    if (currentPhaseKey === 'pass2') return status === 'running' ? 'running' : 'done';
    return 'pending';
  }

  if (phaseKey === 'done') {
    if (status === 'done') return 'done';
    if (currentPhaseKey === 'done' && status === 'running') return 'running';
    return 'pending';
  }

  return 'pending';
}

function getRunningMessage(progress: AutoPipelineProgress): string {
  const msg = sanitizeMessage(progress.message);
  if (msg) return msg;
  return 'Đang xử lý nội dung...';
}

export function AutoPipelineProgress({
  progress,
  onCancel,
}: {
  progress: AutoPipelineProgress | null;
  onCancel: () => void;
}) {
  if (!progress) return null;

  const status = progress.status;
  const result = progress.result as Record<string, string> | null;
  const currentPhaseKey = getCurrentPhaseKey(progress);

  const phases = PHASES.map(phase => ({
    ...phase,
    phaseStatus: getPhaseStatus(progress, phase.key),
  }));

  const runningMessage = getRunningMessage(progress);
  const errorMessage: string = progress.error
    ? sanitizeMessage(progress.error) || 'Có lỗi trong quá trình xử lý. Vui lòng thử lại.'
    : '';

  const detail = progress.detail;
  const loginRequired = detail && !!(detail as Record<string, unknown>).login_required;

  return (
    <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-bold text-violet-200">
          <ExternalLink size={18} />
          Xử lý tự động
        </h3>
        <div className="flex items-center gap-2">
          {status === 'running' && (
            <button className="btn-mini danger" onClick={onCancel}>
              Hủy
            </button>
          )}
          {status === 'done' && <span className="text-xs text-emerald-400">Hoàn tất</span>}
          {status === 'error' && <span className="text-xs text-red-400">Thất bại</span>}
        </div>
      </div>

      <div className="space-y-2">
        {phases.map(phase => (
          <div
            key={phase.key}
            className={`flex items-center gap-3 rounded-xl p-3 transition-colors ${
              phase.phaseStatus === 'running' ? 'border border-violet-400/30 bg-violet-500/10' : ''
            }`}
          >
            {phase.phaseStatus === 'done' ? (
              <CheckCircle2 size={20} className="text-emerald-400" />
            ) : phase.phaseStatus === 'error' ? (
              <XCircle size={20} className="text-red-400" />
            ) : phase.phaseStatus === 'running' ? (
              <Loader2 size={20} className="animate-spin text-cyan-400" />
            ) : (
              <div className="h-5 w-5 rounded-full border-2 border-slate-600" />
            )}
            <div className="min-w-0 flex-1">
              <p
                className={`text-sm font-semibold ${
                  phase.phaseStatus === 'error'
                    ? 'text-red-300'
                    : phase.phaseStatus === 'running'
                      ? 'text-violet-200'
                      : 'text-slate-300'
                }`}
              >
                {phase.label}
                {phase.sublabel && (
                  <span className="ml-2 rounded-full bg-violet-500/20 px-1.5 py-0.5 text-[10px] text-violet-300">
                    {phase.sublabel}
                  </span>
                )}
              </p>
              <p className="text-xs text-slate-400">
                {phase.phaseStatus === 'running' && phase.key === currentPhaseKey
                  ? runningMessage
                  : phase.phaseStatus === 'done'
                    ? 'Hoàn thành'
                    : phase.phaseStatus === 'error'
                      ? errorMessage
                      : ''}
              </p>
            </div>
          </div>
        ))}
      </div>

      {loginRequired && (
        <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-sm">
          <p className="flex items-center gap-2 font-medium text-amber-200">
            <LogIn size={16} />
            Cần xác minh Gemini để tiếp tục.
          </p>
          <p className="mt-1 text-xs text-amber-100/70">
            Trình duyệt đã được mở. Vui lòng đăng nhập vào tài khoản Google trên trình duyệt đó.
            Sau khi đăng nhập xong, pipeline sẽ tự động tiếp tục.
          </p>
        </div>
      )}

      {status === 'done' && (result?.output_dir || result?.final_video_path) && (
        <button
          className="btn-primary mt-4 w-full"
          onClick={async () => {
            try {
              const finalVideosPath = await fetchFinalVideosPath();
              await openOutputFolder(finalVideosPath);
              toast.success('Đã mở thư mục video');
            } catch (e) {
              toast.error(e instanceof Error ? e.message : 'Không mở được thư mục');
            }
          }}
        >
          <FolderOpen size={18} /> Mở danh sách video đã edit
        </button>
      )}
    </div>
  );
}
