import { useState } from 'react';
import { ArrowLeftRight, Loader2 } from 'lucide-react';
import { fetchPresetCompare } from '../api';
import type { Preset, PresetCompareDiff, PresetCompareResponse } from '../types';
import { Card, SectionTitle } from './common';

type PresetCompareCardProps = {
  presets: Preset[];
};

const GROUP_LABELS: Record<string, string> = {
  intent: 'Intent',
  strategy: 'Strategy',
  constraints: 'Constraints',
  localization: 'Localization',
  versioning: 'Versioning',
};

const GROUP_ORDER = ['intent', 'strategy', 'constraints', 'localization', 'versioning'];

export function PresetCompareCard({ presets }: PresetCompareCardProps) {
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [result, setResult] = useState<PresetCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCompare() {
    if (!leftId || !rightId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetchPresetCompare(leftId, rightId);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'So sánh thất bại.');
    } finally {
      setLoading(false);
    }
  }

  const leftPreset = presets.find(p => p.id === leftId || p.name === leftId);
  const rightPreset = presets.find(p => p.id === rightId || p.name === rightId);

  const groupedDiffs: Record<string, PresetCompareDiff[]> = {};
  if (result) {
    for (const d of result.different) {
      if (!groupedDiffs[d.group]) groupedDiffs[d.group] = [];
      groupedDiffs[d.group].push(d);
    }
  }

  return (
    <Card>
      <SectionTitle icon={ArrowLeftRight} title="So sánh Preset" desc="Chọn hai preset để so sánh chi tiết" />
      <div className="mb-4 grid gap-3 md:grid-cols-[1fr_auto_1fr]">
        <div>
          <label className="label">Preset bên trái</label>
          <select
            className="select-ghost"
            value={leftId}
            onChange={e => { setLeftId(e.target.value); setResult(null); }}
          >
            <option value="">-- Chọn preset --</option>
            {presets.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} {p.is_builtin ? '(built-in)' : '(custom)'}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end justify-center pb-2">
          <ArrowLeftRight size={20} className="text-slate-500" />
        </div>
        <div>
          <label className="label">Preset bên phải</label>
          <select
            className="select-ghost"
            value={rightId}
            onChange={e => { setRightId(e.target.value); setResult(null); }}
          >
            <option value="">-- Chọn preset --</option>
            {presets.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} {p.is_builtin ? '(built-in)' : '(custom)'}
              </option>
            ))}
          </select>
        </div>
      </div>
      <button
        className="btn-primary"
        disabled={!leftId || !rightId || leftId === rightId || loading}
        onClick={handleCompare}
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowLeftRight size={16} />}
        {loading ? 'Đang so sánh...' : 'So sánh'}
      </button>
      {leftId === rightId && leftId && (
        <p className="mt-2 text-xs text-amber-400">Chọn hai preset khác nhau để so sánh.</p>
      )}
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      {result && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-bold text-cyan-200">{result.left_name}</span>
            <ArrowLeftRight size={14} className="text-slate-500" />
            <span className="font-bold text-cyan-200">{result.right_name}</span>
          </div>
          {result.same.length > 0 && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-emerald-300">
                Giống nhau ({result.same.length})
              </p>
              <div className="flex flex-wrap gap-1.5 text-xs text-slate-300">
                {result.same.map(f => (
                  <span key={f} className="rounded-md bg-emerald-950/50 px-2 py-0.5">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}
          {GROUP_ORDER.map(group => {
            const diffs = groupedDiffs[group];
            if (!diffs || diffs.length === 0) return null;
            return (
              <div key={group} className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-amber-300">
                  {GROUP_LABELS[group] ?? group} ({diffs.length})
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-500">
                        <th className="pb-1 pr-4">Field</th>
                        <th className="pb-1 pr-4 text-red-300">Left</th>
                        <th className="pb-1 text-emerald-300">Right</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diffs.map(d => (
                        <tr key={d.field} className="border-t border-white/5">
                          <td className="py-1.5 pr-4 font-medium text-slate-200">{d.field}</td>
                          <td className="py-1.5 pr-4 text-red-300">{String(d.left)}</td>
                          <td className="py-1.5 text-emerald-300">{String(d.right)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
          {result.different.length === 0 && (
            <p className="text-sm text-emerald-300">Hai preset giống hệt nhau.</p>
          )}
        </div>
      )}
    </Card>
  );
}
