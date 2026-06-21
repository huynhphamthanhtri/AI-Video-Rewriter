import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import type { GeminiEdlPayload, VideoSegment } from '../types';
import { fmt, parseClipTime, parseSrtTime } from '../utils/time';
import { Card, Pill, SectionTitle, Stat } from './common';

export function EdlSummary({ payload, stats, onOpen }: { payload: GeminiEdlPayload | null; stats: { subDur: number; segDur: number } | null; onOpen: () => void }) {
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

export function EdlInspector({ payload, onApply, onApplyAndValidate }: { payload: GeminiEdlPayload | null; onApply: (payload: GeminiEdlPayload) => void; onApplyAndValidate: (payload: GeminiEdlPayload) => void }) {
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
    updateSegment(seg.segment_id, { source_start: secondsToClip(start), source_end: secondsToClip(end) });
  };
  const trimToSubtitle = (seg: VideoSegment) => {
    const sub = draft.srt.filter(s => s.index >= seg.subtitle_start && s.index <= seg.subtitle_end);
    const sd = sub.reduce((a, s) => a + parseSrtTime(s.end) - parseSrtTime(s.start), 0);
    updateSegment(seg.segment_id, { source_end: secondsToClip(parseClipTime(seg.source_start) + sd) });
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

function secondsToClip(value: number) {
  const safe = Math.max(0, value);
  const totalMs = Math.round(safe * 1000);
  const ms = totalMs % 1000;
  const totalSeconds = Math.floor(totalMs / 1000);
  const seconds = totalSeconds % 60;
  const minutes = Math.floor(totalSeconds / 60) % 60;
  const hours = Math.floor(totalSeconds / 3600);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}
