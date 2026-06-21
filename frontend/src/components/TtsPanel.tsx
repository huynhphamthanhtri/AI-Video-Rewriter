import { useEffect, useState } from 'react';
import { Loader2, Play, Volume2 } from 'lucide-react';
import { fetchTtsStatus, fetchTtsVoicePreview, fetchTtsVoices, ttsAudioUrl } from '../api';
import type { RenderOptions, TtsVoice } from '../types';
import { Card, Pill, SectionTitle } from './common';
import { TtsCloneManager } from './TtsCloneManager';

export function TtsPanel({ renderOptions, onRenderOptionsChange }: { renderOptions: RenderOptions; onRenderOptionsChange: (value: RenderOptions) => void }) {
  const [ttsStatus, setTtsStatus] = useState<{ status: string; message: string } | null>(null);
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);
  const [previewingVoiceId, setPreviewingVoiceId] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    void fetchTtsStatus().then(setTtsStatus).catch(() => setTtsStatus({ status: 'error', message: 'Không kiểm tra được trạng thái TTS.' }));
    void fetchTtsVoices().then(data => setTtsVoices(data.voices)).catch(() => setTtsVoices([]));
  }, []);

  const updateOptions = (patch: Partial<RenderOptions>) => onRenderOptionsChange({ ...renderOptions, ...patch });

  async function handlePreviewVoice(voiceId: string) {
    setPreviewingVoiceId(voiceId);
    setPreviewPath(null);
    try {
      const result = await fetchTtsVoicePreview(voiceId, 'Xin chào, đây là giọng đọc thử từ VieNeu Turbo.');
      setPreviewPath(result.preview_audio_path);
    } catch {
      setPreviewPath(null);
    } finally {
      setPreviewingVoiceId(null);
    }
  }

  return <div className="space-y-6">
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionTitle icon={Volume2} title="Voiceover / TTS" desc="Cấu hình giọng đọc cho video"/>
        </div>
        {ttsStatus && <Pill tone={ttsStatus.status === 'ready' ? 'green' : 'yellow'}>{ttsStatus.status === 'ready' ? 'TTS ready' : 'TTS chưa cài'}</Pill>}
      </div>
      {ttsStatus && <p className="mb-4 text-sm text-slate-400">{ttsStatus.message}</p>}

      <div className="grid gap-4">
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
          <h4 className="mb-3 font-bold">Trạng thái</h4>
          <div className="flex items-center gap-3">
            <select className="select-ghost flex-1" value={renderOptions.tts_mode} onChange={e => updateOptions({ tts_mode: e.target.value as RenderOptions['tts_mode'] })}>
              <option value="none">Tắt TTS</option>
              <option value="voiceover">Bật VieNeu Turbo đọc theo srt[]</option>
            </select>
          </div>
        </div>

        {renderOptions.tts_mode === 'voiceover' && <>
          <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
            <h4 className="mb-3 font-bold">Chọn giọng đọc</h4>
            <div className="grid gap-3 md:grid-cols-3">
              <div><label className="label">Vùng miền</label><select className="select-ghost" value={renderOptions.tts_voice_region} onChange={e => updateOptions({ tts_voice_region: e.target.value as RenderOptions['tts_voice_region'] })}><option value="auto">Auto</option><option value="vi_north">Miền Bắc</option><option value="vi_south">Miền Nam</option></select></div>
              <div><label className="label">Giới tính</label><select className="select-ghost" value={renderOptions.tts_voice_gender} onChange={e => updateOptions({ tts_voice_gender: e.target.value as RenderOptions['tts_voice_gender'] })}><option value="auto">Auto</option><option value="female">Nữ</option><option value="male">Nam</option></select></div>
              <div><label className="label">Ngôn ngữ</label><select className="select-ghost" value={renderOptions.tts_language} onChange={e => updateOptions({ tts_language: e.target.value as RenderOptions['tts_language'] })}><option value="auto">Auto detect</option><option value="vi">Tiếng Việt</option><option value="en">English</option><option value="vi_en">Việt-Anh mixed</option></select></div>
            </div>

            <div className="mt-4 space-y-2">
              {ttsVoices.map(voice => <div key={voice.id} className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-950/40 p-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <b className="text-sm">{voice.label}</b>
                    <Pill tone={voice.gender === 'female' ? 'violet' : 'cyan'}>{voice.gender === 'female' ? 'Nữ' : 'Nam'}</Pill>
                    <Pill tone="cyan">{voice.region === 'vi_north' ? 'Bắc' : 'Nam'}</Pill>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{voice.description}</p>
                </div>
                <button
                  className="btn-mini"
                  disabled={previewingVoiceId === voice.id}
                  onClick={() => handlePreviewVoice(voice.id)}
                >
                  {previewingVoiceId === voice.id ? <Loader2 size={14} className="animate-spin"/> : <Play size={14}/>}
                  Nghe thử
                </button>
              </div>)}
            </div>

            {previewPath && <audio className="mt-3 w-full" controls src={ttsAudioUrl(previewPath)}/>}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <h4 className="mb-3 font-bold">Phong cách</h4>
              <div className="grid gap-3">
                <div><label className="label">Persona</label><select className="select-ghost" value={renderOptions.tts_persona} onChange={e => { updateOptions({ tts_persona: e.target.value as RenderOptions['tts_persona'], tts_voice_id: 'auto' }); }}><option value="neutral">Người kể trung tính</option><option value="sports_commentator">MC thể thao</option><option value="drama_storyteller">Kể chuyện drama</option><option value="news_anchor">Phóng viên tin tức</option><option value="funny_reviewer">Reviewer hài hước</option><option value="podcast_host">Podcast host</option></select></div>
                <div><label className="label">Emotion</label><select className="select-ghost" value={renderOptions.tts_emotion} onChange={e => updateOptions({ tts_emotion: e.target.value as RenderOptions['tts_emotion'] })}><option value="natural">Natural</option><option value="storytelling">Storytelling</option></select></div>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <h4 className="mb-3 font-bold">Âm lượng & Mix</h4>
              <div className="grid gap-3">
                <div><label className="label">Voiceover volume ({Math.round(renderOptions.voiceover_volume * 100)}%)</label><input type="range" min="0" max="2" step="0.05" value={renderOptions.voiceover_volume} onChange={e => updateOptions({ voiceover_volume: Number(e.target.value) })}/></div>
                <div><label className="label">Original audio volume ({Math.round(renderOptions.original_audio_volume * 100)}%)</label><input type="range" min="0" max="1" step="0.05" value={renderOptions.original_audio_volume} onChange={e => updateOptions({ original_audio_volume: Number(e.target.value) })}/></div>
                <div><label className="label">Original audio mode</label><select className="select-ghost" value={renderOptions.original_audio_mode} onChange={e => updateOptions({ original_audio_mode: e.target.value as RenderOptions['original_audio_mode'] })}><option value="lower_fixed">Giảm âm lượng gốc</option><option value="mute">Tắt audio gốc</option></select></div>
              </div>
            </div>
          </div>

          <TtsCloneManager renderOptions={renderOptions} onRenderOptionsChange={onRenderOptionsChange}/>

          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <button className="flex w-full items-center justify-between gap-2 text-left font-bold" onClick={() => setShowAdvanced(!showAdvanced)}>
              Cấu hình nâng cao
              <span className="text-slate-400">{showAdvanced ? '▲' : '▼'}</span>
            </button>
            {showAdvanced && <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div><label className="label">Fit policy</label><select className="select-ghost" value={renderOptions.tts_fit_policy} onChange={e => updateOptions({ tts_fit_policy: e.target.value as RenderOptions['tts_fit_policy'] })}><option value="segment_uniform">Segment uniform</option></select></div>
              <div><label className="label">Max speed ({renderOptions.tts_max_speed.toFixed(2)}x)</label><input type="range" min="0.5" max="2.5" step="0.05" value={renderOptions.tts_max_speed} onChange={e => updateOptions({ tts_max_speed: Number(e.target.value) })}/></div>
              <div><label className="label">Temperature ({renderOptions.tts_temperature.toFixed(2)})</label><input type="range" min="0" max="1" step="0.05" value={renderOptions.tts_temperature} onChange={e => updateOptions({ tts_temperature: Number(e.target.value) })}/></div>
              <div><label className="label">Top-K ({renderOptions.tts_top_k})</label><input type="range" min="1" max="100" step="1" value={renderOptions.tts_top_k} onChange={e => updateOptions({ tts_top_k: Number(e.target.value) })}/></div>
              <div><label className="label">Max chars per segment</label><input className="input" type="number" min="50" max="500" value={renderOptions.tts_max_chars} onChange={e => updateOptions({ tts_max_chars: Number(e.target.value) })}/></div>
              <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm"><input type="checkbox" checked={renderOptions.tts_apply_watermark} onChange={e => updateOptions({ tts_apply_watermark: e.target.checked })}/>Apply watermark</label>
            </div>}
          </div>
        </>}
      </div>
    </Card>
  </div>;
}
