import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Download, Eraser, Lock, LockOpen, Plus, Trash2, Upload } from 'lucide-react';
import { applyRenderJobBlur, blurPreviewUrl, fileDownloadUrl, openOutputFolder, renderBlurVideo, skipRenderJobBlur, uploadBlurVideo } from '../api';
import type { BlurKeyframe, BlurRegion, BlurRenderResponse, BlurUploadResponse, RenderJobStatus } from '../types';
import { Card, SectionTitle, Stat } from './common';

const COLORS = ['#60a5fa', '#34d399', '#f472b6', '#fb923c', '#a78bfa', '#facc15', '#f87171', '#2dd4bf'];

type BlurRegionLocal = BlurRegion & { id: string };
export type { BlurRegionLocal };

const LOCK_STORAGE_KEY = 'blur_locked_ids';

function loadLocked(): Set<string> {
  try {
    const raw = sessionStorage.getItem(LOCK_STORAGE_KEY);
    return new Set<string>(raw ? JSON.parse(raw) : []);
  } catch { return new Set(); }
}

function saveLocked(locked: Set<string>) {
  try { sessionStorage.setItem(LOCK_STORAGE_KEY, JSON.stringify([...locked])); } catch { /* sessionStorage unavailable */ }
}

function newRegionId(): string {
  return crypto.randomUUID();
}

function stripIds(regions: BlurRegionLocal[]): BlurRegion[] {
  return regions.map(({ id: _, ...rest }) => rest);
}

