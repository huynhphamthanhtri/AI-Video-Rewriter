from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


SRT_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}$")
CLIP_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}$")


class MessageResponse(BaseModel):
    message: str


class UploadCookiesResponse(BaseModel):
    message: str
    cookies_file_path: str


def ensure_srt_timestamp(value: str) -> str:
    if not SRT_TIME_RE.match(value):
        raise ValueError("Sai định dạng timestamp SRT, cần HH:MM:SS,mmm")
    return value


def ensure_clip_timestamp(value: str) -> str:
    if not CLIP_TIME_RE.match(value):
        raise ValueError("Sai định dạng timestamp clip, cần HH:MM:SS.mmm")
    return value


class TimestampedSrtModel(BaseModel):
    start: str
    end: str

    _validate_start = field_validator("start")(ensure_srt_timestamp)
    _validate_end = field_validator("end")(ensure_srt_timestamp)


class TimestampedClipModel(BaseModel):
    start: str
    end: str

    _validate_start = field_validator("start")(ensure_clip_timestamp)
    _validate_end = field_validator("end")(ensure_clip_timestamp)
