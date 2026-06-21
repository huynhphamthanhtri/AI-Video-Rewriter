# Kiến trúc

Hệ thống được chia thành các service độc lập: `PromptGenerator`, `JsonValidator`, `VideoDownloader`, `VideoCutter`, `VideoConcatenator`, `SubtitleGenerator`, `SubtitleBurner`, `RenderPipeline`, `PresetService`.

Kiến trúc cho phép thay thế lớp AI provider trong tương lai mà không ảnh hưởng pipeline dựng video.

## EDL / Shot-based editing

Video Rebuilder V2 dùng Edit Decision List thay cho thiết kế `clips[]` + `timeline[]` cũ.

### Payload chính

```json
{
  "metadata": {},
  "rewrite_script": { "full_text": "" },
  "srt": [
    { "index": 1, "start": "00:00:00,000", "end": "00:00:08,000", "text": "" }
  ],
  "video_segments": [
    {
      "segment_id": 1,
      "order": 1,
      "source_start": "00:00:05.000",
      "source_end": "00:00:13.000",
      "subtitle_start": 1,
      "subtitle_end": 1,
      "scene_description": "",
      "importance_score": 95
    }
  ]
}
```

### Luồng render

1. `JsonValidator` validate payload EDL.
2. Nếu lệch duration, `validate_with_auto_fix()` thử điều chỉnh `source_end` theo duration subtitle.
3. `SubtitleGenerator` sinh SRT từ `srt[]`.
4. `VideoCutter` cắt từng `video_segments[].source_start/source_end` thành `segment_{id}.mp4`.
5. `VideoConcatenator` ghép segment theo `order`.
6. `SubtitleBurner` burn subtitle nếu được bật.

### Validation rules

- `source_start < source_end`.
- `subtitle_start <= subtitle_end`.
- `subtitle_start/subtitle_end` phải tồn tại trong `srt[]`.
- `duration(video_segment)` phải gần bằng `duration(subtitle_range)`, sai số tối đa 2 giây.
