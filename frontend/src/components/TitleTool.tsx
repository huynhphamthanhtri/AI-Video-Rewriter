import { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff, Type } from 'lucide-react';
import type { TitleLayoutPreviewResponse } from '../types';
import type { GeminiEdlPayload, RenderOptions } from '../types';
import { fetchTitleLayoutPreview } from '../api';
import { Card, Pill, SectionTitle } from './common';

/**
 * Compute safe margin as percentage of each axis, derived from backend
 * safe_margin_px. Structured to support future safeMarginX / safeMarginY
 * without refactoring callers.
 */
function safeMarginPct(
  layoutPreview: TitleLayoutPreviewResponse | null,
  modelWidth: number,
  modelHeight: number,
): { top: number; right: number; bottom: number; left: number } {
  if (!layoutPreview || !layoutPreview.safe_margin_px) {
    return { top: 6, right: 6, bottom: 6, left: 6 };
  }
  const margin = layoutPreview.safe_margin_px;
  // FUTURE: when backend returns safeMarginX / safeMarginY:
  //   const mx = layoutPreview.safe_margin_x ?? margin;
  //   const my = layoutPreview.safe_margin_y ?? margin;
  const pctX = (margin / modelWidth) * 100;
  const pctY = (margin / modelHeight) * 100;
  return { top: pctY, right: pctX, bottom: pctY, left: pctX };
}

type TitleToolProps = {
  renderOptions: RenderOptions;
  jsonPayload: GeminiEdlPayload | null;
  onRenderOptionsChange: (value: RenderOptions) => void;
};

