from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.schemas.render import RenderOptions


_CJK_RANGES = (
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Extension A
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x1100, 0x11FF),   # Hangul Jamo
    (0x3130, 0x318F),   # Hangul Compatibility Jamo
)


def _contains_cjk(text: str) -> bool:
    return any(
        lo <= ord(ch) <= hi
        for ch in text
        for lo, hi in _CJK_RANGES
    )


_HANGUL_RANGES = (
    (0xAC00, 0xD7AF),
    (0x1100, 0x11FF),
    (0x3130, 0x318F),
)


def _contains_hangul(text: str) -> bool:
    return any(
        lo <= ord(ch) <= hi
        for ch in text
        for lo, hi in _HANGUL_RANGES
    )


@dataclass
class TitleLineLayout:
    text: str
    font_size: int
    font_color: str
    x_expr: str
    y_expr: str
    has_background: bool
    background_color: Optional[str] = None


@dataclass
class TitleBadgeLayout:
    text: str
    font_size: int
    font_color: str
    x_expr: str
    y_expr: str
    has_background: bool
    background_color: Optional[str] = None


@dataclass
class TitleLayoutResult:
    lines: list[TitleLineLayout]
    badge: Optional[TitleBadgeLayout]
    header_drawbox: Optional[list[str]]
    safe_margin_px: int
    header_height_px: int


_BACKGROUND_COLORS = {
    "yellow_highlight": "black@0.55",
    "dark_badge": "black@0.75",
    "clean_white": "black@0.25",
    "breaking_yellow": "black@0.70",
}

_FONT_SIZE_MAP = {
    "small": 38,
    "medium": 48,
    "large": 60,
}


