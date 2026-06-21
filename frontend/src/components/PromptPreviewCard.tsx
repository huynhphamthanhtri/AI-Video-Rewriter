import { useEffect, useRef, useState } from 'react';
import { Copy, Eye, EyeOff, Loader2 } from 'lucide-react';
import { fetchPromptPreview } from '../api';
import type { PromptPreviewResponse } from '../types';
import { Card, Pill, SectionTitle } from './common';

type PromptPreviewCardProps = {
  formFields: Record<string, unknown>;
};

export function PromptPreviewCard({ formFields }: PromptPreviewCardProps) {
  const [preview, setPreview] = useState<PromptPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
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
        const result = await fetchPromptPreview({
          rewrite_style: formFields.rewrite_style,
          target_audience: formFields.target_audience,
          tone: formFields.tone,
          target_duration: formFields.target_duration,
          retention_mode: formFields.retention_mode,
          hook_style: formFields.hook_style,
          clip_strategy: formFields.clip_strategy,
          reuse_level: formFields.reuse_level,
          content_density: formFields.content_density,
          target_language: formFields.target_language,
          target_market: formFields.target_market,
          localization_level: formFields.localization_level,
          rename_characters: formFields.rename_characters,
          adapt_culture: formFields.adapt_culture,
          adapt_currency: formFields.adapt_currency,
          adapt_units: formFields.adapt_units,
          adapt_company_names: formFields.adapt_company_names,
          adaptation_mode: formFields.adaptation_mode,
          narrator_persona: formFields.narrator_persona,
        }, controller.signal);
        if (requestIdRef.current === requestId) {
          setPreview(result);
        }
      } catch {
        if (requestIdRef.current === requestId) {
          setError('Không thể tạo preview.');
        }
      } finally {
        if (requestIdRef.current === requestId) {
          setLoading(false);
        }
      }
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      controller.abort();
    };
  }, [formFields.rewrite_style, formFields.target_audience, formFields.tone, formFields.target_duration, formFields.retention_mode, formFields.hook_style, formFields.clip_strategy, formFields.reuse_level, formFields.content_density, formFields.target_language, formFields.target_market, formFields.localization_level, formFields.rename_characters, formFields.adapt_culture, formFields.adapt_currency, formFields.adapt_units, formFields.adapt_company_names, formFields.adaptation_mode, formFields.narrator_persona]);

  const toggleSection = (title: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };

  if (loading && !preview) {
    return (
      <Card>
        <SectionTitle icon={Eye} title="Prompt Preview" desc="Xem trước prompt dựa trên cấu hình hiện tại" />
        <div className="flex items-center gap-3 py-4 text-sm text-slate-400">
          <Loader2 size={18} className="animate-spin" />
          Đang tạo preview...
        </div>
      </Card>
    );
  }

  if (error && !preview) {
    return (
      <Card>
        <SectionTitle icon={Eye} title="Prompt Preview" desc="Xem trước prompt dựa trên cấu hình hiện tại" />
        <div className="py-4 text-sm text-red-400">{error}</div>
      </Card>
    );
  }

  if (!preview) return null;

  return (
    <Card>
      <SectionTitle icon={Eye} title="Prompt Preview" desc="Xem trước prompt dựa trên cấu hình hiện tại" />
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <Pill tone="cyan">{preview.full_length} ký tự</Pill>
        <Pill tone="green">~{preview.estimated_tokens} tokens</Pill>
        <Pill tone="violet">{preview.sections.length} sections</Pill>
        <button
          className="btn-mini ml-auto"
          onClick={() => navigator.clipboard.writeText(preview.preview_text)}
        >
          <Copy size={14} /> Copy full prompt
        </button>
      </div>
      <div className="space-y-2">
        {preview.sections.map(section => {
          const isExpanded = expandedSections.has(section.title);
          return (
            <div
              key={section.title}
              className="rounded-xl border border-white/10 bg-slate-950/40"
            >
              <button
                className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-sm font-semibold text-slate-200 hover:bg-white/5"
                onClick={() => toggleSection(section.title)}
              >
                <span>{section.title}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">
                    pos {section.start}–{section.end}
                  </span>
                  {isExpanded ? <EyeOff size={14} /> : <Eye size={14} />}
                </div>
              </button>
              {isExpanded && (
                <div className="border-t border-white/5 px-4 py-3">
                  <pre className="whitespace-pre-wrap break-all text-xs text-slate-300">
                    {section.excerpt}
                  </pre>
                  <div className="mt-2 flex justify-end">
                    <button
                      className="btn-mini text-[11px]"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(section.excerpt);
                      }}
                    >
                      <Copy size={12} /> Copy section
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
