import { useEffect, useRef, useState } from 'react';
import { Loader2, Play, Volume2 } from 'lucide-react';
import { toast } from 'sonner';
import { fetchTtsStatus, fetchTtsVoices } from '../api';
import type { RenderOptions, TtsVoice } from '../types';
import { Card, Pill, SectionTitle } from './common';

function RankBadge({ rank }: { rank?: number }) {
  if (!rank || rank > 3) return null;
  const stars = rank === 1 ? '\u2605\u2605\u2605' : rank === 2 ? '\u2605\u2605' : '\u2605';
  const color = rank === 1 ? 'text-yellow-400' : rank === 2 ? 'text-yellow-500' : 'text-yellow-600';
  const title = rank === 1 ? 'Viral' : rank === 2 ? 'Ph\u1ed5 bi\u1ebfn' : 'T\u1ed1t';
  return <span className={`${color} text-xs font-bold`} title={title}>{stars}</span>;
}

function VoiceRow({ voice, selected, previewingVoiceId, onPreview, onSelect }: { voice: TtsVoice; selected: boolean; previewingVoiceId: string | null; onPreview: (id: string) => void; onSelect: (id: string) => void }) {
  return <div
    className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-colors ${selected ? 'border-violet-500/60 bg-violet-500/15' : 'border-white/10 bg-slate-950/40 hover:border-white/20'}`}
    onClick={() => onSelect(voice.id)}
  >
    <div className="flex h-5 w-5 shrink-0 items-center justify-center">
      {selected ? <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-violet-400"><span className="h-2 w-2 rounded-full bg-violet-400"/></span> : <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-slate-600"/>}
    </div>
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-2">
        <RankBadge rank={voice.rank}/>
        <b className="text-sm">{voice.label}</b>
        <Pill tone={voice.gender === 'female' ? 'violet' : 'cyan'}>{voice.gender === 'female' ? 'N\u1eef' : 'Nam'}</Pill>
        {voice.best_for && <Pill tone="cyan">{voice.best_for}</Pill>}
        {selected && <Pill tone="green">\u0110ang d\u00f9ng</Pill>}
      </div>
      <p className="mt-1 text-xs text-slate-400">{voice.description}</p>
    </div>
    <button
      className="btn-mini shrink-0"
      disabled={previewingVoiceId === voice.id}
      onClick={e => { e.stopPropagation(); onPreview(voice.id); }}
    >
      {previewingVoiceId === voice.id ? <Loader2 size={14} className="animate-spin"/> : <Play size={14}/>}
      {'Nghe th\u1eed'}
    </button>
  </div>;
}

export function TtsPanel({ renderOptions, onRenderOptionsChange }: { renderOptions: RenderOptions; onRenderOptionsChange: (value: RenderOptions) => void }) {
  const [ttsStatus, setTtsStatus] = useState<{ status: string; message: string } | null>(null);
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);
  const [previewingVoiceId, setPreviewingVoiceId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    void fetchTtsStatus().then(setTtsStatus).catch(() => setTtsStatus({ status: 'error', message: 'Không kiểm tra được trạng thái TTS.' }));
    void fetchTtsVoices().then(data => setTtsVoices(data.voices)).catch(() => setTtsVoices([]));
  }, []);

  useEffect(() => {
    if (previewUrl && audioRef.current) {
      audioRef.current.src = previewUrl;
      audioRef.current.play().catch(() => {});
    }
  }, [previewUrl]);

  const updateOptions = (patch: Partial<RenderOptions>) => onRenderOptionsChange({ ...renderOptions, ...patch });

  async function handlePreviewVoice(voiceId: string) {
    setPreviewingVoiceId(voiceId);
    setPreviewUrl(`/api/tts/prebuilt-preview/${voiceId}`);
    setPreviewingVoiceId(null);
  }

  const voiceGroups = [
    { label: 'Tiếng Việt', code: 'vi', localePrefix: 'vi-' },
    { label: 'Tiếng Anh (Mỹ)', code: 'en', localePrefix: 'en-US' },
    { label: 'Tiếng Đức', code: 'de', localePrefix: 'de-' },
    { label: 'Tiếng Nhật', code: 'ja', localePrefix: 'ja-' },
    { label: 'Tiếng Tây Ban Nha (Mexico)', code: 'es', localePrefix: 'es-MX' },
    { label: 'Tiếng Hàn', code: 'ko', localePrefix: 'ko-' },
  ];

  return <div className="space-y-6">
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionTitle icon={Volume2} title="Giọng đọc" desc="Cấu hình giọng đọc cho video"/>
        </div>
        {ttsStatus && <Pill tone={ttsStatus.status === 'ready' ? 'green' : 'yellow'}>{ttsStatus.status === 'ready' ? 'Sẵn sàng' : 'TTS chưa cài'}</Pill>}
      </div>
      {ttsStatus && <p className="mb-4 text-sm text-slate-400">{ttsStatus.message}</p>}

      <div className="grid gap-4">
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
          <h4 className="mb-3 font-bold">Trạng thái</h4>
          <div className="flex items-center gap-3">
            <select className="select-ghost flex-1" value={renderOptions.tts_mode} onChange={e => updateOptions({ tts_mode: e.target.value as RenderOptions['tts_mode'] })}>
              <option value="none">Tắt TTS</option>
              <option value="voiceover">Bật giọng đọc theo phụ đề</option>
            </select>
          </div>
        </div>

        {renderOptions.tts_mode === 'voiceover' && ttsStatus?.status !== 'ready' && <p className="mb-3 text-xs text-red-400">Edge TTS chưa cài — vui lòng cài dependencies backend trước khi render.</p>}

        {renderOptions.tts_mode === 'voiceover' && <>
          <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
            <h4 className="mb-3 font-bold">Chọn giọng đọc</h4>

            {/* Auto row */}
            <div
              className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-colors ${renderOptions.tts_voice_id === 'auto' ? 'border-violet-500/60 bg-violet-500/15' : 'border-white/10 bg-slate-950/40 hover:border-white/20'}`}
              onClick={() => updateOptions({ tts_voice_id: 'auto' as RenderOptions['tts_voice_id'] })}
            >
              <div className="flex h-5 w-5 shrink-0 items-center justify-center">
                {renderOptions.tts_voice_id === 'auto' ? <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-violet-400"><span className="h-2 w-2 rounded-full bg-violet-400"/></span> : <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-slate-600"/>}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <b className="text-sm">{'M\u1eb7c \u0111\u1ecbnh'}</b>
                </div>
                <p className="mt-1 text-xs text-slate-400">{'Kh\u00f4ng ch\u1ecdn \u2014 h\u1ec7 th\u1ed1ng t\u1ef1 ch\u1ecdn gi\u1ecdng ph\u00f9 h\u1ee3p v\u1edbi n\u1ed9i dung'}</p>
              </div>
            </div>

            <div className="mt-3 space-y-4">
              {voiceGroups.map(group => {
                const voices = ttsVoices.filter(v => v.languages?.includes(group.code) || v.locale?.startsWith(group.localePrefix));
                if (voices.length === 0) return null;
                return <div key={group.code}>
                  <h5 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">{group.label}</h5>
                  <div className="space-y-2">
                    {voices.map(voice => <VoiceRow key={voice.id} voice={voice} selected={renderOptions.tts_voice_id === voice.id} previewingVoiceId={previewingVoiceId} onPreview={handlePreviewVoice} onSelect={id => updateOptions({ tts_voice_id: id as RenderOptions['tts_voice_id'] })}/>)}
                  </div>
                </div>;
              })}
            </div>
          </div>

          <audio ref={audioRef} hidden/>

          <div className="grid gap-3 md:grid-cols-1">
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <h4 className="mb-3 font-bold">Âm lượng & Mix</h4>
              <div className="grid gap-3">
                <div><label className="label">Âm lượng giọng đọc ({Math.round(renderOptions.voiceover_volume * 100)}%)</label><input type="range" min="0" max="2" step="0.05" value={renderOptions.voiceover_volume} onChange={e => updateOptions({ voiceover_volume: Number(e.target.value) })}/></div>
                <div><label className="label">Âm lượng audio gốc ({Math.round(renderOptions.original_audio_volume * 100)}%)</label><input type="range" min="0" max="1" step="0.05" value={renderOptions.original_audio_volume} onChange={e => updateOptions({ original_audio_volume: Number(e.target.value) })}/></div>
                <div><label className="label">Chế độ audio gốc</label><select className="select-ghost" value={renderOptions.original_audio_mode} onChange={e => updateOptions({ original_audio_mode: e.target.value as RenderOptions['original_audio_mode'] })}><option value="lower_fixed">Giảm âm lượng gốc</option><option value="mute">Tắt audio gốc</option></select></div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <button className="flex w-full items-center justify-between gap-2 text-left font-bold" onClick={() => setShowAdvanced(!showAdvanced)}>
              Cấu hình nâng cao
              <span className="text-slate-400">{showAdvanced ? '▲' : '▼'}</span>
            </button>
            {showAdvanced && <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div><label className="label">Cách khớp thời lượng</label><select className="select-ghost" value={renderOptions.tts_fit_policy} onChange={e => updateOptions({ tts_fit_policy: e.target.value as RenderOptions['tts_fit_policy'] })}><option value="segment_uniform">Phân bổ đều theo từng đoạn</option></select></div>
              <div><label className="label">Tốc độ tối đa ({renderOptions.tts_max_speed.toFixed(2)}x)</label><input type="range" min="0.5" max="2.5" step="0.05" value={renderOptions.tts_max_speed} onChange={e => updateOptions({ tts_max_speed: Number(e.target.value) })}/></div>
              <div><label className="label">Ký tự tối đa mỗi đoạn</label><input className="input" type="number" min="50" max="500" value={renderOptions.tts_max_chars} onChange={e => updateOptions({ tts_max_chars: Number(e.target.value) })}/></div>
            </div>}
          </div>
        </>}
      </div>
    </Card>
  </div>;
}
