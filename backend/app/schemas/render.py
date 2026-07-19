from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import TimestampedSrtModel, ensure_clip_timestamp


MAX_SEGMENT_DURATION_DELTA_SECONDS = 2.0
VerticalMode = Literal["none", "blur_fit", "center_crop"]
RenderQuality = Literal["fast", "balanced", "high"]
OutputResolution = Literal["auto", "720p", "1080p"]
SubtitleMode = Literal["burn", "srt_only", "none"]
RenderStability = Literal["fast", "stable", "max_quality"]
VideoEncoderMode = Literal["auto", "cpu", "nvenc", "qsv", "amf"]
SegmentFps = Literal["auto", "30", "60"]
BlurMode = Literal["none", "review"]
TtsMode = Literal["none", "voiceover"]
TtsEngine = Literal["edge_tts"]
TtsEmotion = Literal["natural", "storytelling"]
TtsFitPolicy = Literal["hybrid", "segment_uniform", "extend_video", "speed_up_voice"]

TtsPersona = Literal["neutral", "sports_commentator", "drama_storyteller", "news_anchor", "funny_reviewer", "podcast_host"]
TtsVoiceRegion = Literal["auto", "vi_north", "vi_south"]
TtsVoiceGender = Literal["auto", "female", "male"]
TtsVoiceId = Literal["auto", "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "en-US-JennyNeural", "en-US-GuyNeural",
                      "de-DE-KatjaNeural", "de-DE-ConradNeural", "ja-JP-NanamiNeural", "ja-JP-KeitaNeural",
                      "es-MX-DaliaNeural", "es-MX-JorgeNeural", "ko-KR-SunHiNeural", "ko-KR-InJoonNeural"]
TtsVoiceMode = Literal["preset"]
OriginalAudioMode = Literal["lower_fixed", "mute"]
TitleMode = Literal["none", "auto", "custom"]
TitleStyle = Literal["yellow_highlight", "dark_badge", "clean_white", "breaking_yellow"]
TitleFontSize = Literal["auto", "small", "medium", "large"]
TitlePosition = Literal["top", "upper_third", "center", "bottom"]
TitleTextAlign = Literal["left", "center", "right"]
TitleShowDuration = Literal["full", "intro_only"]
TitleBadgeMode = Literal["none", "auto", "custom"]
SubtitleStyle = Literal["default", "shorts_bold", "documentary", "minimal", "news", "high_contrast"]
SubtitleFontSize = Literal["auto", "small", "medium", "large"]
SubtitlePosition = Literal["bottom", "center", "top"]
SubtitleTextAlign = Literal["center", "left"]
ArtifactRetention = Literal["smart", "keep_all"]
CleanupTarget = Literal["temp", "outputs", "all"]


def clip_timestamp_to_seconds(value: str) -> float:
    ensure_clip_timestamp(value)
    hms, ms = value.split(".")
    h, m, s = [int(x) for x in hms.split(":")]
    return float((((h * 60) + m) * 60) + s) + (int(ms) / 1000)


def srt_timestamp_to_seconds(value: str) -> float:
    hms, ms = value.split(",")
    h, m, s = [int(x) for x in hms.split(":")]
    return float((((h * 60) + m) * 60) + s) + (int(ms) / 1000)


def seconds_to_clip_timestamp(value: float) -> str:
    safe_value = max(0.0, value)
    total_ms = int(round(safe_value * 1000))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def seconds_to_srt_timestamp(value: float) -> str:
    safe_value = max(0.0, value)
    total_ms = int(round(safe_value * 1000))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


class MetadataSchema(BaseModel):
    video_title: str
    rewrite_style: str
    target_audience: str
    tone: str
    target_duration: str
    target_language: str = ""
    target_market: str = ""
    localization_level: str = ""
    adaptation_mode: str = ""
    narrator_persona: str = ""
    hashtags: list[str] = []


