import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Upload } from 'lucide-react';
import { deleteTtsClone, fetchTtsClones, previewTtsClone, ttsAudioUrl, uploadTtsClone } from '../api';
import type { RenderOptions, TtsCloneVoice } from '../types';
import { Pill } from './common';

export function TtsCloneManager({ renderOptions, onRenderOptionsChange }: { renderOptions: RenderOptions; onRenderOptionsChange: (value: RenderOptions) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [clones, setClones] = useState<TtsCloneVoice[]>([]);
  const [name, setName] = useState('My cloned voice');
  const [previewText, setPreviewText] = useState('Xin chào, đây là bản thử giọng clone bằng VieNeu Turbo.');
  const [previewPath, setPreviewPath] = useState('');
  const [busy, setBusy] = useState(false);
  const updateOptions = (patch: Partial<RenderOptions>) => onRenderOptionsChange({ ...renderOptions, ...patch });
  async function loadClones() {
    try { setClones((await fetchTtsClones()).voices); } catch { setClones([]); }
  }
  useEffect(() => { void loadClones(); }, []);
  async function upload(file: File) {
    try {
      setBusy(true);
      const result = await uploadTtsClone(file, name);
      toast.success('Clone giọng thành công');
      await loadClones();
      updateOptions({ tts_voice_mode: 'clone', tts_clone_voice_id: result.voice.id });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không clone giọng được');
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    if (!renderOptions.tts_clone_voice_id) return toast.error('Chọn cloned voice trước');
    try {
      setBusy(true);
      const result = await previewTtsClone(renderOptions.tts_clone_voice_id, previewText, renderOptions);
      setPreviewPath(result.preview_audio_path);
      toast.success('Đã tạo preview clone voice');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không preview được clone voice');
    } finally {
      setBusy(false);
    }
  }
  async function removeClone(id: string) {
    try {
      await deleteTtsClone(id);
      if (renderOptions.tts_clone_voice_id === id) updateOptions({ tts_voice_mode: 'preset', tts_clone_voice_id: '' });
      await loadClones();
      toast.success('Đã xóa cloned voice');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Không xóa được cloned voice');
    }
  }
  return <div className="rounded-2xl border border-fuchsia-500/20 bg-fuchsia-500/10 p-4"><input ref={fileRef} type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/aac,audio/flac,audio/ogg,.wav,.mp3,.m4a,.aac,.flac,.ogg" hidden onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.currentTarget.value = ''; }}/><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h4 className="font-bold">Clone giọng VieNeu Turbo</h4><Pill tone={renderOptions.tts_voice_mode === 'clone' ? 'violet' : 'cyan'}>{renderOptions.tts_voice_mode === 'clone' ? 'Đang dùng clone' : 'Đang dùng preset'}</Pill></div><p className="mb-3 text-xs text-slate-400">Chỉ clone giọng khi bạn có quyền sử dụng. Reference audio nên sạch, ít nhạc nền, dài 3-10 giây.</p><div className="grid gap-3"><div className="grid gap-3 md:grid-cols-2"><div><label className="label">Voice mode</label><select className="select-ghost" value={renderOptions.tts_voice_mode} onChange={e => updateOptions({ tts_voice_mode: e.target.value as RenderOptions['tts_voice_mode'] })}><option value="preset">Preset voice</option><option value="clone">Cloned voice</option></select></div><div><label className="label">Tên clone mới</label><input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="Tên cloned voice"/></div></div><div className="flex flex-wrap gap-2"><button className="btn-secondary" disabled={busy} onClick={() => fileRef.current?.click()}><Upload size={16}/>Upload reference audio</button><button className="btn-mini" onClick={loadClones}>Refresh clones</button></div>{clones.length > 0 && <div><label className="label">Chọn cloned voice</label><select className="select-ghost" value={renderOptions.tts_clone_voice_id} onChange={e => updateOptions({ tts_voice_mode: 'clone', tts_clone_voice_id: e.target.value })}><option value="">Chưa chọn</option>{clones.map(clone => <option key={clone.id} value={clone.id}>{clone.name} ({clone.duration_seconds ? `${Number(clone.duration_seconds).toFixed(1)}s` : 'audio'})</option>)}</select></div>}<div><label className="label">Preview text</label><textarea className="textarea min-h-[80px]" value={previewText} onChange={e => setPreviewText(e.target.value)}/></div><div className="flex flex-wrap gap-2"><button className="btn-primary" disabled={busy || !renderOptions.tts_clone_voice_id} onClick={preview}>Preview cloned voice</button>{renderOptions.tts_clone_voice_id && <button className="btn-mini danger" onClick={() => removeClone(renderOptions.tts_clone_voice_id)}>Xóa clone đang chọn</button>}</div>{previewPath && <audio className="w-full" controls src={ttsAudioUrl(previewPath)}/>}</div></div>;
}
