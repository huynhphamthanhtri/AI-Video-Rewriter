import { useEffect, useRef, useState } from 'react';
import { Download, FolderOpen, Loader2, Play, Volume2 } from 'lucide-react';
import { toast } from 'sonner';
import { fetchTtsStatus, fetchTtsVoices, generateStandaloneTts, openOutputFolder, ttsAudioUrl } from '../api';
import type { TtsVoice } from '../types';
import { Card, Pill, SectionTitle } from './common';

const LOCALE_LABELS: Record<string, string> = {
  'vi-VN': 'Tiếng Việt',
  'en-US': 'English US',
  'de-DE': 'Deutsch',
  'ja-JP': '日本語',
  'es-MX': 'Español México',
  'ko-KR': '한국어',
};

const LOCALE_ORDER = ['vi-VN', 'en-US', 'ko-KR', 'ja-JP', 'de-DE', 'es-MX'];

const WARN_CHARS = 5000;
const MAX_CHARS = 10000;

type TtsStudioSessionState = {
  selectedLocale: string;
  selectedVoiceId: string;
  text: string;
  format: 'wav' | 'mp3';
  audioUrl: string | null;
  downloadUrl: string | null;
  filename: string | null;
  outputDir: string | null;
};

const ttsStudioSessionState: TtsStudioSessionState = {
  selectedLocale: 'vi-VN',
  selectedVoiceId: '',
  text: '',
  format: 'wav',
  audioUrl: null,
  downloadUrl: null,
  filename: null,
  outputDir: null,
};

