import { CheckCircle2, Loader2, XCircle, Ban, ExternalLink, Clock } from 'lucide-react';
import type { BatchProgress, RenderJobStatus } from '../types';
import { AutoPipelineProgress } from './AutoPipelineProgress';

function statusLabel(status: string) {
  if (status === 'done') return 'Hoàn tất';
  if (status === 'error') return 'Lỗi';
  if (status === 'cancelled') return 'Đã hủy';
  if (status === 'running') return 'Đang chạy';
  return 'Đang chờ';
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'done') return <CheckCircle2 size={18} className="text-emerald-400" />;
  if (status === 'error') return <XCircle size={18} className="text-red-400" />;
  if (status === 'cancelled') return <Ban size={18} className="text-slate-400" />;
  if (status === 'running') return <Loader2 size={18} className="animate-spin text-cyan-400" />;
  return <div className="h-[18px] w-[18px] rounded-full border border-slate-600" />;
}

function fmtTime(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function RenderProgressPanel({ renderStatus }: { renderStatus: RenderJobStatus }) {
  const pct = renderStatus.progress ?? 0;
  return <div className="mt-3 rounded-xl border border-violet-500/20 bg-violet-500/10 p-3">
    <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-violet-200">
      <Clock size={14} /> Render Progress
    </div>
    <div className="progress-track h-2">
      <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </div>
    <p className="mt-1 text-xs text-slate-400">{renderStatus.message || renderStatus.step || ''}</p>
    <div className="mt-2 grid grid-cols-3 gap-1 text-[11px] font-medium text-slate-400">
      <span>Đã chạy: {fmtTime(renderStatus.elapsed_seconds)}</span>
      <span>Còn: {fmtTime(renderStatus.remaining_seconds)}</span>
      <span>Ước tính: {fmtTime(renderStatus.estimated_total_seconds)}</span>
    </div>
    {renderStatus.completed_segments != null && renderStatus.total_segments != null && (
      <p className="mt-1 text-[11px] text-slate-400">
        Segment: {renderStatus.completed_segments}/{renderStatus.total_segments}
      </p>
    )}
  </div>;
}

export function BatchPipelineProgress({ progress, onCancel }: { progress: BatchProgress | null; onCancel: () => void }) {
  if (!progress) return null;
  const doneCount = progress.items.filter(item => item.status === 'done').length;
  const errorCount = progress.items.filter(item => item.status === 'error').length;
  const cancelledCount = progress.items.filter(item => item.status === 'cancelled').length;
  const processed = doneCount + errorCount + cancelledCount;
  const percent = Math.round((processed / Math.max(1, progress.total_items)) * 100);
  const runningItem = progress.items.find(item => item.status === 'running');

  return <div className="rounded-2xl border border-fuchsia-500/20 bg-fuchsia-500/10 p-4">
    <div className="mb-3 flex items-start justify-between gap-3">
      <div>
        <h3 className="flex items-center gap-2 font-bold text-fuchsia-200"><ExternalLink size={18} />Batch Auto Pipeline</h3>
        <p className="mt-1 text-xs text-slate-400">{progress.total_items} video · Item {Math.min(progress.current_index + 1, progress.total_items)}/{progress.total_items} · {statusLabel(progress.status)}</p>
      </div>
      {progress.status === 'running' && <button className="btn-mini danger" onClick={onCancel}>Hủy batch</button>}
    </div>
    <div className="progress-track"><div className={`progress-fill ${progress.status === 'error' ? 'error' : progress.status === 'done' ? 'done' : ''}`} style={{ width: `${percent}%` }}/></div>
    <div className="mt-3 grid gap-2 text-xs text-slate-300 md:grid-cols-4">
      <span>Done: {doneCount}</span>
      <span>Error: {errorCount}</span>
      <span>Cancelled: {cancelledCount}</span>
      <span>Processed: {processed}/{progress.total_items}</span>
    </div>
    <div className="mt-4 space-y-2">
      {progress.items.map(item => <div key={`${item.index}-${item.source_url}`} className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
        <div className="flex items-start gap-3">
          <StatusIcon status={item.status} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <b className="text-sm text-slate-200">#{item.index + 1} {statusLabel(item.status)}</b>
              {item.job_id && <span className="text-[11px] text-slate-500">Job: {item.job_id}</span>}
            </div>
            <p className="mt-1 break-all text-xs text-slate-400">{item.source_url}</p>
            {item.error && <p className="mt-2 rounded-lg border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs text-red-200">{item.error}</p>}
            {Boolean(item.result?.final_video_path) && <p className="mt-2 break-all text-xs text-emerald-300">Output: {String(item.result?.final_video_path)}</p>}
          </div>
        </div>
        {item.status === 'running' && item.render_status && (
          <RenderProgressPanel renderStatus={item.render_status} />
        )}
        {runningItem?.index === item.index && item.task_id && !item.render_status && <div className="mt-3">
          <AutoPipelineProgress progress={{ task_id: item.task_id, step: 'batch_item', status: 'running', message: 'Đang xử lý video trong batch...', detail: null, result: item.result ?? null, error: item.error ?? null, states: item.states }} onCancel={onCancel} />
        </div>}
      </div>)}
    </div>
  </div>;
}
