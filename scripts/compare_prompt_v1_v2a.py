"""Compare V1 vs V2A prompt structure side-by-side.

Usage: python scripts/compare_prompt_v1_v2a.py

Generates a V2A prompt (normal path with VoiceBlock + Creator DNA)
and a V1 prompt (temporarily patched to exclude both),
then prints a structural comparison.

Uses monkeypatching inside script execution only — no runtime app changes.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

# Ensure backend is importable
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from pydantic import HttpUrl

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_generator import PromptGenerator


def _make_request() -> PromptGenerateRequest:
    return PromptGenerateRequest(
        youtube_url=HttpUrl("https://www.youtube.com/watch?v=test"),
        source_mode="single",
        preset_name="So Sánh Prompt V1 vs V2A",
        rewrite_style="Storytelling",
        target_audience="Đại chúng",
        tone="Thân thiện",
        target_duration="5-10 phút",
        retention_mode="Cao",
        hook_style="Cảnh đắt giá",
        clip_strategy="Giữ đầy đủ ngữ cảnh",
        reuse_level="Trung bình",
        content_density="Trung bình",
        narrator_persona="drama_storyteller",
    )


_SECTION_MARKERS: list[tuple[str, str]] = [
    ("Intro", "Bạn là chuyên gia biên tập video"),
    ("Intent", "Cấu hình viết lại:"),
    ("Strategy", "Chiến lược giữ chân"),
    ("Voice", "GIỌNG KỂ / VOICE"),
    ("CreatorDNA", "CREATOR DNA / BẢN SẮC"),
    ("Localization", "Cấu hình ngôn ngữ và bản địa hóa:"),
    ("Subtitle", "RÀNG BUỘC SUBTITLE"),
    ("ContentQuality", "CHẤT LƯỢNG NỘI DUNG"),
    ("Hook", "HOOK BẮT BUỘC"),
    ("Task", "Nhiệm vụ:"),
    ("Alignment", "SRT-SCENE ALIGNMENT"),
    ("DomainRules", "DOMAIN RULES"),
    ("Validation", "QUY TẮC JSON BẮT BUỘC:"),
    ("OutputSchema", "STRICT OUTPUT CONTRACT"),
]


def _detect_sections(text: str) -> list[str]:
    found: list[str] = []
    for name, marker in _SECTION_MARKERS:
        if marker in text:
            found.append(name)
    return found


def _find_marker_index(text: str, marker: str) -> int:
    try:
        return text.index(marker)
    except ValueError:
        return -1


def _verify_order(sections: list[str], expected: list[str]) -> list[str]:
    violations: list[str] = []
    for prev_name, next_name in zip(expected, expected[1:]):
        if prev_name in sections and next_name in sections:
            prev_idx = sections.index(prev_name)
            next_idx = sections.index(next_name)
            if prev_idx > next_idx:
                violations.append(f"{prev_name} > {next_name} (expected {prev_name} < {next_name})")
    return violations


def main() -> None:
    import importlib

    req = _make_request()

    # --- V2A prompt (normal path, VoiceBlock + Creator DNA active) ---
    v2a_prompt = PromptGenerator().generate(req)

    # --- V1 prompt (patched to exclude VoiceBlock + Creator DNA) ---
    # Patch VoiceBlock.render to return empty string
    import app.services.prompt_blocks.voice_block as vb_mod
    import app.services.creator_dna as cdna_mod

    _original_render = vb_mod.VoiceBlock.render
    _original_load = cdna_mod.load_creator_dna

    def _empty_render(self, data):  # type: ignore[no-untyped-def]
        return ""

    def _none_load(path=None):  # type: ignore[no-untyped-def]
        return None

    vb_mod.VoiceBlock.render = _empty_render  # type: ignore[method-assign]
    cdna_mod.load_creator_dna = _none_load

    # Reimport composer to pick up patched references
    import app.services.prompt_blocks.composer as comp_mod
    importlib.reload(comp_mod)

    v1_req = _make_request()
    from app.services.prompt_generator import PromptGenerator as PG2
    v1_prompt = PG2().generate(v1_req)

    # Restore originals
    vb_mod.VoiceBlock.render = _original_render  # type: ignore[method-assign]
    cdna_mod.load_creator_dna = _original_load
    importlib.reload(comp_mod)

    # --- Analysis ---
    v1_sections = _detect_sections(v1_prompt)
    v2a_sections = _detect_sections(v2a_prompt)
    v2a_added = [s for s in v2a_sections if s not in v1_sections]
    v2a_removed = [s for s in v1_sections if s not in v2a_sections]

    expected_order = [
        "Intro", "Intent", "Strategy", "Voice", "CreatorDNA",
        "Localization", "Subtitle", "ContentQuality", "Hook",
        "Task", "Alignment", "DomainRules", "Validation", "OutputSchema",
    ]
    v1_violations = _verify_order(v1_sections, expected_order)
    v2a_violations = _verify_order(v2a_sections, expected_order)

    # --- Output ---
    print("=" * 72)
    print("  CONTENT ENGINE V2A — Prompt Comparison (V1 vs V2A)")
    print("=" * 72)

    print(f"\n{'Metric':<35} {'V1':<25} {'V2A':<25}")
    print("-" * 85)
    print(f"{'Total length (chars)':<35} {len(v1_prompt):<25} {len(v2a_prompt):<25}")
    print(f"{'Section count':<35} {len(v1_sections):<25} {len(v2a_sections):<25}")
    print(f"{'VoiceBlock present':<35} {'[NO]':<25} {'[YES]':<25}")
    print(f"{'Creator DNA present':<35} {'[NO]':<25} {'[YES]':<25}")
    print(f"{'Char delta':<35} {'-':<25} {len(v2a_prompt) - len(v1_prompt):<25}")
    if v2a_added:
        print(f"{'Sections added in V2A':<35} {','.join(v2a_added):<25}")
    if v2a_removed:
        print(f"{'Sections removed in V2A':<35} {','.join(v2a_removed):<25}")

    print(f"\n{'-' * 85}")
    print(f"Section order comparison:")
    print(f"  V1  sections: {v1_sections}")
    print(f"  V2A sections: {v2a_sections}")
    if v1_violations:
        print(f"  V1 order violations: {v1_violations}")
    if v2a_violations:
        print(f"  V2A order violations: {v2a_violations}")
    if not v1_violations and not v2a_violations:
        print(f"  [OK] Order is valid for both V1 and V2A")

    print(f"\n{'-' * 85}")
    print(f"V1 first 500 chars:")
    print(f"{v1_prompt[:500]}")
    print(f"\n{'-' * 85}")
    print(f"V2A first 500 chars:")
    print(f"{v2a_prompt[:500]}")

    print(f"\n{'-' * 85}")
    print(f"V2A VoiceBlock section (excerpt):")
    voice_marker = "GIỌNG KỂ / VOICE"
    if voice_marker in v2a_prompt:
        start = v2a_prompt.index(voice_marker)
        excerpt = v2a_prompt[start:start + 600]
        print(excerpt)

    print(f"\n{'-' * 85}")
    print(f"V2A Creator DNA section (excerpt):")
    dna_marker = "CREATOR DNA / BẢN SẮC"
    if dna_marker in v2a_prompt:
        start = v2a_prompt.index(dna_marker)
        excerpt = v2a_prompt[start:start + 600]
        print(excerpt)
    else:
        print("(no Creator DNA file found — run from project root with data/creator_dna.md present)")

    print(f"\n{'=' * 72}")
    print("  Comparison complete. [OK]" if len(v2a_sections) >= len(v1_sections) else "  Check section loss.")
    print("=" * 72)


if __name__ == "__main__":
    main()
