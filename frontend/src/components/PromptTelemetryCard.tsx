import { useEffect, useState } from 'react';
import { fetchPromptRunStats } from '../api';
import type { PromptRunStats } from '../types';
import { Card, SectionTitle } from './common';
import { Activity } from 'lucide-react';

export function PromptTelemetryCard() {
  const [stats, setStats] = useState<PromptRunStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchPromptRunStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  if (!stats || stats.total_runs === 0) return null;

  return (
    <div className="mt-6">
      <Card>
        <button className="flex w-full items-center justify-between gap-2" onClick={() => setCollapsed(!collapsed)}>
          <SectionTitle icon={Activity} title="Usage Stats" desc="Prompt generation analytics" />
          <span className="text-xs text-slate-500">{collapsed ? '▶' : '▼'}</span>
        </button>
        {!collapsed && (<>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <StatBox label="Total" value={stats.total_runs} />
          <StatBox label="Success" value={stats.success_count} />
          <StatBox label="Errors" value={stats.error_count} />
          <StatBox label="Avg Health" value={stats.avg_health_score != null ? `${stats.avg_health_score}` : '-'} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {stats.top_presets.length > 0 && (
            <div>
              <h4 className="text-sm font-bold mb-1">Top Presets</h4>
              <div className="space-y-1 text-xs">
                {stats.top_presets.map((p, i) => (
                  <div key={i} className="flex justify-between"><span>{p.name}</span><span className="text-slate-400">{p.count}</span></div>
                ))}
              </div>
            </div>
          )}
          {stats.top_rewrite_styles.length > 0 && (
            <div>
              <h4 className="text-sm font-bold mb-1">Top Rewrite Styles</h4>
              <div className="space-y-1 text-xs">
                {stats.top_rewrite_styles.map((s, i) => (
                  <div key={i} className="flex justify-between"><span>{s.style}</span><span className="text-slate-400">{s.count}</span></div>
                ))}
              </div>
            </div>
          )}
        </div>
        {stats.daily_counts.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-bold mb-1">Last 30 Days</h4>
            <div className="flex items-end gap-1 h-16">
              {stats.daily_counts.slice(0, 14).reverse().map((d, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full bg-cyan-600/40 rounded-t" style={{ height: `${Math.max(4, (d.count / Math.max(...stats.daily_counts.map(x => x.count))) * 48)}px` }} title={`${d.date}: ${d.count} runs`} />
                  <span className="text-[8px] text-slate-500">{d.date.slice(5)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-3 text-xs text-slate-400">
          <span className="mr-4">Last 7d: {stats.last_7d_count}</span>
          <span>Prev 7d: {stats.prev_7d_count}</span>
        </div>
        </>)}
      </Card>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-slate-900/60 border border-white/10 p-3 text-center">
      <div className="text-lg font-bold">{value}</div>
      <div className="text-[10px] text-slate-400">{label}</div>
    </div>
  );
}