class RewriteScriptSchema(BaseModel):
    full_text: str


class SourceSchema(BaseModel):
    source_id: str = Field(min_length=1)
    youtube_url: str | None = None
    local_video_path: str | None = None
    label: str = ""


class SrtItemSchema(TimestampedSrtModel):
    index: int = Field(ge=1)
    text: str
    tts_text: str | None = None


MAX_FREEZE_FRAME_SECONDS = 3.0


class VideoSegmentSchema(BaseModel):
    segment_id: int = Field(ge=1)
    order: int = Field(ge=1)
    source_id: str | None = None
    source_start: str
    source_end: str
    subtitle_start: int = Field(ge=1)
    subtitle_end: int = Field(ge=1)
    scene_description: str
    freeze_frame_duration: float | None = None

    @model_validator(mode="after")
    def validate_segment_range(self) -> "VideoSegmentSchema":
        if clip_timestamp_to_seconds(self.source_start) >= clip_timestamp_to_seconds(self.source_end):
            raise ValueError(f"Segment #{self.segment_id} có source_start phải nhỏ hơn source_end.")
        if self.subtitle_start > self.subtitle_end:
            raise ValueError(f"Segment #{self.segment_id} có subtitle_start lớn hơn subtitle_end.")
        return self

    @property
    def duration_seconds(self) -> float:
        return clip_timestamp_to_seconds(self.source_end) - clip_timestamp_to_seconds(self.source_start)


class SegmentPlanItem(BaseModel):
    segment_id: int
    scene_duration: float
    natural_voice_duration: float
    required_duration: float
    extend_seconds: float
    decision: str
    source_id: str
    source_remaining_seconds: float
    speed_factor: float = 1.0
    video_speed_factor: float = 1.0
    freeze_duration: float | None = None
    warning: str = ""
    overrun_seconds: float = 0.0
    duration_delta_seconds: float = 0.0
    balance_ratio: float | None = None
    cue_natural_durations: dict[int, float] = Field(default_factory=dict)


class GeminiPayloadSchema(BaseModel):
    metadata: MetadataSchema
    sources: list[SourceSchema] = Field(default_factory=list)
    rewrite_script: RewriteScriptSchema
    srt: list[SrtItemSchema]
    video_segments: list[VideoSegmentSchema]

    @model_validator(mode="after")
    def validate_cross_refs(self) -> "GeminiPayloadSchema":
        srt_indexes = [item.index for item in self.srt]
        if len(srt_indexes) != len(set(srt_indexes)):
            raise ValueError("Danh sách srt có index bị trùng nhau.")

        for item in self.srt:
            lines = item.text.split("\n")
            new_lines: list[str] = []
            for line in lines:
                if len(line) > 80:
                    split_at = line.rfind(" ", 0, 80)
                    if split_at > 0:
                        new_lines.append(line[:split_at])
                        new_lines.append(line[split_at + 1:])
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            if len(new_lines) > 3:
                raise ValueError(
                    f"SRT #{item.index} có {len(new_lines)} dòng (tối đa 3) sau khi tự động chia. "
                    f"Cần chia nhỏ thành nhiều SRT item."
                )
            if new_lines != lines:
                item.text = "\n".join(new_lines)

        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Danh sách sources có source_id bị trùng nhau.")
        source_id_set = set(source_ids)

        segment_ids = [segment.segment_id for segment in self.video_segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("Danh sách video_segments có segment_id bị trùng nhau.")

        segment_orders = [segment.order for segment in self.video_segments]
        if len(segment_orders) != len(set(segment_orders)):
            raise ValueError("Danh sách video_segments có order bị trùng nhau.")

        srt_by_index = {item.index: item for item in self.srt}
        for segment in self.video_segments:
            if self.sources and not segment.source_id:
                raise ValueError(f"Segment #{segment.segment_id} thiếu source_id khi JSON có nhiều nguồn.")
            if segment.source_id and self.sources and segment.source_id not in source_id_set:
                raise ValueError(f"Segment #{segment.segment_id} tham chiếu source_id không tồn tại: {segment.source_id}.")

            if segment.subtitle_start not in srt_by_index or segment.subtitle_end not in srt_by_index:
                raise ValueError(
                    f"Segment #{segment.segment_id} đang tham chiếu subtitle không tồn tại trong danh sách SRT."
                )

            subtitle_duration = (
                srt_timestamp_to_seconds(srt_by_index[segment.subtitle_end].end)
                - srt_timestamp_to_seconds(srt_by_index[segment.subtitle_start].start)
            )
            video_duration = segment.duration_seconds
            if abs(video_duration - subtitle_duration) > MAX_SEGMENT_DURATION_DELTA_SECONDS:
                raise ValueError(
                    f"Segment #{segment.segment_id} lệch timing: video={video_duration:.1f}s, "
                    f"subtitle={subtitle_duration:.1f}s, diff={abs(video_duration - subtitle_duration):.1f}s "
                    f"(giới hạn {MAX_SEGMENT_DURATION_DELTA_SECONDS:.0f}s). "
                    f"Auto-fix không thể đồng bộ đoạn này; hãy kiểm tra source_start/source_end hoặc chia nhỏ segment."
                )

        return self


class ValidateJsonRequest(BaseModel):
    payload: Any


class ValidateJsonResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str] = Field(default_factory=list)
    fixed_payload: dict | None = None