export function TitleTool({ renderOptions, jsonPayload, onRenderOptionsChange }: TitleToolProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [frameWidth, setFrameWidth] = useState(0);
  const [showGuides, setShowGuides] = useState(false);
  const [layoutPreview, setLayoutPreview] = useState<TitleLayoutPreviewResponse | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const updateOptions = (patch: Partial<RenderOptions>) => onRenderOptionsChange({ ...renderOptions, ...patch });

  const model = targetTitlePreviewSize(renderOptions);
  const scale = frameWidth > 0 ? frameWidth / model.width : 1;

  const isVertical = renderOptions.vertical_mode !== 'none';
  const isBlurFit = renderOptions.vertical_mode === 'blur_fit';
  const isBreaking = renderOptions.title_style === 'breaking_yellow' && renderOptions.title_position === 'top';

  const fgW = 1080;
  const fgH = 1080;
  const fgY = (model.height - fgH) / 2;
  const fgX = (model.width - fgW) / 2;

  useEffect(() => {
    const node = frameRef.current;
    if (!node) return;
    const update = () => setFrameWidth(node.getBoundingClientRect().width);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetchTitleLayoutPreview({
          render_options: renderOptions,
          video_width: model.width,
          video_height: model.height,
        });
        setLayoutPreview(res);
      } catch {
        setLayoutPreview(estimateLayout(renderOptions, model.width, model.height));
      }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [renderOptions, model.width, model.height]);

  const display = layoutPreview ?? estimateLayout(renderOptions, model.width, model.height);
  const lines = display.lines;
  const badge = display.badge;

  return <Card>
    <SectionTitle icon={Type} title="Title Tool" desc="Preview title overlay đúng tỉ lệ trước khi render"/>
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <div className="rounded-[28px] border border-white/10 bg-slate-950/60 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2"><Pill tone="cyan">{isBlurFit ? '9:16 blur fit' : isVertical ? '9:16 center crop' : '16:9 horizontal'}</Pill><Pill tone={lines.length > 0 ? 'green' : 'yellow'}>{lines.length > 0 ? `${lines.length} dòng` : 'Không có title'}</Pill></div>
          <span className="text-xs text-slate-500">Model: {model.width}x{model.height}</span>
        </div>
        <div className="grid min-h-[520px] place-items-center rounded-[24px] border border-white/10 bg-[#020617] p-4">
          <div ref={frameRef} className={`relative w-full overflow-hidden rounded-[24px] border border-white/10 shadow-2xl ${isVertical ? 'aspect-[9/16] max-h-[74vh] max-w-[440px]' : 'aspect-video max-w-5xl'}`}>

            {isBlurFit ? <>
              <div className="absolute inset-0 bg-gradient-to-b from-slate-800/85 via-slate-700/60 to-slate-800/85"/>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,rgba(148,163,184,.28),transparent_30%)]"/>
              <div className="absolute rounded-[16px] border border-white/20 bg-[radial-gradient(circle_at_50%_28%,rgba(148,163,184,.38),transparent_30%),linear-gradient(135deg,#4b5563,#111827)] shadow-xl shadow-black/60"
                style={{ left: fgX * scale, top: fgY * scale, width: fgW * scale, height: fgH * scale }}
              >
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="rounded-2xl border border-white/15 bg-white/10 px-3 py-1.5 text-[11px] font-semibold text-white/60">Video {fgW}x{fgH}</div>
                </div>
              </div>
              <div className="absolute left-3 top-3 rounded bg-black/60 px-2 py-1 text-[10px] font-semibold leading-none text-white/60">Blur background</div>
              <div className="absolute left-3 rounded bg-black/60 px-2 py-1 text-[10px] font-semibold leading-none text-white/60" style={{ top: fgY * scale + 4, fontSize: `${10 * Math.min(1, scale * 2)}px` }}>Foreground {fgW}x{fgH}</div>
            </> : <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,rgba(148,163,184,.32),transparent_30%),linear-gradient(135deg,#1f2937,#020617)]"/>}

            {showGuides && (() => {
              const m = safeMarginPct(layoutPreview, model.width, model.height);
              return <>
                <div className="absolute rounded-[20px] border border-dashed border-white/20"
                  style={{ left: `${m.left}%`, right: `${m.right}%`, top: `${m.top}%`, bottom: `${m.bottom}%` }}
                />
                {display.header_height_px > 0 && (
                  <div className="absolute rounded-t-[20px] border-b border-dashed border-amber-400/30 bg-amber-400/5"
                    style={{ left: `${m.left}%`, right: `${m.right}%`, top: `${m.top}%`, height: `${(display.header_height_px / model.height) * 100}%` }}
                  >
                    <span className="absolute left-1 top-0 text-[9px] text-amber-400/60">Header {display.header_height_px}px · Safe {display.safe_margin_px}px</span>
                  </div>
                )}
                <div className="absolute inset-x-[14%] bottom-[8%] rounded-xl bg-black/50 px-4 py-2 text-center text-sm font-semibold text-white/70">
                  Safe {display.safe_margin_px}px · Header {display.header_height_px}px
                </div>
              </>;
            })()}

            {renderOptions.title_mode !== 'none' && isBreaking && <div className="absolute inset-x-0 top-0" style={{ height: display.header_height_px * scale, backgroundColor: 'rgba(0,0,0,.82)' }}>
              <div className="absolute inset-x-0 top-0 bg-[#B91C1C]" style={{ height: Math.max(9, model.height * 0.009) * scale }}/>
              <div className="absolute inset-x-0 bg-[#FFD319]" style={{ bottom: 0, height: Math.max(6, model.height * 0.006) * scale }}/>
              {badge && <div className="absolute rounded-lg bg-[#B91C1C] font-black uppercase tracking-wide text-white shadow-xl" style={{
                left: badge.x_px * scale,
                top: badge.y_px * scale,
                padding: `${10 * scale}px ${13 * scale}px`,
                fontSize: badge.font_size * scale,
                lineHeight: `${Math.max(28, badge.font_size - 12) * scale}px`,
              }}>{badge.text}</div>}
            </div>}

            {renderOptions.title_mode !== 'none' && lines.length > 0 && <div className="absolute" style={{
              top: lines[0].y_px * scale,
              left: lines[0].x_px * scale,
              right: renderOptions.title_text_align === 'right' && lines[0].x_px > 0 ? 'auto' : undefined,
            }}>
              <div className="inline-block max-w-full rounded-2xl text-center shadow-2xl" style={{
                backgroundColor: isBreaking ? 'rgba(0,0,0,.70)' : lines[0].has_background ? lines[0].background_color?.replace('black@', 'rgba(0,0,0,').replace(/@(\d+\.?\d*)/, ',$1)') : 'transparent',
                color: lines[0].font_color === '0xFFD319' ? '#FFD319' : 'white',
                fontFamily: 'Segoe UI, Arial, sans-serif',
                fontSize: lines[0].font_size * scale,
                fontWeight: 400,
                lineHeight: `${(lines[0].font_size + 12) * scale}px`,
                padding: `${18 * scale}px ${27 * scale}px`,
                textShadow: `${2 * scale}px ${2 * scale}px ${2 * scale}px rgba(0,0,0,.8)`,
                textAlign: renderOptions.title_text_align === 'left' ? 'left' : renderOptions.title_text_align === 'right' ? 'right' : 'center',
              }}>
                {lines.map((line, index) => (
                  <span
                    className="block whitespace-nowrap"
                    style={{ marginTop: index === 0 ? 0 : 8 * scale }}
                    key={`${line.text}-${index}`}
                  >{line.text}</span>
                ))}
              </div>
            </div>}
          </div>
        </div>
        <div className="mt-3 grid gap-2 text-xs text-slate-400 md:grid-cols-4"><span>Target: {model.width}x{model.height}</span><span>Font: {lines.length > 0 ? `${lines[0].font_size}px` : '-'}</span><span>Y: {lines.length > 0 ? `${lines[0].y_px}px` : '-'}</span><span>Scale: {scale.toFixed(3)}</span></div>
      </div>

      <aside className="rounded-[24px] border border-amber-500/20 bg-amber-500/10 p-4">
        <h3 className="mb-3 text-lg font-bold">Title Controls</h3>
        <div className="grid gap-3">
          <div><label className="label">Title overlay</label><select className="select-ghost" value={renderOptions.title_mode} onChange={e => updateOptions({ title_mode: e.target.value as RenderOptions['title_mode'] })}><option value="auto">Auto from JSON title</option><option value="custom">Custom title</option><option value="none">Off</option></select></div>
          {renderOptions.title_mode === 'custom' && <div><label className="label">Custom title</label><textarea className="textarea min-h-[110px]" value={renderOptions.title_text} onChange={e => updateOptions({ title_text: e.target.value })} placeholder="Title hiển thị trên đầu video"/></div>}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <div><label className="label">Style</label><select className="select-ghost" value={renderOptions.title_style} onChange={e => updateOptions({ title_style: e.target.value as RenderOptions['title_style'] })}><option value="breaking_yellow">Breaking + Yellow</option><option value="yellow_highlight">Yellow highlight</option><option value="dark_badge">Dark badge</option><option value="clean_white">Clean white</option></select></div>
            <div><label className="label">Font size</label><select className="select-ghost" value={renderOptions.title_font_size} onChange={e => updateOptions({ title_font_size: e.target.value as RenderOptions['title_font_size'] })}><option value="auto">Auto</option><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></div>
          </div>
          <div><label className="label">Canh chữ</label><select className="select-ghost" value={renderOptions.title_text_align} onChange={e => updateOptions({ title_text_align: e.target.value as RenderOptions['title_text_align'] })}><option value="left">Trái</option><option value="center">Giữa</option><option value="right">Phải</option></select></div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <div><label className="label">Max lines</label><select className="select-ghost" value={renderOptions.title_max_lines} onChange={e => updateOptions({ title_max_lines: Number(e.target.value) })}><option value={1}>1 dòng</option><option value={2}>2 dòng</option><option value={3}>3 dòng</option></select></div>
            <div><label className="label">Chars / line</label><input className="input py-2" type="number" min={16} max={60} value={renderOptions.title_chars_per_line} onChange={e => updateOptions({ title_chars_per_line: Number(e.target.value) })}/></div>
          </div>
          <div><label className="label">Position</label><select className="select-ghost" value={renderOptions.title_position} onChange={e => updateOptions({ title_position: e.target.value as RenderOptions['title_position'] })}><option value="top">Top</option><option value="upper_third">Upper third</option><option value="center">Center</option><option value="bottom">Bottom</option></select></div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <div><label className="label">Badge</label><select className="select-ghost" value={renderOptions.title_badge_mode} onChange={e => updateOptions({ title_badge_mode: e.target.value as RenderOptions['title_badge_mode'] })}><option value="none">Không badge</option><option value="auto">Auto badge</option><option value="custom">Custom badge</option></select></div>
            {renderOptions.title_badge_mode === 'custom' && <div><label className="label">Badge text</label><input className="input" value={renderOptions.title_badge_text} onChange={e => updateOptions({ title_badge_text: e.target.value })} placeholder="BODYCAM"/></div>}
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <div><label className="label">Title duration</label><select className="select-ghost" value={renderOptions.title_show_duration} onChange={e => updateOptions({ title_show_duration: e.target.value as RenderOptions['title_show_duration'] })}><option value="full">Xuyên suốt video</option><option value="intro_only">Chỉ intro</option></select></div>
            {renderOptions.title_show_duration === 'intro_only' && <div><label className="label">Intro seconds</label><input className="input py-2" type="number" min={1} max={30} value={renderOptions.title_intro_seconds} onChange={e => updateOptions({ title_intro_seconds: Number(e.target.value) })}/></div>}
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <div><label className="label">Header height</label><input className="input py-2" type="number" min={0} max={360} value={renderOptions.title_header_height} onChange={e => updateOptions({ title_header_height: Number(e.target.value) })} placeholder="0 = auto"/></div>
            <div><label className="label">Safe margin</label><input className="input py-2" type="number" min={0} max={240} value={renderOptions.title_safe_margin} onChange={e => updateOptions({ title_safe_margin: Number(e.target.value) })} placeholder="0 = auto"/></div>
          </div>
          <div><label className="label">Output ratio source</label><select className="select-ghost" value={renderOptions.vertical_mode} onChange={e => updateOptions({ vertical_mode: e.target.value as RenderOptions['vertical_mode'] })}><option value="none">16:9 / giữ ngang</option><option value="blur_fit">9:16 blur fit</option><option value="center_crop">9:16 center crop</option></select></div>
          <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
            <input type="checkbox" checked={showGuides} onChange={e => setShowGuides(e.target.checked)}/>
            {showGuides ? <Eye size={16}/> : <EyeOff size={16}/>}
            Show guides
          </label>
          <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-3 text-xs text-slate-400">Auto title lấy từ <code>metadata.video_title</code>. Nếu preview báo title bị rút gọn, hãy tăng max lines, tăng chars/line hoặc giảm font size.</div>
        </div>
      </aside>
    </div>
  </Card>;
}

