import { CheckCircle2, Loader2, XCircle, ExternalLink, LogIn } from 'lucide-react';
import type { AutoPipelineProgress } from '../types';

const STEP_LABELS: Record<string, { label: string; desc: string }> = {
  init: { label: 'Khởi tạo', desc: 'Đang chuẩn bị' },
  init_browser: { label: 'Khởi tạo Chromium', desc: 'Đang mở trình duyệt...' },
  navigate_gemini: { label: 'Truy cập Gemini', desc: 'Đang mở gemini.google.com...' },
  wait_login: { label: 'Đăng nhập Gemini', desc: 'Vui lòng đăng nhập...' },
  submitting_prompt: { label: 'Gửi prompt', desc: 'Đang gửi prompt đến Gemini...' },
  waiting_response: { label: 'Gemini trả lời', desc: 'Gemini đang xử lý prompt...' },
  extracting_json: { label: 'Trích xuất dữ liệu', desc: 'Đang lấy JSON từ Gemini...' },
  validating: { label: 'Kiểm tra dữ liệu', desc: 'Đang kiểm tra JSON...' },
  auto_retry: { label: 'Thử lại', desc: 'JSON chưa hợp lệ, đang thử lại...' },
  submitting_render: { label: 'Tạo video', desc: 'Đang gửi render job...' },
  complete: { label: 'Hoàn tất', desc: 'Pipeline hoàn thành!' },
  error: { label: 'Lỗi', desc: 'Pipeline thất bại' },
  cancelling: { label: 'Đang hủy', desc: 'Đang hủy pipeline...' },
};

function StepIcon({ step, status }: { step: string; status: string }) {
  if (status === 'done') return <CheckCircle2 size={20} className="text-emerald-400" />;
  if (status === 'error') return <XCircle size={20} className="text-red-400" />;
  if (step === 'wait_login') return <LogIn size={20} className="text-amber-400" />;
  if (status === 'running') return <Loader2 size={20} className="animate-spin text-cyan-400" />;
  return <div className="h-5 w-5 rounded-full border-2 border-slate-600" />;
}

export function AutoPipelineProgress({
  progress,
  onCancel,
}: {
  progress: AutoPipelineProgress | null;
  onCancel: () => void;
}) {
  if (!progress) return null;

  const allStates = progress.states ?? [];
  const status = progress.status;

  return (
    <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-bold text-violet-200">
          <ExternalLink size={18} />
          Auto Pipeline
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
        {allStates.map((state, idx) => {
          const info = STEP_LABELS[state.step] ?? { label: state.label, desc: '' };
          return (
            <div
              key={`${state.step}-${idx}`}
              className={`flex items-center gap-3 rounded-xl p-3 transition-colors ${
                state.status === 'running' ? 'border border-violet-400/30 bg-violet-500/10' : ''
              }`}
            >
              <StepIcon step={state.step} status={state.status} />
              <div className="min-w-0 flex-1">
                <p className={`text-sm font-semibold ${
                  state.status === 'error' ? 'text-red-300'
                  : state.status === 'running' ? 'text-violet-200'
                  : 'text-slate-300'
                }`}>
                  {info.label}
                </p>
                <p className="text-xs text-slate-400">
                  {state.status === 'running' ? progress.message ?? info.desc
                   : state.status === 'done' ? 'Hoàn thành'
                   : state.status === 'error' ? progress.error ?? info.desc
                   : info.desc}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {!!((progress.detail as Record<string, unknown>)?.login_required) && (
        <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-sm">
          <p className="flex items-center gap-2 font-medium text-amber-200">
            <LogIn size={16} />
            Vui lòng đăng nhập Gemini
          </p>
          <p className="mt-1 text-xs text-amber-100/70">
            Trình duyệt Chromium đã được mở. Vui lòng đăng nhập vào tài khoản Google của bạn trên trình duyệt đó.
            Sau khi đăng nhập xong, pipeline sẽ tự động tiếp tục.
          </p>
        </div>
      )}
    </div>
  );
}