class RenderOptions(BaseModel):
    vertical_mode: VerticalMode = "none"
    render_quality: RenderQuality = "balanced"
    output_resolution: OutputResolution = "auto"
    render_stability: RenderStability = "stable"
    video_encoder: VideoEncoderMode = "auto"
    segment_fps: SegmentFps = "60"
    blur_mode: BlurMode = "none"
    tts_mode: TtsMode = "none"
    tts_engine: TtsEngine = "edge_tts"
    tts_persona: TtsPersona = "neutral"
    tts_voice_region: TtsVoiceRegion = "auto"
    tts_voice_gender: TtsVoiceGender = "female"
    tts_voice_id: TtsVoiceId = "auto"
    tts_voice_mode: TtsVoiceMode = "preset"
    tts_clone_voice_id: str = ""
    tts_emotion: TtsEmotion = "natural"
    tts_fit_policy: TtsFitPolicy = "hybrid"
    tts_max_speed: float = Field(default=1.5, ge=1.0, le=2.0)
    tts_temperature: float = Field(default=0.4, ge=0.1, le=1.2)
    tts_top_k: int = Field(default=50, ge=1, le=200)
    tts_max_chars: int = Field(default=256, ge=80, le=600)
    tts_apply_watermark: bool = True
    original_audio_mode: OriginalAudioMode = "lower_fixed"
    original_audio_volume: float = Field(default=0.3, ge=0, le=1)
    voiceover_volume: float = Field(default=1.0, ge=0, le=2)
    title_mode: TitleMode = "auto"
    title_text: str = ""
    title_style: TitleStyle = "yellow_highlight"
    title_font_size: TitleFontSize = "auto"
    title_max_lines: int = Field(default=2, ge=1, le=3)
    title_chars_per_line: int = Field(default=34, ge=16, le=60)
    title_position: TitlePosition = "top"
    title_text_align: TitleTextAlign = "center"
    title_show_duration: TitleShowDuration = "full"
    title_intro_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    title_badge_mode: TitleBadgeMode = "none"
    title_badge_text: str = ""
    title_header_height: int = Field(default=0, ge=0, le=360)
    title_safe_margin: int = Field(default=0, ge=0, le=240)
    subtitle_style: SubtitleStyle = "default"
    subtitle_font_size: SubtitleFontSize = "auto"
    subtitle_position: SubtitlePosition = "bottom"
    subtitle_text_align: SubtitleTextAlign = "center"
    subtitle_max_chars_per_line: int = Field(default=40, ge=20, le=80)
    subtitle_outline: bool = True
    subtitle_shadow: bool = False
    subtitle_box: bool = True
    domain: str = "general"
    artifact_retention: ArtifactRetention = "smart"
    video_speed: float = Field(default=1.0, ge=1.0, le=1.5)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_tts_options(cls, value: Any) -> Any:
        if isinstance(value, dict):
            data = dict(value)
            if data.get("tts_engine") == "vieneu_turbo":
                data["tts_engine"] = "edge_tts"
            if data.get("tts_voice_mode") == "clone":
                data["tts_voice_mode"] = "preset"
                data["tts_clone_voice_id"] = ""
            legacy_voice_ids = {
                "ly", "ngoc", "tuyen", "binh", "doan", "vinh", "mai_anh_tai",
                "co_gai_hoat_ngon", "thanh_nien_tu_tin", "duyen", "rachel", "jessica",
                "matilda", "liam", "brian", "james", "jessie", "serena", "adam", "eddie",
            }
            if data.get("tts_voice_id") in legacy_voice_ids:
                data["tts_voice_id"] = "auto"
            return data
        return value