def _title_font_path(text: str = "") -> Path | None:
    candidates: list[Path]
    if _contains_hangul(text):
        candidates = [
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/malgunbd.ttf"),
            Path("C:/Windows/Fonts/malgunsl.ttf"),
            Path("C:/Windows/Fonts/NotoSansKR-Regular.otf"),
            Path("C:/Windows/Fonts/NotoSansKR-Bold.otf"),
            Path("C:/Windows/Fonts/NotoSansCJKkr-Regular.otf"),
            Path("C:/Windows/Fonts/NotoSansCJK-Regular.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttf"),
            Path("C:/Windows/Fonts/YuGothR.ttc"),
            Path("C:/Windows/Fonts/YuGothM.ttc"),
            Path("C:/Windows/Fonts/YuGothB.ttc"),
            Path("C:/Windows/Fonts/msgothic.ttc"),
            Path("C:/Windows/Fonts/yumin.ttf"),
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msjh.ttc"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
    elif _contains_cjk(text):
        candidates = [
            Path("C:/Windows/Fonts/meiryo.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttf"),
            Path("C:/Windows/Fonts/YuGothR.ttc"),
            Path("C:/Windows/Fonts/YuGothM.ttc"),
            Path("C:/Windows/Fonts/YuGothB.ttc"),
            Path("C:/Windows/Fonts/msgothic.ttc"),
            Path("C:/Windows/Fonts/yumin.ttf"),
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msjh.ttc"),
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
    else:
        candidates = [
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/meiryo.ttc"),
            Path("C:/Windows/Fonts/meiryo.ttf"),
            Path("C:/Windows/Fonts/YuGothR.ttc"),
            Path("C:/Windows/Fonts/YuGothM.ttc"),
            Path("C:/Windows/Fonts/YuGothB.ttc"),
            Path("C:/Windows/Fonts/msgothic.ttc"),
            Path("C:/Windows/Fonts/yumin.ttf"),
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/msjh.ttc"),
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _display_width(value: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1 for ch in value)


def _trim_to_width(value: str, max_width: int) -> str:
    result = ""
    width = 0
    for ch in value:
        ch_width = 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
        if width + ch_width > max_width:
            break
        result += ch
        width += ch_width
    return result.rstrip()


def _wrap_title(value: str, max_lines: int = 2, chars_per_line: int = 34) -> str:
    original = value.strip()
    if not original:
        return ""
    lines: list[str] = []
    current = ""
    max_lines = max(1, min(3, int(max_lines)))
    max_chars = max(16, min(60, int(chars_per_line)))
    tokens = original.split() if " " in original else list(original)
    separator = " " if " " in original else ""
    for word in tokens:
        next_line = f"{current}{separator}{word}".strip()
        if _display_width(next_line) > max_chars and current:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
        else:
            current = next_line
    if current and len(lines) < max_lines:
        lines.append(current)
    text = "\n".join(lines[:max_lines])
    if len(text.replace("\n", separator)) < len(original) and not text.endswith("..."):
        text = _trim_to_width(text, max(0, _display_width(text) - 3)).rstrip() + "..."
    return text


def resolve_badge_text(options: RenderOptions, metadata: Optional[dict] = None) -> str:
    if options.title_badge_mode == "none":
        return ""
    if options.title_badge_mode == "custom":
        return options.title_badge_text.strip().upper()[:32]
    if not metadata:
        return ""
    haystack = " ".join([
        metadata.get("video_title", ""),
        metadata.get("rewrite_style", ""),
        metadata.get("tone", ""),
        metadata.get("narrator_persona", ""),
    ]).lower()
    if any(token in haystack for token in ["bodycam", "police", "cops", "cop", "officer"]):
        return "BODYCAM"
    if any(token in haystack for token in ["case", "crime", "documentary", "detective"]):
        return "CASE FILE"
    return "TRUE CRIME"


def resolve_title_text(options: RenderOptions, metadata: Optional[dict] = None) -> str:
    raw = options.title_text if options.title_mode == "custom" else (metadata or {}).get("video_title", "")
    return _wrap_title(raw, options.title_max_lines, options.title_chars_per_line)


def _safe_margin_expr(options: RenderOptions) -> str:
    if options.title_safe_margin > 0:
        return str(options.title_safe_margin)
    return "max(42\\,w*0.035)"


def _safe_margin_px(options: RenderOptions, video_width: int) -> int:
    if options.title_safe_margin > 0:
        return options.title_safe_margin
    return max(42, int(video_width * 0.035))


def _header_height_expr(options: RenderOptions) -> str:
    if options.title_header_height > 0:
        return str(options.title_header_height)
    return "max(118\\,ih*0.105)"


def _header_height_px(options: RenderOptions, video_height: int) -> int:
    if options.title_header_height > 0:
        return options.title_header_height
    return max(118, int(video_height * 0.105))


def _title_block_y_expr(options: RenderOptions, total_text_h: int) -> str:
    if options.title_style == "breaking_yellow" and options.title_position == "top":
        return "max(28\\,h*0.034)"
    if options.title_position == "upper_third":
        return "h*0.16"
    if options.title_position == "center":
        return f"(h-{total_text_h})/2"
    if options.title_position == "bottom":
        return f"h-{total_text_h}-h*0.08"
    return "max(42\\,h*0.045)"


def _title_block_y_px(options: RenderOptions, video_height: int, total_text_h: int) -> int:
    if options.title_style == "breaking_yellow" and options.title_position == "top":
        return max(28, int(video_height * 0.034))
    if options.title_position == "upper_third":
        return int(video_height * 0.16)
    if options.title_position == "center":
        return (video_height - total_text_h) // 2
    if options.title_position == "bottom":
        return video_height - total_text_h - int(video_height * 0.08)
    return max(42, int(video_height * 0.045))


def _title_x_expr(options: RenderOptions, has_badge: bool) -> str:
    margin = _safe_margin_expr(options)
    if options.title_text_align == "left":
        if options.title_style == "breaking_yellow" and has_badge:
            return f"{margin}+max(160\\,w*0.14)"
        return margin
    if options.title_text_align == "right":
        return f"w-text_w-{margin}"
    return "(w-text_w)/2"


def _title_x_px(options: RenderOptions, video_width: int, has_badge: bool, estimated_width: int) -> int:
    margin = _safe_margin_px(options, video_width)
    if options.title_text_align == "left":
        if options.title_style == "breaking_yellow" and has_badge:
            return margin + max(160, int(video_width * 0.14))
        return margin
    if options.title_text_align == "right":
        return video_width - estimated_width - margin
    return (video_width - estimated_width) // 2


def compute_title_layout(
    options: RenderOptions,
    video_width: int,
    video_height: int,
    metadata: Optional[dict] = None,
) -> TitleLayoutResult:
    title_text = resolve_title_text(options, metadata)
    badge_text = resolve_badge_text(options, metadata)

    if not title_text:
        return TitleLayoutResult(
            lines=[],
            badge=None,
            header_drawbox=None,
            safe_margin_px=_safe_margin_px(options, video_width),
            header_height_px=_header_height_px(options, video_height),
        )

    font_size = _FONT_SIZE_MAP.get(options.title_font_size, 52)
    font_color = "0xFFD319" if options.title_style in {"yellow_highlight", "breaking_yellow"} else "white"
    has_bg = True
    bg_color = _BACKGROUND_COLORS.get(options.title_style)

    safe_margin_px = _safe_margin_px(options, video_width)
    header_height_px = _header_height_px(options, video_height)

    lines = title_text.split("\n")
    interline_gap = 8
    total_text_h = len(lines) * font_size + (len(lines) - 1) * interline_gap

    base_y_expr = _title_block_y_expr(options, total_text_h)

    has_badge = bool(badge_text)
    x_expr = _title_x_expr(options, has_badge)

    title_lines: list[TitleLineLayout] = []
    for i, line in enumerate(lines):
        line_y = f"{base_y_expr}+{i * (font_size + interline_gap)}" if i > 0 else base_y_expr
        title_lines.append(TitleLineLayout(
            text=line,
            font_size=font_size,
            font_color=font_color,
            x_expr=x_expr,
            y_expr=line_y,
            has_background=has_bg,
            background_color=bg_color,
        ))

    badge_layout: Optional[TitleBadgeLayout] = None
    if has_badge:
        badge_font_size = max(24, font_size - 18)
        badge_x = _safe_margin_expr(options)
        badge_y = "max(30\\,h*0.036)"
        badge_layout = TitleBadgeLayout(
            text=badge_text,
            font_size=badge_font_size,
            font_color="white",
            x_expr=badge_x,
            y_expr=badge_y,
            has_background=True,
            background_color="0xB91C1C@0.95",
        )

    header_drawbox: Optional[list[str]] = None
    if options.title_style == "breaking_yellow" and options.title_position == "top":
        hh = _header_height_expr(options)
        enable_part = _title_enable_expr(options)
        header_drawbox = [
            f"drawbox=x=0:y=0:w=iw:h={hh}:color=black@0.82:t=fill{enable_part}",
            f"drawbox=x=0:y=0:w=iw:h=max(9\\,ih*0.009):color=0xB91C1C@0.95:t=fill{enable_part}",
            f"drawbox=x=0:y={hh}-max(6\\,ih*0.006):w=iw:h=max(6\\,ih*0.006):color=0xFFD319@0.95:t=fill{enable_part}",
        ]

    return TitleLayoutResult(
        lines=title_lines,
        badge=badge_layout,
        header_drawbox=header_drawbox,
        safe_margin_px=safe_margin_px,
        header_height_px=header_height_px,
    )


def _title_enable_expr(options: RenderOptions) -> str:
    if options.title_show_duration == "intro_only":
        return f":enable='between(t\\,0\\,{options.title_intro_seconds:.2f})'"
    return ""


def _eval_expr(expr: str, w: int, h: int, text_w: int, text_h: int) -> int:
    subbed = expr.replace("w", str(w)).replace("h", str(h))
    subbed = subbed.replace("text_w", str(text_w)).replace("text_h", str(text_h))
    subbed = subbed.replace("ih", str(h)).replace("iw", str(w))

    subbed = re.sub(
        r"max\((\d+)\s*,\s*h\*([\d.]+)\)",
        lambda m: str(max(int(m.group(1)), int(h * float(m.group(2))))),
        subbed,
    )
    subbed = re.sub(
        r"max\((\d+)\s*,\s*w\*([\d.]+)\)",
        lambda m: str(max(int(m.group(1)), int(w * float(m.group(2))))),
        subbed,
    )
    subbed = re.sub(
        r"max\(([^,]+),([^)]+)\)",
        lambda m: str(max(float(m.group(1)), float(m.group(2)))),
        subbed,
    )

    subbed = subbed.replace("\\,", ",")
    try:
        return int(eval(subbed))
    except (SyntaxError, NameError, TypeError, ZeroDivisionError):
        return 0


def compute_title_preview(
    options: RenderOptions,
    video_width: int,
    video_height: int,
    metadata: Optional[dict] = None,
) -> dict:
    layout = compute_title_layout(options, video_width, video_height, metadata)

    if not layout.lines:
        return {
            "lines": [],
            "badge": None,
            "header_drawbox": None,
            "safe_margin_px": layout.safe_margin_px,
            "header_height_px": layout.header_height_px,
        }

    interline_gap = 8

    def line_px(line: TitleLineLayout, index: int, total_text_h: int) -> dict:
        estimated_width = max(16, int(len(line.text) * line.font_size * 0.6))
        estimated_height = line.font_size + 12

        y_px = _title_block_y_px(options, video_height, total_text_h)
        if index > 0:
            y_px += index * (line.font_size + interline_gap)

        has_badge = layout.badge is not None
        x_px = _title_x_px(options, video_width, has_badge, estimated_width)

        return {
            "text": line.text,
            "x_px": x_px,
            "y_px": y_px,
            "font_size": line.font_size,
            "font_color": line.font_color,
            "width_px": estimated_width,
            "height_px": estimated_height,
            "has_background": line.has_background,
            "background_color": line.background_color,
        }

    total_text_h = len(layout.lines) * layout.lines[0].font_size + (len(layout.lines) - 1) * interline_gap

    badge_result = None
    if layout.badge:
        badge_estimated_w = max(16, int(len(layout.badge.text) * layout.badge.font_size * 0.7))
        badge_estimated_h = layout.badge.font_size + 12
        badge_y = max(30, int(video_height * 0.036))
        badge_x = _safe_margin_px(options, video_width)
        badge_result = {
            "text": layout.badge.text,
            "x_px": badge_x,
            "y_px": badge_y,
            "font_size": layout.badge.font_size,
            "font_color": layout.badge.font_color,
            "width_px": badge_estimated_w,
            "height_px": badge_estimated_h,
            "has_background": True,
            "background_color": "0xB91C1C@0.95",
        }

    return {
        "lines": [line_px(l, i, total_text_h) for i, l in enumerate(layout.lines)],
        "badge": badge_result,
        "header_drawbox": layout.header_drawbox,
        "safe_margin_px": layout.safe_margin_px,
        "header_height_px": layout.header_height_px,
    }