function getActiveKfIndex(keyframes: BlurKeyframe[], time: number): number | null {
  if (!keyframes.length) return null;
  if (time <= keyframes[0].time) return 0;
  for (let i = 0; i < keyframes.length - 1; i++) {
    if (time >= keyframes[i].time && time < keyframes[i + 1].time) return i;
  }
  return keyframes.length - 1;
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function updateOrAddKf(region: BlurRegion, time: number, patch: { x: number; y: number; width: number; height: number; strength?: number }): BlurRegion {
  const kfTime = Math.round(time * 100) / 100;
  const existing = region.keyframes.findIndex(k => Math.abs(k.time - kfTime) < 0.05);
  const updated: BlurKeyframe = { time: kfTime, x: patch.x, y: patch.y, width: patch.width, height: patch.height, strength: patch.strength ?? 14 };
  let keyframes: BlurKeyframe[];
  if (existing >= 0) {
    keyframes = [...region.keyframes];
    keyframes[existing] = updated;
  } else {
    keyframes = [...region.keyframes, updated].sort((a, b) => a.time - b.time);
  }
  return { ...region, keyframes };
}

function addKfToRegions(regions: BlurRegion[], regionId: string, time: number, patch: { x: number; y: number; width: number; height: number; strength?: number }): BlurRegion[] {
  return regions.map(r => isBlurRegionLocal(r) && (r as BlurRegionLocal).id === regionId ? updateOrAddKf(r, time, patch) : r);
}

function isBlurRegionLocal(r: BlurRegion): r is BlurRegionLocal {
  return 'id' in r;
}

function activeKfAt(region: BlurRegion, time: number): BlurKeyframe | null {
  const idx = getActiveKfIndex(region.keyframes, time);
  return idx !== null ? region.keyframes[idx] : null;
}

function handlePositions(rect: { x: number; y: number; width: number; height: number }) {
  const { x, y, width: w, height: h } = rect;
  return [
    { id: 'tl', x, y },
    { id: 'tc', x: x + w / 2, y },
    { id: 'tr', x: x + w, y },
    { id: 'ml', x, y: y + h / 2 },
    { id: 'mr', x: x + w, y: y + h / 2 },
    { id: 'bl', x, y: y + h },
    { id: 'bc', x: x + w / 2, y: y + h },
    { id: 'br', x: x + w, y: y + h },
  ] as const;
}

const HANDLE_CURSOR: Record<string, string> = {
  tl: 'nwse-resize', tc: 'ns-resize', tr: 'nesw-resize',
  ml: 'ew-resize', mr: 'ew-resize',
  bl: 'nesw-resize', bc: 'ns-resize', br: 'nwse-resize',
};

type HandleId = 'tl' | 'tc' | 'tr' | 'ml' | 'mr' | 'bl' | 'bc' | 'br';
const CORNER_HANDLES: HandleId[] = ['tl', 'tr', 'bl', 'br'];

export function BlurTool({ reviewJob, onAfterReviewDecision }: { reviewJob?: RenderJobStatus | null; onAfterReviewDecision?: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [upload, setUpload] = useState<BlurUploadResponse | null>(null);
  const [reviewRegions, setReviewRegions] = useState<BlurRegion[]>([]);
  const [regions, setRegions] = useState<BlurRegionLocal[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [lastSelected, setLastSelected] = useState<string | null>(null);
  const [locked, setLocked] = useState<Set<string>>(loadLocked);
  const [uploadDuration, setUploadDuration] = useState(30);
  const [rendering, setRendering] = useState(false);
  const [result, setResult] = useState<BlurRenderResponse | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const reviewRegionsLocal = useMemo(() => reviewRegions.map((r, i) => ({ ...r, id: `review-${i}` })), [reviewRegions]);

  useEffect(() => { saveLocked(locked); }, [locked]);

  function isLocked(id: string) { return locked.has(id); }

  function toggleLock(id: string) {
    setLocked(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function selectExclusive(id: string) {
    setSelected(new Set([id]));
    setLastSelected(id);
  }

  function toggleSelection(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
    setLastSelected(id);
  }

  function clearSelection() {
    setSelected(new Set());
    setLastSelected(null);
  }

  function handleBulkAction(action: 'select_all' | 'deselect_all') {
    if (action === 'select_all') {
      const unlocked = regions.filter(r => !locked.has(r.id)).map(r => r.id);
      if (unlocked.length === 0) return;
      setSelected(new Set(unlocked));
      setLastSelected(unlocked[unlocked.length - 1]);
    } else {
      clearSelection();
    }
  }

  async function handleUpload(file: File) {
    try {
      setResult(null);
      setRegions([]);
      clearSelection();
      const resp = await uploadBlurVideo(file);
      setUpload(resp);
      setUploadDuration(Number(resp.duration_seconds) || 30);
      toast.success('Đã upload video');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload video thất bại');
    }
  }

  async function exportBlurred() {
    if (!upload) return toast.error('Vui lòng upload video trước');
    if (!regions.length) return toast.error('Vui lòng tạo ít nhất một vùng blur');
    try {
      setRendering(true);
      const data = await renderBlurVideo({ video_path: upload.video_path, regions: stripIds(regions) });
      setResult(data);
      toast.success('Đã export video blur');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Render blur thất bại');
    } finally {
      setRendering(false);
    }
  }

  async function applyReviewBlur() {
    if (!reviewJob) return;
    if (!reviewRegions.length) return toast.error('Vui lòng tạo ít nhất một vùng blur hoặc chọn bỏ qua');
    try {
      setRendering(true);
      await applyRenderJobBlur(reviewJob.job_id, reviewRegions);
      toast.success('Đã áp dụng blur, job sẽ tiếp tục render final');
      onAfterReviewDecision?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không áp dụng blur được');
    } finally {
      setRendering(false);
    }
  }

  async function skipReviewBlur() {
    if (!reviewJob) return;
    try {
      setRendering(true);
      await skipRenderJobBlur(reviewJob.job_id);
      toast.success('Đã bỏ qua blur, job sẽ tiếp tục render final');
      onAfterReviewDecision?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không bỏ qua blur được');
    } finally {
      setRendering(false);
    }
  }

  return <Card><SectionTitle icon={Eraser} title="Blur Tool" desc="Upload video và kéo thả vùng blur để che logo/subtitle gốc"/>
    {reviewJob?.status === 'waiting_blur' && reviewJob.result?.pre_blur_video_path && <div className="mb-6 rounded-2xl border border-yellow-500/30 bg-yellow-500/10 p-4"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-lg font-bold text-yellow-100">Render Review Workspace</h3><p className="text-sm text-slate-300">Chọn vùng blur trên video trung gian kích thước lớn. Tọa độ sẽ áp dụng trước khi burn subtitle hoặc xuất final.</p></div><div className="flex flex-wrap gap-2"><button className="btn-secondary" disabled={rendering} onClick={skipReviewBlur}>Không blur, tiếp tục final</button><button className="btn-primary" disabled={rendering || !reviewRegions.length} onClick={applyReviewBlur}>Áp dụng blur và tiếp tục</button></div></div><div className="grid gap-5 xl:grid-cols-[1.45fr_.55fr]">      <BlurRegionEditor videoUrl={blurPreviewUrl(reviewJob.result.pre_blur_video_path)} regions={reviewRegionsLocal} selected={new Set()} locked={new Set()} onChange={r => setReviewRegions(stripIds(r))} onSelect={() => {}} onToggleLock={() => {}} onCurrentTimeChange={setCurrentTime}/><BlurRegionSidebar regions={reviewRegionsLocal} selected={new Set()} locked={new Set()} onChange={r => setReviewRegions(stripIds(r))} onSelect={() => {}} onToggleLock={() => {}} videoDuration={30} currentTime={currentTime}/></div></div>}
    <div className="mb-3 border-t border-white/10 pt-5"><h3 className="mb-2 font-bold">Upload Video Mode</h3><p className="mb-4 text-sm text-slate-400">Dùng khi muốn blur hậu kỳ một video bất kỳ từ máy.</p></div>
    <input ref={inputRef} type="file" accept="video/mp4,video/quicktime,video/webm,.mkv" hidden onChange={e => { const file = e.target.files?.[0]; if (file) void handleUpload(file); e.currentTarget.value = ''; }}/>
    <div className="mb-4 flex flex-wrap gap-2"><button className="btn-primary" onClick={() => inputRef.current?.click()}><Upload size={16}/>Upload video</button>{upload && <button className="btn-secondary" disabled={rendering} onClick={exportBlurred}>{rendering ? 'Đang export...' : 'Export video blur'}</button>}</div>
    {!upload && !reviewJob && <div className="mt-6 mb-4 text-center py-12 rounded-2xl border border-dashed border-white/10 bg-white/[0.02]"><Eraser size={48} className="mx-auto mb-4 opacity-20" /><p className="text-base font-medium text-slate-300">Upload a video to start creating blur regions</p><p className="text-sm text-slate-500 mt-1">Supports MP4, MOV, WebM, MKV</p><p className="text-xs text-slate-600 mt-3">Click "Upload video" above, then drag on the video to define blur areas</p></div>}
    {upload && <div className="grid gap-5 lg:grid-cols-[1.3fr_.7fr]">
      <BlurRegionEditor videoUrl={blurPreviewUrl(upload.preview_url)} regions={regions} selected={selected} locked={locked} onChange={setRegions} onSelect={(id, mode) => { if (id === null) { clearSelection(); return; } if (mode === 'toggle') toggleSelection(id); else selectExclusive(id); }} onToggleLock={toggleLock} onCurrentTimeChange={setCurrentTime}/>
      <BlurRegionSidebar regions={regions} selected={selected} locked={locked} onChange={setRegions} onSelect={(id, mode) => { if (id === null) { clearSelection(); return; } if (mode === 'toggle') toggleSelection(id); else selectExclusive(id); }} onToggleLock={toggleLock} onBulkAction={handleBulkAction} videoDuration={uploadDuration} currentTime={currentTime}/>
    </div>}
    {result && <div className="mt-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm"><b>Blur Result</b><p className="mt-2 break-all">Video: {result.final_video_path}</p><div className="mt-3 grid gap-2 md:grid-cols-4"><Stat label="Encoder" value={result.video_encoder_label || result.video_encoder || 'N/A'}/><Stat label="Output" value={`${result.output_codec || 'N/A'} ${result.output_fps || ''}`}/><Stat label="Resolution" value={result.output_resolution_actual || 'N/A'}/><Stat label="Size" value={result.output_file_size_bytes || 'N/A'}/></div><div className="mt-3 flex flex-wrap gap-2"><a className="btn-secondary" href={fileDownloadUrl(result.final_video_path)}><Download size={16}/>Tải video</a><button className="btn-secondary" onClick={() => void openOutputFolder(result.output_dir)}>Mở thư mục output</button></div></div>}
  </Card>;
}

export function BlurRegionEditor({ videoUrl, regions, selected, locked, onChange, onSelect, onToggleLock, onCurrentTimeChange }: { videoUrl: string; regions: BlurRegionLocal[]; selected: Set<string>; locked: Set<string>; onChange: (regions: BlurRegionLocal[]) => void; onSelect: (id: string | null, mode?: 'exclusive' | 'toggle') => void; onToggleLock: (id: string) => void; onCurrentTimeChange?: (t: number) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(100);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(30);
  const [isPlaying, setIsPlaying] = useState(false);
  const [draft, setDraft] = useState<{ x: number; y: number; width: number; height: number } | null>(null);
  const [multiDrafts, setMultiDrafts] = useState<Map<string, { x: number; y: number; width: number; height: number }> | null>(null);
  const dragRef = useRef<{ mode: string; regionIds: string[]; startPoint: { x: number; y: number }; startRects: Map<string, { x: number; y: number; w: number; h: number }>; snapshot: BlurRegionLocal[] } | null>(null);
  const isDraggingTimeline = useRef(false);
  const [showShortcuts, setShowShortcuts] = useState(false);

  const onTimeUpdate = useCallback(() => {
    const t = videoRef.current?.currentTime ?? 0;
    setCurrentTime(t);
    onCurrentTimeChange?.(t);
  }, [onCurrentTimeChange]);

  const onLoadedMetadata = useCallback(() => {
    if (videoRef.current) setDuration(videoRef.current.duration || 30);
  }, []);

  const onPlay = useCallback(() => setIsPlaying(true), []);
  const onPause = useCallback(() => setIsPlaying(false), []);

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { void v.play(); } else { v.pause(); }
  }

  function seekFromEvent(e: React.MouseEvent | MouseEvent) {
    const rect = timelineRef.current?.getBoundingClientRect();
    if (!rect || !videoRef.current) return;
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    videoRef.current.currentTime = pct * duration;
  }

  function goToKeyframe(dir: 'prev' | 'next') {
    const v = videoRef.current;
    if (!v || !regions.length) return;
    const allKfs = regions.flatMap(r => r.keyframes).map(kf => kf.time).sort((a, b) => a - b);
    if (!allKfs.length) return;
    const ct = v.currentTime;
    if (dir === 'prev') {
      const prev = allKfs.filter(t => t < ct - 0.01);
      v.currentTime = prev.length ? prev[prev.length - 1] : allKfs[allKfs.length - 1];
    } else {
      const next = allKfs.filter(t => t > ct + 0.01);
      v.currentTime = next.length ? next[0] : allKfs[0];
    }
  }

  function deleteSelectedRegions() {
    const unlocked = [...selected].filter(id => !locked.has(id));
    if (unlocked.length === 0) {
      toast('Selected region(s) are locked — unlock to delete.');
      return;
    }
    if (unlocked.length === 1) {
      // Single-select: current behavior (delete active keyframe or region)
      const id = unlocked[0];
      const region = regions.find(r => r.id === id);
      if (!region) return;
      const kfIdx = getActiveKfIndex(region.keyframes, currentTime);
      if (kfIdx === null) return;
      if (region.keyframes.length <= 1) {
        onChange(regions.filter(r => r.id !== id));
        onSelect(null);
      } else {
        onChange(regions.map(r => r.id !== id ? r : { ...r, keyframes: r.keyframes.filter((_, j) => j !== kfIdx) }));
      }
      return;
    }
    // Multi-select: confirm then delete entire regions
    if (!confirm(`Delete ${unlocked.length} blur region(s)?`)) return;
    const idSet = new Set(unlocked);
    onChange(regions.filter(r => !idSet.has(r.id)));
    onSelect(null);
  }

  useEffect(() => {
    function handleGlobalMouseUp() { isDraggingTimeline.current = false; }
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => window.removeEventListener('mouseup', handleGlobalMouseUp);
  }, []);

  function handleTimelineMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    isDraggingTimeline.current = true;
    seekFromEvent(e);
  }

  function handleTimelineMouseMove(e: React.MouseEvent) {
    if (isDraggingTimeline.current) seekFromEvent(e);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    const v = videoRef.current;
    if (!v) return;
    switch (e.key) {
      case ' ':
        e.preventDefault();
        togglePlay();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        if (e.shiftKey) { goToKeyframe('prev'); } else { v.currentTime = Math.max(0, v.currentTime - 0.5); }
        break;
      case 'ArrowRight':
        e.preventDefault();
        if (e.shiftKey) { goToKeyframe('next'); } else { v.currentTime = Math.min(duration, v.currentTime + 0.5); }
        break;
      case 'Delete':
      case 'Backspace':
        e.preventDefault();
        deleteSelectedRegions();
        break;
      case 'l':
      case 'L':
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          for (const id of selected) {
            onToggleLock(id);
          }
        }
        break;
      case '?':
        e.preventDefault();
        setShowShortcuts(prev => !prev);
        break;
    }
  }

  function normalize(event: React.MouseEvent | MouseEvent) {
    const rect = overlayRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
  }

  function clampRect(r: { x: number; y: number; w: number; h: number }) {
    let { x, y, w, h } = r;
    if (w < 0) { x = x + w; w = -w; }
    if (h < 0) { y = y + h; h = -h; }
    if (w < 0.01) w = 0.01;
    if (h < 0.01) h = 0.01;
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (x + w > 1) w = 1 - x;
    if (y + h > 1) h = 1 - y;
    return { x, y, w, h };
  }

  function computeGroupDelta(rawDx: number, rawDy: number, ids: string[], regions: BlurRegionLocal[], time: number): { dx: number; dy: number } {
    let dx = rawDx, dy = rawDy;
    for (const id of ids) {
      const region = regions.find(r => r.id === id);
      if (!region || locked.has(id)) continue;
      const kf = activeKfAt(region, time);
      if (!kf) continue;
      if (dx > 0) dx = Math.min(dx, 1 - (kf.x + kf.width));
      if (dx < 0) dx = Math.max(dx, -kf.x);
      if (dy > 0) dy = Math.min(dy, 1 - (kf.y + kf.height));
      if (dy < 0) dy = Math.max(dy, -kf.y);
    }
    return { dx, dy };
  }

  function commitDrag() {
    const drag = dragRef.current;
    if (!drag) return;
    const d = multiDrafts ?? (draft ? new Map([[drag.regionIds[0], draft]]) : null);
    dragRef.current = null;
    setDraft(null);
    setMultiDrafts(null);
    if (!d) return;
    const t = videoRef.current?.currentTime ?? 0;
    let next = [...drag.snapshot];
    for (const [id, rect] of d) {
      if (rect.width < 0.005 || rect.height < 0.005) continue;
      next = addKfToRegions(next, id, t, { x: rect.x, y: rect.y, width: rect.width, height: rect.height }) as BlurRegionLocal[];
    }
    onChange(next as BlurRegionLocal[]);
  }

  function startDrag(mode: string, ids: string[], p: { x: number; y: number }, rects: Map<string, { x: number; y: number; width: number; height: number }> | null, singleRect: { x: number; y: number; width: number; height: number } | null) {
    const snapshot = regions;
    const startRects: Map<string, { x: number; y: number; w: number; h: number }> = new Map();
    if (mode.startsWith('resize-') && ids.length === 1 && singleRect) {
      startRects.set(ids[0], { x: singleRect.x, y: singleRect.y, w: singleRect.width, h: singleRect.height });
    } else if (mode === 'move' && rects) {
      for (const [id, r] of rects) {
        if (!locked.has(id)) startRects.set(id, { x: r.x, y: r.y, w: r.width, h: r.height });
      }
    }
    dragRef.current = { mode, regionIds: [...startRects.keys()], startPoint: p, startRects, snapshot };
  }

  function handleMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    const p = normalize(e);
    const overlayRect = overlayRef.current?.getBoundingClientRect();
    if (!overlayRect) return;
    const handleThreshold = 10 / Math.min(overlayRect.width, overlayRect.height);
    setDraft(null);
    setMultiDrafts(null);

    // Find region under cursor (reverse z-order)
    let hitId: string | null = null;
    let hitRect: { x: number; y: number; width: number; height: number } | null = null;
    for (let i = regions.length - 1; i >= 0; i--) {
      const r = regions[i];
      const rect = activeKfAt(r, currentTime);
      if (!rect) continue;
      if (p.x >= rect.x && p.x <= rect.x + rect.width && p.y >= rect.y && p.y <= rect.y + rect.height) {
        hitId = r.id;
        hitRect = rect;
        break;
      }
    }

    // Check resize handle on primary selected
    if (selected.size === 1 && hitId && selected.has(hitId) && !locked.has(hitId)) {
      const rect = activeKfAt(regions.find(r => r.id === hitId)!, currentTime);
      if (rect) {
        for (const h of handlePositions(rect)) {
          if (Math.abs(p.x - h.x) < handleThreshold && Math.abs(p.y - h.y) < handleThreshold) {
            const rects = new Map([[hitId, { x: rect.x, y: rect.y, width: rect.width, height: rect.height }]]);
            startDrag(`resize-${h.id}`, [hitId], p, null, rect);
            return;
          }
        }
      }
    }

    if (hitId) {
      if (e.shiftKey || e.ctrlKey || e.metaKey) {
        onSelect(hitId, 'toggle');
      } else if (!selected.has(hitId)) {
        onSelect(hitId);
      }

      // Determine which regions to drag
      const isMoveAll = selected.size > 1;
      if (isMoveAll) {
        // Collect active keyframes for all selected unlocked regions
        const rects: Map<string, { x: number; y: number; width: number; height: number }> = new Map();
        for (const id of selected) {
          const r = regions.find(rr => rr.id === id);
          if (!r || locked.has(id)) continue;
          const kf = activeKfAt(r, currentTime);
          if (kf) rects.set(id, { x: kf.x, y: kf.y, width: kf.width, height: kf.height });
        }
        if (rects.size > 0) {
          startDrag('move', [...rects.keys()], p, rects, null);
          return;
        }
      }

      // Single drag
      const r = regions.find(rr => rr.id === hitId)!;
      const rect = activeKfAt(r, currentTime);
      if (rect && !locked.has(hitId)) {
        startDrag('move', [hitId], p, null, rect);
      }
      return;
    }

    // Empty space: clear selection + create new region
    clearSelection();
    const w = 0.15, h = 0.15;
    const x = Math.max(0, Math.min(1 - w, p.x - w / 2));
    const y = Math.max(0, Math.min(1 - h, p.y - h / 2));
    const id = newRegionId();
    const newRegion: BlurRegionLocal = { id, start: 0, end: duration, keyframes: [{ time: videoRef.current?.currentTime ?? 0, x, y, width: w, height: h, strength: 14 }], interpolate: false };
    onChange([...regions, newRegion]);
    selectExclusive(id);
  }

  function selectExclusive(id: string) {
    onSelect(id);
  }

  function clearSelection() {
    onSelect(null);
  }

  function handleMouseMove(e: React.MouseEvent) {
    if (!dragRef.current) return;
    const cur = normalize(e);
    const { mode, startPoint, startRects } = dragRef.current;

    if (mode === 'move') {
      // Compute global delta
      const rawDx = cur.x - startPoint.x;
      const rawDy = cur.y - startPoint.y;
      const ids = [...startRects.keys()];
      const { dx, dy } = computeGroupDelta(rawDx, rawDy, ids, regions, currentTime);

      if (ids.length === 1) {
        const sr = startRects.get(ids[0])!;
        const x = sr.x + dx;
        const y = sr.y + dy;
        setDraft({ x, y, width: sr.w, height: sr.h });
        setMultiDrafts(null);
      } else {
        const drafts: Map<string, { x: number; y: number; width: number; height: number }> = new Map();
        for (const id of ids) {
          const sr = startRects.get(id)!;
          drafts.set(id, { x: sr.x + dx, y: sr.y + dy, width: sr.w, height: sr.h });
        }
        setMultiDrafts(drafts);
        setDraft(null);
      }
      return;
    }

    // Resize (single region only)
    const sr = startRects.get([...startRects.keys()][0]);
    if (!sr) return;
    const dx = cur.x - startPoint.x;
    const dy = cur.y - startPoint.y;
    let x = sr.x, y = sr.y, w = sr.w, h = sr.h;
    const handle = mode.replace('resize-', '') as HandleId;
    switch (handle) {
      case 'tl': x = sr.x + dx; w = sr.w - dx; y = sr.y + dy; h = sr.h - dy; break;
      case 'tc': y = sr.y + dy; h = sr.h - dy; break;
      case 'tr': w = sr.w + dx; y = sr.y + dy; h = sr.h - dy; break;
      case 'ml': x = sr.x + dx; w = sr.w - dx; break;
      case 'mr': w = sr.w + dx; break;
      case 'bl': x = sr.x + dx; w = sr.w - dx; h = sr.h + dy; break;
      case 'bc': h = sr.h + dy; break;
      case 'br': w = sr.w + dx; h = sr.h + dy; break;
    }
    if (e.shiftKey && (CORNER_HANDLES as readonly string[]).includes(handle)) {
      const aspect = sr.w / sr.h;
      if (Math.abs(dx) >= Math.abs(dy)) {
        h = w / aspect;
        if (handle === 'tl' || handle === 'tr') y = sr.y + sr.h - h;
      } else {
        w = h * aspect;
        if (handle === 'tl' || handle === 'bl') x = sr.x + sr.w - w;
      }
    }
    const clamped = clampRect({ x, y, w, h });
    setDraft({ x: clamped.x, y: clamped.y, width: clamped.w, height: clamped.h });
  }

  function handleMouseUp() {
    commitDrag();
  }

  function cancelDrag() {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDraft(null);
    setMultiDrafts(null);
  }

  return <div tabIndex={0} onKeyDown={handleKeyDown} className="outline-none"><div className="mb-2 flex flex-wrap items-center gap-2"><span className="text-xs text-slate-400">Zoom</span>{[100, 150, 200].map(v => <button key={v} className="btn-mini" onClick={() => setZoom(v)}>{v}%</button>)}<button className="btn-mini ml-auto" onClick={() => setShowShortcuts(prev => !prev)} title="Keyboard shortcuts">?</button></div>
    {showShortcuts && <div className="mb-2 rounded-xl border border-white/10 bg-slate-950/80 p-3 text-xs text-slate-300"><div className="grid gap-x-6 gap-y-1" style={{ gridTemplateColumns: 'max-content 1fr' }}><span className="font-mono text-yellow-300">Space</span><span>Play / Pause</span><span className="font-mono text-yellow-300">← / →</span><span>Seek -0.5s / +0.5s</span><span className="font-mono text-yellow-300">Shift + ← / →</span><span>Prev / Next keyframe</span><span className="font-mono text-yellow-300">Delete / Backspace</span><span>Delete region or keyframe</span><span className="font-mono text-yellow-300">Ctrl+L / Cmd+L</span><span>Toggle lock on selected</span><span className="font-mono text-yellow-300">Shift/Ctrl/Cmd + Click</span><span>Toggle multi-select</span><span className="font-mono text-yellow-300">Click empty area</span><span>Create blur region</span><span className="font-mono text-yellow-300">?</span><span>Toggle this panel</span></div></div>}
    <div className="overflow-auto rounded-t-2xl border border-white/10 bg-black"><div className="relative mx-auto" style={{ width: `${zoom}%`, minWidth: zoom > 100 ? `${zoom}%` : '100%' }}><video ref={videoRef} className="block w-full" src={videoUrl} onTimeUpdate={onTimeUpdate} onLoadedMetadata={onLoadedMetadata} onPlay={onPlay} onPause={onPause}/><div ref={overlayRef} className="absolute inset-0" style={{ cursor: dragRef.current ? (dragRef.current.mode === 'move' ? 'grabbing' : HANDLE_CURSOR[dragRef.current.mode.replace('resize-', '')] || 'default') : 'crosshair' }} onMouseDown={handleMouseDown} onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={cancelDrag}>{regions.map((region, ri) => {
    const isLocked = locked.has(region.id);
    const dragRect = selected.has(region.id) && multiDrafts?.get(region.id) ? multiDrafts.get(region.id)! : null;
    const localDraft = selected.size === 1 && selected.has(region.id) && draft ? draft : null;
    const rect = dragRect ?? localDraft ?? activeKfAt(region, currentTime);
    if (!rect) return null;
    const isSelected = selected.has(region.id);
    const isPrimary = selected.size === 1 && selected.has(region.id);
    const color = isPrimary ? '#eab308' : isSelected ? COLORS[ri % COLORS.length] : COLORS[ri % COLORS.length];
    return <div key={region.id} className={`absolute pointer-events-none ${isSelected ? 'border-2' : 'border'}`} style={{ left: `${rect.x * 100}%`, top: `${rect.y * 100}%`, width: `${rect.width * 100}%`, height: `${rect.height * 100}%`, borderColor: color, backgroundColor: `${color}20`, opacity: isLocked ? 0.5 : 1 }}>{isPrimary && !isLocked && handlePositions(rect).map(h => <div key={h.id} className="absolute w-2 h-2 -ml-1 -mt-1 border border-white" style={{ left: `${h.x * 100}%`, top: `${h.y * 100}%`, backgroundColor: color }}/>)}
      {isLocked && <div className="absolute inset-0 flex items-center justify-center text-white/40" style={{ fontSize: `${Math.min(rect.width, rect.height) * 60}%` }}>🔒</div>}
    </div>;
  })}</div></div></div><div className="flex items-center gap-1.5 rounded-b-xl border border-t-0 border-white/10 bg-slate-900 px-2 py-1.5"><button className="btn-mini px-1.5" onClick={togglePlay} title="Play/Pause (Space)">{isPlaying ? '⏸' : '▶'}</button><button className="btn-mini px-1.5" onClick={() => goToKeyframe('prev')} title="Previous keyframe (Shift+←)">⏮</button><div ref={timelineRef} className="relative flex-1 h-6 cursor-pointer rounded bg-slate-800" onMouseDown={handleTimelineMouseDown} onMouseMove={handleTimelineMouseMove}><div className="pointer-events-none absolute left-0 top-0 h-full rounded bg-cyan-600/30" style={{ width: `${(currentTime / duration) * 100}%` }}/><div className="pointer-events-none absolute left-0 top-0 h-full w-full">{regions.flatMap((r, ri) => { const activeIdx = getActiveKfIndex(r.keyframes, currentTime); return r.keyframes.map((kf, ki) => { const isActive = selected.has(r.id) && ki === activeIdx; return <div key={`${r.id}-${ki}`} className="absolute top-0 h-full w-0.5" style={{ left: `${(kf.time / duration) * 100}%`, backgroundColor: isActive ? '#eab308' : COLORS[ri % COLORS.length] }}/>; }); })}</div><div className="pointer-events-none absolute left-0 top-0 h-full w-1 -translate-x-1/2 rounded-full bg-cyan-400" style={{ left: `${(currentTime / duration) * 100}%` }}/></div><button className="btn-mini px-1.5" onClick={() => goToKeyframe('next')} title="Next keyframe (Shift+→)">⏭</button><span className="w-20 text-right text-[11px] tabular-nums text-slate-400">{formatTime(currentTime)} / {formatTime(duration)}</span></div>{!showShortcuts && <p className="mt-2 text-xs text-slate-500">Press ? for shortcuts</p>}</div>;
}

function regionDimLabel(region: BlurRegionLocal, time: number): string {
  const kf = activeKfAt(region, time);
  if (!kf) return '';
  return `${(kf.width * 100).toFixed(0)}×${(kf.height * 100).toFixed(0)}%`;
}

export function BlurRegionSidebar({ regions, selected, locked, onChange, onSelect, onToggleLock, onBulkAction, videoDuration = 30, currentTime = 0 }: { regions: BlurRegionLocal[]; selected: Set<string>; locked: Set<string>; onChange: (regions: BlurRegionLocal[]) => void; onSelect: (id: string | null, mode?: 'exclusive' | 'toggle') => void; onToggleLock: (id: string) => void; onBulkAction?: (action: 'select_all' | 'deselect_all') => void; videoDuration?: number; currentTime?: number }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selectedKf, setSelectedKf] = useState<number | null>(null);

  const toggleExpand = (idx: number) => {
    const next = new Set(expanded);
    if (next.has(idx)) next.delete(idx); else next.add(idx);
    setExpanded(next);
  };

  const patchKf = (ri: number, ki: number, patch: Partial<BlurKeyframe>) => {
    onChange(regions.map((r, i) => i !== ri ? r : {
      ...r, keyframes: r.keyframes.map((k, j) => j === ki ? { ...k, ...patch } : k),
    }));
  };

  const deleteKf = (ri: number, ki: number) => {
    const r = regions[ri];
    if (r.keyframes.length <= 1) {
      onChange(regions.filter((_, i) => i !== ri));
      if (selected.has(r.id)) onSelect(null);
      return;
    }
    onChange(regions.map((reg, i) => i !== ri ? reg : { ...reg, keyframes: reg.keyframes.filter((_, j) => j !== ki) }));
    if (selectedKf === ki) setSelectedKf(null);
  };

  const addKfNow = (ri: number) => {
    const t = currentTime;
    const r = regions[ri];
    const prevKf = [...r.keyframes].sort((a, b) => Math.abs(a.time - t) - Math.abs(b.time - t))[0];
    const newKf: BlurKeyframe = { time: t, x: prevKf?.x ?? 0.05, y: prevKf?.y ?? 0.78, width: prevKf?.width ?? 0.9, height: prevKf?.height ?? 0.18, strength: prevKf?.strength ?? 14 };
    const sorted = [...r.keyframes, newKf].sort((a, b) => a.time - b.time);
    onChange(regions.map((reg, i) => i !== ri ? reg : { ...reg, keyframes: sorted }));
  };

  const newRegion = (x: number, y: number, width: number, height: number) => {
    const id = newRegionId();
    const region: BlurRegionLocal = { id, start: 0, end: videoDuration, keyframes: [{ time: 0, x, y, width, height, strength: 14 }], interpolate: false };
    onChange([...regions, region]);
    onSelect(id);
    setExpanded(new Set([...expanded, regions.length]));
  };

  return <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4"><h3 className="mb-3 font-bold">Vùng blur</h3><div className="flex flex-wrap gap-2">
    <button className="btn-mini" onClick={() => newRegion(0.05, 0.78, 0.9, 0.18)}>Blur subtitle bottom</button>
    <button className="btn-mini" onClick={() => newRegion(0.02, 0.02, 0.18, 0.1)}>Top-left logo</button>
    <button className="btn-mini" onClick={() => newRegion(0.8, 0.02, 0.18, 0.1)}>Top-right logo</button>
  </div>
  {regions.length > 0 && <div className="mt-1 mb-1 flex flex-wrap gap-1.5">{selected.size > 0 && <button className="btn-mini" onClick={() => onBulkAction?.('deselect_all')}>Bỏ chọn</button>}<button className="btn-mini" onClick={() => onBulkAction?.('select_all')}>Chọn tất cả</button></div>}
  {selected.size > 0 && <div className="mt-2 rounded-xl border border-cyan-500/20 bg-cyan-500/10 p-2 text-xs text-cyan-300">
    {selected.size} region(s) selected · {locked.size} locked
    <span className="ml-2 text-slate-400">Ctrl+L toggle lock · Del delete</span>
  </div>}
  {regions.map((region, ri) => {
    const isLocked = locked.has(region.id);
    const isSelected = selected.has(region.id);
    return <div key={region.id} className="mt-3 rounded-xl border border-white/10 bg-[#070B18] p-3" style={{ borderColor: isSelected ? COLORS[ri % COLORS.length] : undefined, opacity: isLocked ? 0.55 : 1 }}>
      <button className="flex w-full items-center justify-between text-left" onClick={(e) => { if (e.shiftKey || e.ctrlKey || e.metaKey) { onSelect(region.id, 'toggle'); } else { onSelect(region.id); } toggleExpand(ri); }}>
        <span className="font-bold text-sm"><span className="inline-block w-2.5 h-2.5 rounded-full mr-1.5 align-middle" style={{ backgroundColor: COLORS[ri % COLORS.length] }}/>#{ri + 1} <span className="text-xs text-slate-400">· {region.keyframes.length} kf · {regionDimLabel(region, currentTime)}</span></span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500" onClick={e => { e.stopPropagation(); onToggleLock(region.id); }}>
            {isLocked ? <Lock size={14} /> : <LockOpen size={14} />}{isLocked && <span className="ml-0.5 text-[10px] text-slate-500">Locked</span>}
          </span>
          <span className="text-xs text-slate-500">{expanded.has(ri) ? '▲' : '▼'}</span>
        </div>
      </button>
      {expanded.has(ri) && <div className="mt-2 space-y-2">{region.keyframes.map((kf, ki) => { const isActiveKf = isSelected && getActiveKfIndex(region.keyframes, currentTime) === ki; const isSelectedKf = selectedKf === ki; const kfBorder = isActiveKf ? 'border-cyan-400/50 bg-cyan-400/5' : isSelectedKf ? 'border-yellow-400/60 bg-yellow-400/5' : 'border-white/10';
      return <div key={ki} className={`rounded-lg border p-2 ${kfBorder}`}>
        {([
          ['t', kf.time, (v: number) => patchKf(ri, ki, { time: v }), 0, 99999],
          ['x', kf.x, (v: number) => patchKf(ri, ki, { x: v }), 0, 1],
          ['y', kf.y, (v: number) => patchKf(ri, ki, { y: v }), 0, 1],
          ['w', kf.width, (v: number) => patchKf(ri, ki, { width: v }), 0, 1],
          ['h', kf.height, (v: number) => patchKf(ri, ki, { height: v }), 0, 1],
          ['s', kf.strength, (v: number) => patchKf(ri, ki, { strength: Math.round(v) }), 1, 30],
        ] as const).map(([label, value, onValueChange, min, max]) => <label key={label} className="flex items-center gap-1"><span className="w-3 text-slate-500">{label}</span><input className="input flex-1" type="number" min={min} max={max} step={0.01} value={value} onChange={e => onValueChange(Number(e.target.value))} disabled={isLocked}/></label>)}
        <button className="btn-mini danger mt-1" disabled={isLocked} onClick={() => deleteKf(ri, ki)}><Trash2 size={10}/> Xóa keyframe</button>
      </div>; })}</div>}
      <div className="mt-2 flex gap-2">
        <button className="btn-mini flex-1" disabled={isLocked} onClick={() => addKfNow(ri)}><Plus size={12}/> @{currentTime.toFixed(1)}s</button>
        <button className="btn-mini danger" disabled={isLocked} onClick={() => { onChange(regions.filter((_, i) => i !== ri)); if (isSelected) onSelect(null); }}>Xóa region</button>
      </div>
    </div>;
  })}</div>;
}
