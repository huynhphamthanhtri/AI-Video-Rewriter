from __future__ import annotations

import re
from pathlib import Path

from app.schemas.render import RenderOptions


def _srt_time_to_centiseconds(value: str) -> str:
    hms, frac = value.replace(",", ".").rsplit(".", 1)
    h, m, s = hms.split(":")
    cs = str(int(frac[:3].ljust(3, "0")) // 10).zfill(2)
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs}"


def _parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\n\s*\n", text)
    items: list[dict] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not time_line:
            continue
        parts = time_line.split("-->")
        if len(parts) != 2:
            continue
        items.append({
            "index": len(items) + 1,
            "start": _srt_time_to_centiseconds(parts[0].strip()),
            "end": _srt_time_to_centiseconds(parts[1].strip()),
            "text": "\n".join(lines[2:] if "-->" in lines[1] else lines[1:]),
        })
    return items


class SubtitleStyler:
    STYLE_PRESETS: dict[str, dict] = {
        "default": {"Fontname": "Arial", "Fontsize": 48, "Outline": 2, "Shadow": 1, "BorderStyle": 1, "BackColour": "&H99000000"},
        "shorts_bold": {"Fontname": "Arial", "Fontsize": 52, "Outline": 4, "Shadow": 2, "BorderStyle": 1, "BackColour": "&H99000000"},
        "documentary": {"Fontname": "Tahoma", "Fontsize": 42, "Outline": 2, "Shadow": 1, "BorderStyle": 1, "BackColour": "&H99000000"},
        "minimal": {"Fontname": "Arial", "Fontsize": 36, "Outline": 0, "Shadow": 0, "BorderStyle": 0, "BackColour": "&H00000000"},
        "news": {"Fontname": "Tahoma", "Fontsize": 46, "Outline": 2, "Shadow": 1, "BorderStyle": 1, "BackColour": "&H99000000"},
        "high_contrast": {"Fontname": "Arial", "Fontsize": 50, "Outline": 5, "Shadow": 3, "BorderStyle": 1, "BackColour": "&HBB000000"},
    }
    STYLE_METADATA: dict[str, dict[str, str]] = {
        "default": {"label": "Default", "description": "Arial 48px, viền nhẹ, hộp nền"},
        "shorts_bold": {"label": "Shorts Bold", "description": "Arial 52px, viền dày, nổi bật"},
        "documentary": {"label": "Documentary", "description": "Tahoma 42px, thanh lịch"},
        "minimal": {"label": "Minimal", "description": "Arial 36px, không viền, không hộp"},
        "news": {"label": "News", "description": "Tahoma 46px, sạch sẽ, giống phát thanh viên"},
        "high_contrast": {"label": "High Contrast", "description": "Arial 50px, viền dày, tương phản cao"},
    }
    ALIGNMENT_MAP: dict[str, int] = {"bottom": 2, "center": 8, "top": 5}

    def _resolve_style(self, options: RenderOptions) -> dict:
        preset = dict(self.STYLE_PRESETS.get(options.subtitle_style, self.STYLE_PRESETS["default"]))
        if options.subtitle_font_size != "auto":
            size_map = {"small": 36, "medium": 48, "large": 56}
            preset["Fontsize"] = size_map.get(options.subtitle_font_size, 48)
        if not options.subtitle_outline:
            preset["Outline"] = 0
        if not options.subtitle_shadow:
            preset["Shadow"] = 0
        base_align = self.ALIGNMENT_MAP.get(options.subtitle_position, 2)
        if options.subtitle_text_align == "left":
            base_align = base_align - 1
        preset["Alignment"] = base_align
        if not options.subtitle_box:
            preset["BackColour"] = "&H00000000"
            if preset["BorderStyle"] == 1:
                preset["BorderStyle"] = 1
        return preset

    def srt_to_ass(self, srt_path: Path, ass_path: Path, options: RenderOptions) -> Path:
        items = _parse_srt(srt_path)
        style = self._resolve_style(options)
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{style['Fontname']},{style['Fontsize']},&H00FFFFFF,&H000000FF,&H00000000,{style['BackColour']},-1,0,0,0,100,100,0,0,{style['BorderStyle']},{style['Outline']},{style['Shadow']},{style['Alignment']},40,40,120,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        for item in items:
            text = item["text"].replace("\n", "\\N")
            lines.append(f"Dialogue: 0,{item['start']},{item['end']},Default,,0,0,0,,{text}")
        ass_path.write_text("\n".join(lines), encoding="utf-8")
        return ass_path
