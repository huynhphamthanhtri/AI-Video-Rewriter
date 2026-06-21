from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.schemas.render import BlurRegion, RenderOptions
from app.services.video_tools import probe_video_metadata, run_ffmpeg_with_encoder_fallback, safe_filename_prefix, video_encoder_args, audio_encoder_args, quality_for_stability


class BlurService:
    def apply_blur(self, input_path: Path, output_path: Path, regions: list[BlurRegion], options: RenderOptions | None = None) -> tuple[Path, dict[str, str]]:
        render_options = options or RenderOptions()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = probe_video_metadata(input_path)
        video_duration = float(metadata.get("duration_seconds") or 0)
        resolution = metadata.get("resolution", "")
        try:
            width_text, height_text = resolution.split("x")
            video_width = int(width_text)
            video_height = int(height_text)
        except ValueError:
            video_width = 1920
            video_height = 1080

        intervals = self._normalize_regions(regions, video_width, video_height, video_duration)
        if not intervals:
            import shutil
            shutil.copy2(input_path, output_path)
            return output_path, metadata

        quality = quality_for_stability(render_options)

        def build_cmd(profile):
            return [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(input_path.resolve()),
                "-filter_complex",
                self._filter_complex(intervals),
                "-map",
                f"[v{len(intervals)}]",
                "-map",
                "0:a?",
                *video_encoder_args(profile, quality),
                *audio_encoder_args(quality),
                "-movflags",
                "+faststart",
                str(output_path.resolve()),
            ]

        encoder = run_ffmpeg_with_encoder_fallback(build_cmd, "FFmpeg blur video thất bại", mode_override=render_options.video_encoder)
        output_metadata = probe_video_metadata(output_path)
        output_metadata.update(video_encoder=encoder.name, video_encoder_label=encoder.label, video_encoder_codec=encoder.codec)
        return output_path, output_metadata

    def output_path_for(self, input_path: Path) -> Path:
        prefix = safe_filename_prefix(input_path.stem, fallback="blurred_video")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = settings.outputs_dir / f"{prefix}_blurred_{timestamp}"
        return output_dir / f"{prefix}_blurred.mp4"

    def _normalize_regions(self, regions: list[BlurRegion], video_width: int, video_height: int, video_duration: float) -> list[tuple[float, float, int, int, int, int, int]]:
        intervals: list[tuple[float, float, int, int, int, int, int]] = []
        for region in regions:
            kfs = sorted(region.keyframes, key=lambda k: k.time)
            if not kfs:
                continue
            first = kfs[0]
            last = kfs[-1]
            px = lambda v, dim: max(0, min(dim - 2, round(v * dim)))
            times = [region.start] + [k.time for k in kfs] + [region.end]
            for i in range(len(times) - 1):
                seg_start = times[i]
                seg_end = times[i + 1]
                if seg_end <= seg_start:
                    continue
                if i == 0:
                    kf = first
                else:
                    kf = kfs[i - 1]
                x = px(kf.x, video_width)
                y = px(kf.y, video_height)
                w = max(2, min(video_width - x, px(kf.width, video_width)))
                h = max(2, min(video_height - y, px(kf.height, video_height)))
                intervals.append((seg_start, seg_end, x, y, w, h, kf.strength))
        return intervals

    def _filter_complex(self, intervals: list[tuple[float, float, int, int, int, int, int]]) -> str:
        n = len(intervals)
        if n == 0:
            return ""
        parts = [f"[0:v]split={n + 1}[v0]" + "".join(f"[k{i}]" for i in range(n)) + ";"]
        for i, (_, _, x, y, w, h, strength) in enumerate(intervals):
            parts.append(f"[k{i}]crop={w}:{h}:{x}:{y},boxblur={strength}:10[b{i}];")
        for i, (seg_start, seg_end, x, y, _, _, _) in enumerate(intervals):
            parts.append(f"[v{i}][b{i}]overlay={x}:{y}:enable='between(t,{seg_start},{seg_end})'[v{i + 1}];")
        return re.sub(r";$", "", "".join(parts))
