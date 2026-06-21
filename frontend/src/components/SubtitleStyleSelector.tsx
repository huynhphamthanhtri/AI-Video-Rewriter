import { Captions } from 'lucide-react';
import type { RenderOptions } from '../types';
import { Card, Pill, SectionTitle } from './common';

type SubtitleStyleSelectorProps = {
  renderOptions: RenderOptions;
  onChange: (patch: Partial<RenderOptions>) => void;
};

const styleLabels: Record<string, string> = {
  default: 'Default — Arial 48px, viền nhẹ, hộp nền',
  shorts_bold: 'Shorts Bold — Arial 52px, viền dày, nổi bật',
  documentary: 'Documentary — Tahoma 42px, thanh lịch',
  minimal: 'Minimal — Arial 36px, không viền, không hộp',
  news: 'News — Tahoma 46px, sạch sẽ, giống phát thanh viên',
  high_contrast: 'High Contrast — Arial 50px, viền dày, tương phản cao',
};

export function SubtitleStyleSelector({ renderOptions, onChange }: SubtitleStyleSelectorProps) {
  return (
    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-bold">Subtitle Style</h4>
        <Pill tone="green">{renderOptions.subtitle_style}</Pill>
      </div>
      <div className="grid gap-3">
        <div>
          <label className="label">Kiểu phụ đề</label>
          <select
            className="select-ghost"
            value={renderOptions.subtitle_style}
            onChange={e => onChange({ subtitle_style: e.target.value as RenderOptions['subtitle_style'] })}
          >
            {Object.entries(styleLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="label">Cỡ chữ</label>
            <select
              className="select-ghost"
              value={renderOptions.subtitle_font_size}
              onChange={e => onChange({ subtitle_font_size: e.target.value as RenderOptions['subtitle_font_size'] })}
            >
              <option value="auto">Auto — theo style</option>
              <option value="small">Small (36px)</option>
              <option value="medium">Medium (48px)</option>
              <option value="large">Large (56px)</option>
            </select>
          </div>
          <div>
            <label className="label">Vị trí</label>
            <select
              className="select-ghost"
              value={renderOptions.subtitle_position}
              onChange={e => onChange({ subtitle_position: e.target.value as RenderOptions['subtitle_position'] })}
            >
              <option value="bottom">Dưới cùng</option>
              <option value="center">Giữa màn hình</option>
              <option value="top">Trên cùng</option>
            </select>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="label">Canh lề</label>
            <select
              className="select-ghost"
              value={renderOptions.subtitle_text_align}
              onChange={e => onChange({ subtitle_text_align: e.target.value as RenderOptions['subtitle_text_align'] })}
            >
              <option value="center">Canh giữa</option>
              <option value="left">Canh trái</option>
            </select>
          </div>
          <div>
            <label className="label">Số chữ tối đa / dòng</label>
            <input
              className="input"
              type="number"
              min={20}
              max={80}
              value={renderOptions.subtitle_max_chars_per_line}
              onChange={e => onChange({ subtitle_max_chars_per_line: Math.max(20, Math.min(80, Number(e.target.value))) })}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
            <input
              type="checkbox"
              checked={renderOptions.subtitle_outline}
              onChange={e => onChange({ subtitle_outline: e.target.checked })}
            />
            Viền chữ (Outline)
          </label>
          <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
            <input
              type="checkbox"
              checked={renderOptions.subtitle_shadow}
              onChange={e => onChange({ subtitle_shadow: e.target.checked })}
            />
            Bóng đổ (Shadow)
          </label>
          <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
            <input
              type="checkbox"
              checked={renderOptions.subtitle_box}
              onChange={e => onChange({ subtitle_box: e.target.checked })}
            />
            Hộp nền (Box)
          </label>
        </div>
      </div>
    </div>
  );
}
