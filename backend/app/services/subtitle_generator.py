from __future__ import annotations

from pathlib import Path

import pysubs2

from app.schemas.render import GeminiPayloadSchema


def _srt_ms(value: str) -> int:
    hms, ms = value.split(",")
    h, m, s = [int(x) for x in hms.split(":")]
    return (((h * 60) + m) * 60 + s) * 1000 + int(ms)


class SubtitleGenerator:
    def generate(self, payload: GeminiPayloadSchema, output_path: Path) -> Path:
        subs = pysubs2.SSAFile()
        for item in payload.srt:
            subs.append(pysubs2.SSAEvent(start=_srt_ms(item.start), end=_srt_ms(item.end), text=item.text))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subs.save(str(output_path))
        return output_path
