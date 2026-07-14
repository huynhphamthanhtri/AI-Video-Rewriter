from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class PromptGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    youtube_url: HttpUrl
    youtube_urls: list[HttpUrl] = Field(default_factory=list)
    source_mode: Literal["single", "multi"] = "single"
    preset_name: str | None = None
    rewrite_style: str = "Storytelling"
    target_audience: str = "Đại chúng"
    tone: str = "Thân thiện"
    target_duration: str = "3-5 phút"
    retention_mode: str = "Cao"
    hook_style: str = "Cảnh đắt giá"
    clip_strategy: str = "Giữ đầy đủ ngữ cảnh"
    reuse_level: str = "Trung bình"
    content_density: str = "Trung bình"
    target_language: str = "Tiếng Việt"
    target_market: str = "Việt Nam"
    localization_level: str = "medium"
    rename_characters: bool = True
    adapt_culture: bool = True
    adapt_currency: bool = True
    adapt_units: bool = True
    adapt_company_names: bool = True
    adaptation_mode: str = "localized"
    narrator_persona: str = "neutral_narrator"
    domain: str = "general"
    user_instruction: str = ""


class PromptGenerateResponse(BaseModel):
    prompt: str


PromptHealthLevel = Literal["excellent", "good", "risky", "weak"]


class PromptHealthDetail(BaseModel):
    factor: str
    label: str
    value: str
    impact: int
    reason: str


class PromptHealthResponse(BaseModel):
    score: int
    level: PromptHealthLevel
    warnings: list[str]
    strengths: list[str]
    details: list[PromptHealthDetail] = []


class PromptPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rewrite_style: str = "Storytelling"
    target_audience: str = "Đại chúng"
    tone: str = "Thân thiện"
    target_duration: str = "3-5 phút"
    retention_mode: str = "Cao"
    hook_style: str = "Cảnh đắt giá"
    clip_strategy: str = "Giữ đầy đủ ngữ cảnh"
    reuse_level: str = "Trung bình"
    content_density: str = "Trung bình"
    target_language: str = "Tiếng Việt"
    target_market: str = "Việt Nam"
    localization_level: str = "medium"
    rename_characters: bool = True
    adapt_culture: bool = True
    adapt_currency: bool = True
    adapt_units: bool = True
    adapt_company_names: bool = True
    adaptation_mode: str = "localized"
    narrator_persona: str = "neutral_narrator"
    user_instruction: str = ""


class PromptPreviewSection(BaseModel):
    title: str
    start: int
    end: int
    excerpt: str


class PromptPreviewResponse(BaseModel):
    preview_text: str
    full_length: int
    estimated_tokens: int
    sections: list[PromptPreviewSection]


class PromptRunCreate(BaseModel):
    prompt_text: str = ""
    form_data: dict = {}
    health_score: int | None = None
    health_level: str | None = None
    status: str = "success"
    error_message: str | None = None
    duration_ms: float | None = None


class PromptRunRead(BaseModel):
    id: str
    created_at: float
    status: str
    prompt_chars: int | None
    prompt_hash: str | None
    health_score: int | None
    health_level: str | None
    error_message: str | None
    duration_ms: float | None
    preset_name: str | None = None
    rewrite_style: str | None = None
    preset_schema_version: int | None = None
    prompt_template_version: int | None = None
    json_output_schema_version: int | None = None


class PromptRunStats(BaseModel):
    total_runs: int
    success_count: int
    error_count: int
    avg_health_score: float | None
    top_presets: list[dict] = []
    top_rewrite_styles: list[dict] = []
    daily_counts: list[dict] = []
    last_7d_count: int = 0
    prev_7d_count: int = 0


class PresetRecommendRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    youtube_urls: list[str] = []
    target_language: str = "Tiếng Việt"
    user_instruction: str = ""


class PresetRecommendResponse(BaseModel):
    recommendations: list[dict] = []


class GeminiAutoSubmitRequest(BaseModel):
    form_data: dict = {}
    render_options: dict = {}
    subtitle_mode: str = "burn"
    ytdlp_cookies_file: str | None = None
    ytdlp_cookies_from_browser: str | None = None
    local_video_path: str | None = None
    user_data_dir: str | None = None
    output_dir_name: str | None = None
    output_dir_path: str | None = None
    headless: bool = True
    gemini_thinking_mode: Literal["standard", "extended"] = "extended"
    gemini_analysis_mode: Literal["deep_analysis", "fast"] = "deep_analysis"
    gemini_dry_run: bool = False


class GeminiAutoSubmitResponse(BaseModel):
    task_id: str
    prompt_text: str


class GeminiAutoSubmitStatusResponse(BaseModel):
    task_id: str
    step: str
    status: str  # "running" | "done" | "error"
    message: str | None = None
    detail: dict | None = None
    result: dict | None = None
    error: str | None = None