export function TtsStudioPanel() {
  const [ttsStatus, setTtsStatus] = useState<{ status: string; message: string } | null>(null);
  const [voices, setVoices] = useState<TtsVoice[]>([]);
  const [selectedLocale, setSelectedLocaleState] = useState(ttsStudioSessionState.selectedLocale);
  const [selectedVoiceId, setSelectedVoiceIdState] = useState(ttsStudioSessionState.selectedVoiceId);
  const [text, setTextState] = useState(ttsStudioSessionState.text);
  const [format, setFormatState] = useState<'wav' | 'mp3'>(ttsStudioSessionState.format);
  const [generating, setGenerating] = useState(false);
  const [audioUrl, setAudioUrlState] = useState<string | null>(ttsStudioSessionState.audioUrl);
  const [downloadUrl, setDownloadUrlState] = useState<string | null>(ttsStudioSessionState.downloadUrl);
  const [filename, setFilenameState] = useState<string | null>(ttsStudioSessionState.filename);
  const [outputDir, setOutputDirState] = useState<string | null>(ttsStudioSessionState.outputDir);
  const [previewingVoiceId, setPreviewingVoiceId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  function syncSession() {
    Object.assign(ttsStudioSessionState, {
      selectedLocale, selectedVoiceId, text, format, audioUrl, downloadUrl, filename, outputDir,
    });
  }

  function setSelectedLocale(value: string) {
    setSelectedLocaleState(value);
    setAudioUrlState(null);
    setDownloadUrlState(null);
    setFilenameState(null);
    setOutputDirState(null);
  }

  function setSelectedVoiceId(value: string) {
    setSelectedVoiceIdState(value);
    setAudioUrlState(null);
    setDownloadUrlState(null);
    setFilenameState(null);
    setOutputDirState(null);
  }

  function setText(value: string) {
    setTextState(value);
    if (audioUrl) {
      setAudioUrlState(null);
      setDownloadUrlState(null);
      setFilenameState(null);
      setOutputDirState(null);
    }
  }

  function setFormat(value: 'wav' | 'mp3') {
    setFormatState(value);
    setAudioUrlState(null);
    setDownloadUrlState(null);
    setFilenameState(null);
    setOutputDirState(null);
  }

  useEffect(() => {
    Object.assign(ttsStudioSessionState, {
      selectedLocale, selectedVoiceId, text, format, audioUrl, downloadUrl, filename, outputDir,
    });
  }, [selectedLocale, selectedVoiceId, text, format, audioUrl, downloadUrl, filename, outputDir]);

  useEffect(() => {
    void fetchTtsStatus().then(setTtsStatus).catch(() => setTtsStatus({ status: 'error', message: 'Không kiểm tra được trạng thái TTS.' }));
    void fetchTtsVoices().then(data => {
      setVoices(data.voices);
      const sortedLocales = LOCALE_ORDER.filter(l => data.voices.some(v => v.locale === l));
      const firstLocale = sortedLocales[0] ?? data.voices[0]?.locale ?? 'vi-VN';
      if (!ttsStudioSessionState.selectedVoiceId) {
        setSelectedLocale(firstLocale);
        const firstInLocale = data.voices
          .filter(v => v.locale === firstLocale)
          .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));
        if (firstInLocale.length > 0) setSelectedVoiceId(firstInLocale[0].id);
      }
    }).catch(() => setVoices([]));
  }, []);

  const filteredVoices = voices
    .filter(v => v.locale === selectedLocale)
    .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));

  const localesInData = LOCALE_ORDER.filter(l => voices.some(v => v.locale === l));

  const canGenerate = ttsStatus?.status === 'ready' && selectedVoiceId && text.trim().length > 0 && !generating;

  const estimatedSeconds = Math.max(3, Math.ceil(text.trim().length / 120));

  async function handleGenerate() {
    if (!canGenerate) return;
    setGenerating(true);
    setAudioUrlState(null);
    setDownloadUrlState(null);
    setFilenameState(null);
    setOutputDirState(null);
    try {
      const res = await generateStandaloneTts({ voice_id: selectedVoiceId, text: text.trim(), format });
      const previewUrl = ttsAudioUrl(res.audio_path);
      const dlUrl = ttsAudioUrl(res.audio_path, true);
      setAudioUrlState(previewUrl);
      setDownloadUrlState(dlUrl);
      setFilenameState(res.filename);
      setOutputDirState(res.output_dir);
      toast.success(res.message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Tạo TTS thất bại.');
    } finally {
      setGenerating(false);
    }
  }

  function handleSelectVoice(id: string) {
    setSelectedVoiceId(id);
  }

  function handleLocaleChange(locale: string) {
    setSelectedLocale(locale);
    setSelectedVoiceId('');
    const firstInLocale = voices
      .filter(v => v.locale === locale)
      .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));
    if (firstInLocale.length > 0) setSelectedVoiceId(firstInLocale[0].id);
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <SectionTitle icon={Volume2} title="Text to Speech" desc="Tạo file giọng đọc WAV/MP3 từ text bằng Edge TTS" />
          </div>
          {ttsStatus && (
            <Pill tone={ttsStatus.status === 'ready' ? 'green' : 'yellow'}>
              {ttsStatus.status === 'ready' ? 'TTS ready' : 'TTS chưa cài'}
            </Pill>
          )}
        </div>
        {ttsStatus && <p className="mb-4 text-sm text-slate-400">{ttsStatus.message}</p>}

        <div className="grid gap-4">
          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <h4 className="mb-3 font-bold">Ngôn ngữ</h4>
            <div className="flex flex-wrap gap-2">
              {localesInData.map(locale => (
                <button
                  key={locale}
                  className={selectedLocale === locale ? 'btn-primary' : 'btn-secondary'}
                  onClick={() => handleLocaleChange(locale)}
                >
                  {LOCALE_LABELS[locale] ?? locale}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
            <h4 className="mb-3 font-bold">Chọn giọng đọc</h4>
            {filteredVoices.length === 0 ? (
              <p className="text-sm text-slate-400">Không có voice cho ngôn ngữ này.</p>
            ) : (
              <div className="space-y-2">
                {filteredVoices.map(voice => (
                  <div
                    key={voice.id}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-colors ${selectedVoiceId === voice.id ? 'border-violet-500/60 bg-violet-500/15' : 'border-white/10 bg-slate-950/40 hover:border-white/20'}`}
                    onClick={() => handleSelectVoice(voice.id)}
                  >
                    <div className="flex h-5 w-5 shrink-0 items-center justify-center">
                      {selectedVoiceId === voice.id ? (
                        <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-violet-400"><span className="h-2 w-2 rounded-full bg-violet-400" /></span>
                      ) : (
                        <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-slate-600" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <b className="text-sm">{voice.label}</b>
                        <Pill tone={voice.gender === 'female' ? 'violet' : 'cyan'}>{voice.gender === 'female' ? 'Nữ' : 'Nam'}</Pill>
                        {voice.best_for && <Pill tone="cyan">{voice.best_for}</Pill>}
                        {selectedVoiceId === voice.id && <Pill tone="green">Đã chọn</Pill>}
                      </div>
                      <p className="mt-1 text-xs text-slate-400">{voice.description}</p>
                    </div>
                    <button
                      className="btn-mini shrink-0"
                      disabled={previewingVoiceId === voice.id}
                      onClick={e => { e.stopPropagation(); setPreviewingVoiceId(voice.id); setAudioUrlState(`/api/tts/prebuilt-preview/${voice.id}`); setDownloadUrlState(null); setFilenameState(null); setOutputDirState(null); setPreviewingVoiceId(null); }}
                    >
                      {previewingVoiceId === voice.id ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                      {'Nghe thử'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <h4 className="mb-3 font-bold">Nội dung</h4>
            <textarea
              className="textarea min-h-[120px]"
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Nhập nội dung cần chuyển thành giọng đọc..."
            />
            <div className="mt-2 flex items-center justify-between text-xs">
              <span className="text-slate-400">{text.length} / {MAX_CHARS} ký tự</span>
              {text.length > WARN_CHARS && (
                <span className="text-amber-400">Vượt quá {WARN_CHARS} ký tự, có thể gây chậm.</span>
              )}
              {text.length > MAX_CHARS && (
                <span className="text-red-400">Vượt quá giới hạn {MAX_CHARS} ký tự.</span>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <h4 className="mb-3 font-bold">Định dạng output</h4>
            <div className="flex gap-2">
              <button className={format === 'wav' ? 'btn-primary' : 'btn-secondary'} onClick={() => setFormat('wav')}>WAV</button>
              <button className={format === 'mp3' ? 'btn-primary' : 'btn-secondary'} onClick={() => setFormat('mp3')}>MP3</button>
            </div>
          </div>

          {generating && (
            <div className="rounded-2xl border border-violet-500/20 bg-violet-500/10 p-4">
              <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full w-1/3 animate-pulse rounded-full bg-violet-400" style={{ width: '40%' }} />
              </div>
              <p className="mt-2 text-sm text-slate-300">
                Đang tạo audio... ước tính khoảng {estimatedSeconds} giây
              </p>
              {text.trim().length > WARN_CHARS && (
                <p className="mt-1 text-xs text-amber-400">Text dài, có thể mất 1-2 phút tùy mạng.</p>
              )}
            </div>
          )}

          <button
            className="btn-primary w-full"
            disabled={!canGenerate}
            onClick={handleGenerate}
          >
            {generating ? <><Loader2 size={18} className="animate-spin" /> Đang tạo...</> : <>Tạo file TTS</>}
          </button>

          {audioUrl && (
            <div className="rounded-2xl border border-green-500/20 bg-green-500/10 p-4">
              <h4 className="mb-3 font-bold text-green-300">Tạo thành công</h4>
              <audio ref={audioRef} controls src={audioUrl} className="w-full" />

              <div className="mt-3 rounded-xl bg-slate-950/40 p-3 text-xs text-slate-400">
                <div><b>File:</b> {filename}</div>
                {outputDir && <div className="break-all"><b>Thư mục tạm:</b> {outputDir}</div>}
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                <a
                  href={downloadUrl ?? audioUrl}
                  download={filename ?? 'tts_output.wav'}
                  className="btn-primary inline-flex items-center gap-2"
                >
                  <Download size={16} /> Tải file
                </a>
                {outputDir && (
                  <button
                    className="btn-secondary inline-flex items-center gap-2"
                    onClick={async () => {
                      try {
                        await openOutputFolder(outputDir);
                        toast.success('Đã mở thư mục tạm.');
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Không mở được thư mục.');
                      }
                    }}
                  >
                    <FolderOpen size={16} /> Mở thư mục tạm
                  </button>
                )}
              </div>

              <p className="mt-2 text-xs text-slate-500">
                Bấm Tải file để trình duyệt mở hộp thoại lưu file hoặc lưu vào Downloads tùy cấu hình.
              </p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
