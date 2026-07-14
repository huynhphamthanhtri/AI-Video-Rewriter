import { z } from 'zod';

const srtTime = /^\d{2}:\d{2}:\d{2},\d{3}$/;
const clipTime = /^\d{2}:\d{2}:\d{2}\.\d{3}$/;

export const geminiEdlSchema = z.object({
  metadata: z.object({ video_title: z.string(), rewrite_style: z.string(), target_audience: z.string(), tone: z.string(), target_duration: z.string(), target_language: z.string().optional(), target_market: z.string().optional(), localization_level: z.string().optional(), adaptation_mode: z.string().optional(), narrator_persona: z.string().optional() }),
  sources: z.array(z.object({ source_id: z.string().min(1), youtube_url: z.string().nullable().optional(), local_video_path: z.string().nullable().optional(), label: z.string().optional() })).optional(),
  rewrite_script: z.object({ full_text: z.string() }),
  srt: z.array(z.object({ index: z.number().int().positive(), start: z.string().regex(srtTime), end: z.string().regex(srtTime), text: z.string(), tts_text: z.string().optional() })).min(1),
  video_segments: z.array(z.object({ segment_id: z.number().int().positive(), order: z.number().int().positive(), source_id: z.string().optional(), source_start: z.string().regex(clipTime), source_end: z.string().regex(clipTime), subtitle_start: z.number().int().positive(), subtitle_end: z.number().int().positive(), scene_description: z.string(), importance_score: z.number().min(0).max(100) })).min(1),
});