class BlurKeyframe(BaseModel):
    time: float = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    strength: int = Field(default=12, ge=1, le=30)


class BlurRegion(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    keyframes: list[BlurKeyframe] = Field(min_length=1)
    interpolate: bool = False


class BlurUploadResponse(BaseModel):
    message: str
    video_path: str
    preview_url: str
    width: int | None = None
    height: int | None = None
    duration_seconds: str | None = None


class BlurRenderRequest(BaseModel):
    video_path: str
    regions: list[BlurRegion] = Field(default_factory=list)


class BlurRenderResponse(BaseModel):
    message: str
    final_video_path: str
    output_dir: str
    video_encoder: str | None = None
    video_encoder_label: str | None = None
    video_encoder_codec: str | None = None
    output_codec: str | None = None
    output_fps: str | None = None
    output_resolution_actual: str | None = None
    output_duration_seconds: str | None = None
    output_file_size_bytes: str | None = None


class BlurDecisionRequest(BaseModel):
    regions: list[BlurRegion] = Field(default_factory=list)


class TtsVoicePreviewRequest(BaseModel):
    voice_id: str
    text: str = "Xin chào, đây là giọng đọc thử từ Edge TTS."


class TtsVoicePreviewResponse(BaseModel):
    message: str
    preview_audio_path: str


class TtsGenerateRequest(BaseModel):
    voice_id: str
    text: str
    format: Literal["wav", "mp3"] = "wav"


class TtsGenerateResponse(BaseModel):
    message: str
    audio_path: str
    audio_url: str
    filename: str
    output_dir: str


class TtsClonePreviewRequest(BaseModel):
    text: str = "Edge TTS không hỗ trợ clone voice."
    render_options: RenderOptions = Field(default_factory=RenderOptions)


class TtsCloneVoiceResponse(BaseModel):
    id: str
    name: str
    reference_audio_path: str
    created_at: float
    duration_seconds: str | None = None


class TtsCloneUploadResponse(BaseModel):
    message: str
    voice: TtsCloneVoiceResponse


class TtsClonePreviewResponse(BaseModel):
    message: str
    preview_audio_path: str


class SavedCookiesResponse(BaseModel):
    available: bool
    cookies_file_path: str | None = None
    uploaded_at: float | None = None
    file_size: int | None = None


class RenderPreferencesRequest(BaseModel):
    subtitle_mode: SubtitleMode = "burn"
    render_done_bell: bool = True
    render_options: RenderOptions = Field(default_factory=RenderOptions)


class RenderPreferencesResponse(RenderPreferencesRequest):
    updated_at: float | None = None


class RenderRequest(BaseModel):
    youtube_url: str | None = None
    local_video_path: str | None = None
    ytdlp_cookies_file: str | None = None
    ytdlp_cookies_from_browser: str | None = None
    user_data_dir: str | None = None
    gemini_json: Any
    burn_subtitle: bool = True
    subtitle_mode: SubtitleMode | None = None
    render_options: RenderOptions = Field(default_factory=RenderOptions)
    output_dir_name: str | None = None
    output_dir_path: str | None = None

    @property
    def effective_subtitle_mode(self) -> SubtitleMode:
        if self.subtitle_mode:
            return self.subtitle_mode
        return "burn" if self.burn_subtitle else "none"

    @model_validator(mode="after")
    def ensure_video_source(self) -> "RenderRequest":
        has_json_sources = bool(self.gemini_json.get("sources")) if isinstance(self.gemini_json, dict) else False
        if self.effective_subtitle_mode != "srt_only" and not self.youtube_url and not self.local_video_path and not has_json_sources:
            raise ValueError("Bạn phải cung cấp Youtube URL hoặc đường dẫn video local.")
        if self.ytdlp_cookies_file and self.ytdlp_cookies_from_browser:
            raise ValueError("Chỉ được dùng một trong hai: ytdlp_cookies_file hoặc ytdlp_cookies_from_browser.")
        return self


class RenderResponse(BaseModel):
    message: str
    final_video_path: str
    final_subtitle_path: str
    render_plan_path: str
    output_dir: str
    video_encoder: str | None = None
    video_encoder_label: str | None = None
    video_encoder_codec: str | None = None
    source_codec: str | None = None
    source_fps: str | None = None
    source_resolution: str | None = None
    output_codec: str | None = None
    output_fps: str | None = None
    output_resolution_actual: str | None = None
    output_duration_seconds: str | None = None
    output_file_size_bytes: str | None = None
    voiceover_path: str | None = None
    tts_plan_path: str | None = None
    tts_warning_count: str | None = None


class RenderJobStartResponse(BaseModel):
    job_id: str
    status: str
    message: str


class RenderJobStatusResponse(BaseModel):
    job_id: str
    status: str
    step: str
    message: str
    progress: int = Field(default=0, ge=0, le=100)
    total_segments: int | None = None
    completed_segments: int = Field(default=0, ge=0)
    started_at: float | None = None
    updated_at: float | None = None
    elapsed_seconds: float | None = None
    estimated_total_seconds: float | None = None
    remaining_seconds: float | None = None
    result: dict[str, str] | None = None
    errors: list[str] = Field(default_factory=list)


class OpenFolderRequest(BaseModel):
    path: str


class StorageStatsResponse(BaseModel):
    outputs_size_bytes: int
    temp_size_bytes: int
    outputs_count: int
    temp_count: int


class StorageCleanupRequest(BaseModel):
    target: CleanupTarget = "temp"
    older_than_hours: int = Field(default=24, ge=0)
    dry_run: bool = True


class StorageCleanupResponse(BaseModel):
    target: CleanupTarget
    dry_run: bool
    matched_count: int
    deleted_count: int
    freed_bytes: int
    items: list[str] = Field(default_factory=list)


class TitleLinePreview(BaseModel):
    text: str
    x_px: int
    y_px: int
    font_size: int
    font_color: str
    width_px: int
    height_px: int
    has_background: bool
    background_color: str | None = None


class TitleBadgePreview(BaseModel):
    text: str
    x_px: int
    y_px: int
    font_size: int
    font_color: str
    width_px: int
    height_px: int
    has_background: bool
    background_color: str | None = None


class TitleLayoutPreviewRequest(BaseModel):
    render_options: RenderOptions
    video_width: int
    video_height: int
    metadata: dict | None = None


class TitleLayoutPreviewResponse(BaseModel):
    lines: list[TitleLinePreview]
    badge: TitleBadgePreview | None = None
    header_drawbox: list[str] | None = None
    safe_margin_px: int
    header_height_px: int
