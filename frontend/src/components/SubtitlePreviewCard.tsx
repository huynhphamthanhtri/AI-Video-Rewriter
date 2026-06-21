import { SubtitleStyleCss } from '../types';

interface Props {
  styleKey: string;
  label: string;
  description: string;
  css: SubtitleStyleCss;
  sampleText?: string;
  onSelect?: (styleKey: string) => void;
  selected?: 'none' | 'A' | 'B';
}

export default function SubtitlePreviewCard({
  styleKey,
  label,
  description,
  css,
  sampleText = 'Xin chào, đây là phụ đề preview',
  onSelect,
  selected = 'none',
}: Props) {
  const outlineStyle =
    css.outline_width_px > 0
      ? ({
          WebkitTextStroke: `${css.outline_width_px}px ${css.outline_color}`,
          textStroke: `${css.outline_width_px}px ${css.outline_color}`,
        } as React.CSSProperties)
      : {};

  const shadowStyle =
    css.shadow_offset_px > 0
      ? ({ textShadow: `${css.shadow_offset_px}px ${css.shadow_offset_px}px 2px ${css.shadow_color}` } as React.CSSProperties)
      : {};

  const boxStyle =
    css.background_color !== 'transparent'
      ? ({ backgroundColor: css.background_color, padding: '8px 16px', borderRadius: '4px' } as React.CSSProperties)
      : {};

  const scaledSize = Math.min(css.font_size_px, 36);

  const selectRing =
    selected === 'A' ? 'ring-2 ring-emerald-400' :
    selected === 'B' ? 'ring-2 ring-blue-400' : '';

  return (
    <div
      className={`rounded-2xl border border-white/10 bg-slate-900/60 p-3 ${selectRing} ${onSelect ? 'cursor-pointer hover:ring-1 hover:ring-white/30' : ''}`}
      onClick={onSelect ? () => onSelect(styleKey) : undefined}
    >
      <div className="relative mb-2 aspect-video overflow-hidden rounded-xl bg-gradient-to-b from-slate-800 to-black">
        <div
          className={`absolute bottom-0 left-0 right-0 flex items-end justify-center p-3 ${
            css.text_align === 'left' ? 'justify-start' : css.text_align === 'right' ? 'justify-end' : ''
          }`}
        >
          <span
            style={{
              fontFamily: css.font_family,
              fontSize: `${scaledSize}px`,
              color: css.color,
              lineHeight: 1.4,
              wordBreak: 'break-word',
              ...outlineStyle,
              ...shadowStyle,
              ...boxStyle,
            }}
          >
            {sampleText}
          </span>
        </div>
      </div>
      <div className="text-xs text-white/60">
        <span className="font-semibold text-white/80">{label}</span>
        <span className="ml-2">{description}</span>
      </div>
    </div>
  );
}
