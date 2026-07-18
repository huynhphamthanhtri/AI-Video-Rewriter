import { Captions } from 'lucide-react';
import type { RenderOptions } from '../types';
import { Card, Pill, SectionTitle } from './common';

type SubtitleStyleSelectorProps = {
  renderOptions: RenderOptions;
  onChange: (patch: Partial<RenderOptions>) => void;
};

const styleLabels: Record<string, string> = {
  default: 'Mặc định — Arial 48px, viền nhẹ, hộp nền',
  shorts_bold: 'Shorts Bold — Arial 52px, viền dày, nổi bật',
  documentary: 'Phim tài liệu — Tahoma 42px, thanh lịch',
  minimal: 'Tối giản — Arial 36px, không viền, không hộp',
  news: 'Tin tức — Tahoma 46px, sạch sẽ, giống phát thanh viên',
  high_contrast: 'Tương phản cao — Arial 50px, viền dày, tương phản cao',
};

const stylePillLabels: Record<string, string> = {
  default: 'Mặc định',
  shorts_bold: 'Shorts Bold',
  documentary: 'Phim tài liệu',
  minimal: 'Tối giản',
  news: 'Tin tức',
  high_contrast: 'Tương phản cao',
};

export function SubtitleStyleSelector({ renderOptions, onChange }: SubtitleStyleSelectorProps) {
  return (
    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-bold">Kiểu phụ đề</h4>
        <Pill tone="green">{stylePillLabels[renderOptions.subtitle_style] ?? renderOptions.subtitle_style}</Pill>
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
              <option value="auto">Tự động — theo style</option>
              <option value="small">Nhỏ (36px)</option>
              <option value="medium">Vừa (48px)</option>
              <option value="large">Lớn (56px)</option>
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
            Viền chữ
          </label>
          <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
            <input
              type="checkbox"
              checked={renderOptions.subtitle_shadow}
              onChange={e => onChange({ subtitle_shadow: e.target.checked })}
            />
            Bóng đổ
          </label>
          <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
            <input
              type="checkbox"
              checked={renderOptions.subtitle_box}
              onChange={e => onChange({ subtitle_box: e.target.checked })}
            />
            Hộp nền
          </label>
        </div>
      </div>
    </div>
  );
}
