import { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowLeftRight, X } from 'lucide-react';
import { fetchSubtitleStylePreviews } from '../api';
import type { SubtitlePreviewStyleResponse, RenderOptions } from '../types';
import SubtitlePreviewCard from './SubtitlePreviewCard';

interface Props {
  renderOptions: RenderOptions;
  onChange?: (patch: Partial<RenderOptions>) => void;
}

const diffFields: { key: keyof SubtitlePreviewStyleResponse['styles'][0]['css']; label: string; fmt: (v: string | number) => string }[] = [
  { key: 'font_family', label: 'Font', fmt: (v) => String(v) },
  { key: 'font_size_px', label: 'Cỡ chữ', fmt: (v) => `${v}px` },
  { key: 'outline_width_px', label: 'Viền (Outline)', fmt: (v) => (Number(v) > 0 ? `${v}px` : 'Không') },
  { key: 'shadow_offset_px', label: 'Bóng đổ (Shadow)', fmt: (v) => (Number(v) > 0 ? `${v}px` : 'Không') },
  { key: 'background_color', label: 'Hộp nền (Box)', fmt: (v) => (String(v) !== 'transparent' ? 'Có' : 'Không') },
  { key: 'text_align', label: 'Canh lề', fmt: (v) => (String(v) === 'center' ? 'Giữa' : 'Trái') },
];

export default function SubtitleGallery({ renderOptions, onChange }: Props) {
  const [data, setData] = useState<SubtitlePreviewStyleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sampleText, setSampleText] = useState('Xin chào, đây là phụ đề preview');
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareA, setCompareA] = useState<string | null>(null);
  const [compareB, setCompareB] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) abortRef.current.abort();
    setError(null);

    const requestId = ++requestIdRef.current;
    const controller = new AbortController();
    abortRef.current = controller;

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await fetchSubtitleStylePreviews({
          subtitle_font_size: renderOptions.subtitle_font_size,
          subtitle_position: renderOptions.subtitle_position,
          subtitle_text_align: renderOptions.subtitle_text_align,
          subtitle_outline: renderOptions.subtitle_outline,
          subtitle_shadow: renderOptions.subtitle_shadow,
          subtitle_box: renderOptions.subtitle_box,
          sample_text: sampleText,
        }, controller.signal);
        if (requestIdRef.current === requestId) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        if (requestIdRef.current === requestId) {
          console.error('Subtitle preview error:', err);
          setError('Không tải được preview subtitle.');
        }
      } finally {
        if (requestIdRef.current === requestId) {
          setLoading(false);
        }
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      controller.abort();
    };
  }, [
    renderOptions.subtitle_font_size,
    renderOptions.subtitle_position,
    renderOptions.subtitle_text_align,
    renderOptions.subtitle_outline,
    renderOptions.subtitle_shadow,
    renderOptions.subtitle_box,
    sampleText,
  ]);

  const handleSelect = useCallback((key: string) => {
    if (!compareA) {
      setCompareA(key);
    } else if (!compareB && key !== compareA) {
      setCompareB(key);
    }
  }, [compareA, compareB]);

  const exitCompare = useCallback(() => {
    setCompareEnabled(false);
    setCompareA(null);
    setCompareB(null);
  }, []);

  const applyStyle = useCallback((key: string) => {
    onChange?.({ subtitle_style: key as RenderOptions['subtitle_style'] });
    exitCompare();
  }, [onChange, exitCompare]);

  const swapStyles = useCallback(() => {
    setCompareA(compareB);
    setCompareB(compareA);
  }, [compareA, compareB]);

  const comparing = compareEnabled && compareA && compareB && data;

  const renderCompareView = () => {
    if (!data || !compareA || !compareB) return null;
    const itemA = data.styles.find((s) => s.key === compareA);
    const itemB = data.styles.find((s) => s.key === compareB);
    if (!itemA || !itemB) return null;

    return (
      <>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-emerald-400 font-semibold">A: {itemA.label}</span>
            <span className="text-white/40">vs</span>
            <span className="text-blue-400 font-semibold">B: {itemB.label}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-mini" onClick={swapStyles} title="Đổi vị trí A/B">
              <ArrowLeftRight size={14} /> Đổi vị trí
            </button>
            <button className="btn-mini" onClick={exitCompare}>
              <X size={14} /> Thoát
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SubtitlePreviewCard
            styleKey={itemA.key}
            label={itemA.label}
            description={itemA.description}
            css={itemA.css}
            sampleText={sampleText}
            selected="A"
          />
          <SubtitlePreviewCard
            styleKey={itemB.key}
            label={itemB.label}
            description={itemB.description}
            css={itemB.css}
            sampleText={sampleText}
            selected="B"
          />
        </div>

        <div className="mt-4 overflow-x-auto rounded-xl border border-white/10 bg-slate-950/40 p-3">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-white/40 uppercase tracking-wide">
                <th className="pb-2 pr-4">Thuộc tính</th>
                <th className="pb-2 pr-4 text-emerald-400">Style A</th>
                <th className="pb-2 text-blue-400">Style B</th>
              </tr>
            </thead>
            <tbody>
              {diffFields.map(({ key, label, fmt }) => {
                const valA = fmt(itemA.css[key]);
                const valB = fmt(itemB.css[key]);
                const differs = valA !== valB;
                return (
                  <tr key={key} className="border-t border-white/5">
                    <td className="py-2 pr-4 text-white/60">{label}</td>
                    <td className={`py-2 pr-4 ${differs ? 'text-emerald-300' : 'text-white/60'}`}>{valA}</td>
                    <td className={`py-2 ${differs ? 'text-blue-300' : 'text-white/60'}`}>{valB}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn-secondary text-sm" onClick={() => applyStyle(compareA)}>
            Áp dụng Style A: {itemA.label}
          </button>
          <button className="btn-secondary text-sm" onClick={() => applyStyle(compareB)}>
            Áp dụng Style B: {itemB.label}
          </button>
        </div>
      </>
    );
  };

  return (
    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-bold">
          {comparing ? 'So sánh style' : compareEnabled ? 'Chọn style để so sánh' : 'Preview tất cả style'}
        </h4>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            className="input max-w-xs text-xs"
            placeholder="Nhập text preview..."
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
          />
          {!compareEnabled && (
            <button className="btn-mini" onClick={() => setCompareEnabled(true)}>
              So sánh style
            </button>
          )}
        </div>
      </div>

      {compareEnabled && !comparing && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-white/60">
          {!compareA && <span>Chọn style đầu tiên (A)...</span>}
          {compareA && !compareB && <span>Đã chọn A, chọn style thứ hai (B)...</span>}
          {compareA && (
            <button className="btn-mini" onClick={exitCompare}>
              <X size={14} /> Thoát
            </button>
          )}
        </div>
      )}

      {loading && !data && <div className="py-4 text-center text-sm text-white/40">Đang tải preview...</div>}
      {error && <div className="py-4 text-center text-sm text-red-400">{error}</div>}

      {data && comparing && renderCompareView()}

      {data && !comparing && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.styles.map((item) => (
            <SubtitlePreviewCard
              key={item.key}
              styleKey={item.key}
              label={item.label}
              description={item.description}
              css={item.css}
              sampleText={sampleText}
              onSelect={compareEnabled ? handleSelect : undefined}
              selected={item.key === compareA ? 'A' : item.key === compareB ? 'B' : 'none'}
            />
          ))}
        </div>
      )}
    </div>
  );
}
