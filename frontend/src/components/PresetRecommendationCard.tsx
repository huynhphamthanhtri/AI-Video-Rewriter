import { useEffect, useRef, useState } from 'react';
import { fetchPresetRecommendations } from '../api';
import type { PresetRecommendResponse } from '../types';

const CONFIDENCE_COLORS: Record<string, string> = {
  strong: 'bg-emerald-500',
  medium: 'bg-amber-400',
  weak: 'bg-slate-400',
};

export function PresetRecommendationCard({
  videoTitle,
  youtubeUrl,
  onApplyPreset,
}: {
  videoTitle?: string;
  youtubeUrl?: string;
  onApplyPreset: (presetName: string) => void;
}) {
  const [data, setData] = useState<PresetRecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const hasTitle = videoTitle?.trim();
    const hasUrl = youtubeUrl?.trim();
    if (!hasTitle && !hasUrl) {
      setData(null);
      return;
    }
    setLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetchPresetRecommendations({
          video_title: hasTitle || undefined,
          youtube_url: hasUrl || undefined,
        });
        setData(res);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    }, 800);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [videoTitle, youtubeUrl]);

  if (loading) {
    return <div className="mt-3 text-xs text-slate-400 animate-pulse">Analyzing video title...</div>;
  }

  if (!data || !data.title || data.recommendations.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-bold">Recommended Presets</h4>
        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
          {data.title_source === 'provided' ? 'From title' : 'From YouTube'}
        </span>
      </div>
      <p className="mb-2 truncate text-[11px] text-slate-500" title={data.title}>{data.title}</p>
      <div className="space-y-2">
        {data.recommendations.map((rec, i) => (
          <div key={i} className="flex items-center gap-2 rounded-lg border border-white/5 bg-slate-900/40 p-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{rec.preset_name}</span>
                <span className={`text-[10px] font-bold ${rec.confidence_label === 'strong' ? 'text-emerald-400' : rec.confidence_label === 'medium' ? 'text-amber-400' : 'text-slate-400'}`}>
                  {Math.round(rec.confidence * 100)}%
                </span>
              </div>
              <div className="mt-0.5 h-1 w-full rounded-full bg-slate-700">
                <div className={`h-full rounded-full ${CONFIDENCE_COLORS[rec.confidence_label] || 'bg-slate-500'}`}
                  style={{ width: `${rec.confidence * 100}%` }} />
              </div>
              {rec.matched_keywords.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {rec.matched_keywords.slice(0, 5).map((kw, j) => (
                    <span key={j} className="rounded bg-slate-800 px-1 py-0.5 text-[9px] text-slate-400">{kw}</span>
                  ))}
                </div>
              )}
            </div>
            <button className="btn-mini shrink-0" onClick={() => onApplyPreset(rec.preset_name)}>
              Apply
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