function targetTitlePreviewSize(options: RenderOptions) {
  const isVertical = options.vertical_mode !== 'none';
  if (isVertical) return options.output_resolution === '720p' ? { width: 720, height: 1280 } : { width: 1080, height: 1920 };
  return options.output_resolution === '720p' ? { width: 1280, height: 720 } : { width: 1920, height: 1080 };
}

function estimateLayout(options: RenderOptions, width: number, height: number): TitleLayoutPreviewResponse {
  const fontPx = options.title_font_size === 'small' ? 38 : options.title_font_size === 'medium' ? 48 : options.title_font_size === 'large' ? 60 : 52;
  const fontColor = options.title_style === 'yellow_highlight' || options.title_style === 'breaking_yellow' ? '0xFFD319' : 'white';
  const safeMarginPx = options.title_safe_margin > 0 ? options.title_safe_margin : Math.max(42, width * 0.035);
  const headerHeightPx = options.title_header_height > 0 ? options.title_header_height : Math.max(118, height * 0.105);

  const interlineGap = 8;
  const previewLines = fallbackWrapTitle(options);
  const lines = previewLines.map((text, i) => {
    const estimatedW = Math.max(16, Math.round(text.length * fontPx * 0.6));
    const estimatedH = fontPx + 12;

    let yPx: number;
    if (options.title_position === 'upper_third') yPx = Math.round(height * 0.16);
    else if (options.title_position === 'center') yPx = Math.round((height - (previewLines.length * fontPx + (previewLines.length - 1) * interlineGap)) / 2);
    else if (options.title_position === 'bottom') yPx = height - (previewLines.length * fontPx + (previewLines.length - 1) * interlineGap) - Math.round(height * 0.08);
    else if (options.title_style === 'breaking_yellow') yPx = Math.max(28, Math.round(height * 0.034));
    else yPx = Math.max(42, Math.round(height * 0.045));

    if (i > 0) yPx += i * (fontPx + interlineGap);

    let xPx: number;
    const hasBadge = options.title_badge_mode !== 'none';
    if (options.title_text_align === 'left') {
      xPx = options.title_style === 'breaking_yellow' && hasBadge ? safeMarginPx + Math.max(160, Math.round(width * 0.14)) : safeMarginPx;
    } else if (options.title_text_align === 'right') {
      xPx = width - estimatedW - safeMarginPx;
    } else {
      xPx = Math.round((width - estimatedW) / 2);
    }

    const bgColors: Record<string, string> = {
      yellow_highlight: 'black@0.55',
      dark_badge: 'black@0.75',
      clean_white: 'black@0.25',
      breaking_yellow: 'black@0.70',
    };

    return {
      text,
      x_px: xPx,
      y_px: yPx,
      font_size: fontPx,
      font_color: fontColor,
      width_px: estimatedW,
      height_px: estimatedH,
      has_background: true,
      background_color: bgColors[options.title_style] ?? 'black@0.55',
    };
  });

  let badgeResult = null;
  if (options.title_badge_mode !== 'none') {
    const badgeText = options.title_badge_mode === 'custom'
      ? options.title_badge_text.trim().toUpperCase().slice(0, 32)
      : 'TRUE CRIME';
    const badgeFontSize = Math.max(24, fontPx - 18);
    badgeResult = {
      text: badgeText,
      x_px: safeMarginPx,
      y_px: Math.max(30, Math.round(height * 0.036)),
      font_size: badgeFontSize,
      font_color: 'white',
      width_px: Math.max(16, Math.round(badgeText.length * badgeFontSize * 0.7)),
      height_px: badgeFontSize + 12,
      has_background: true,
      background_color: '0xB91C1C@0.95',
    };
  }

  return {
    lines,
    badge: badgeResult,
    header_drawbox: null,
    safe_margin_px: safeMarginPx,
    header_height_px: headerHeightPx,
  };
}

function fallbackWrapTitle(options: RenderOptions) {
  const rawTitle = options.title_text || 'Title preview';
  const maxLines = Math.max(1, Math.min(3, Number(options.title_max_lines) || 2));
  const charsPerLine = Math.max(16, Math.min(60, Number(options.title_chars_per_line) || 34));
  const words = rawTitle.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return ['Title preview'];
  const result: string[] = [];
  let current = '';
  for (const word of words) {
    const next = `${current} ${word}`.trim();
    if (next.length > charsPerLine && current) {
      result.push(current);
      current = word;
      if (result.length === maxLines) break;
    } else {
      current = next;
    }
  }
  if (current && result.length < maxLines) result.push(current);
  const text = result.join(' ');
  const original = words.join(' ');
  if (text.length < original.length) {
    const last = result.length - 1;
    result[last] = `${result[last].slice(0, Math.max(0, charsPerLine - 3)).trim()}...`;
  }
  return result.slice(0, maxLines);
}
