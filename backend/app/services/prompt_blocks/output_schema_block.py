from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class OutputSchemaBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        urls = [str(u) for u in (data.youtube_urls or [])]
        if data.source_mode != "multi" or not urls:
            urls = [str(data.youtube_url)]

        source_items: list[str] = []
        for index, url in enumerate(urls, start=1):
            label = "Video nguồn chính" if len(urls) == 1 else f"Mô tả ngắn nguồn video {index}"
            source_items.append(
                "    {\n"
                f'      "source_id": "source_{index}",\n'
                f'      "youtube_url": "{url}",\n'
                f'      "label": "{label}"\n'
                "    }"
            )

        sources_schema = '  "sources": [\n' + ",\n".join(source_items) + "\n  ],"
        example_url = urls[0]
        target_language = data.target_language or "Tiếng Việt"
        target_market = data.target_market or "Việt Nam"
        return (
            "Schema bắt buộc:\n"
            "{\n"
            '  "metadata": {\n'
            '    "video_title": "string",\n'
            '    "rewrite_style": "string",\n'
            '    "target_audience": "string",\n'
            '    "tone": "string",\n'
            '    "target_duration": "string",\n'
            f'    "target_language": "{target_language}",\n'
            f'    "target_market": "{target_market}",\n'
            '    "localization_level": "string",\n'
            '    "hashtags": ["hashtag1", "hashtag2"]\n'
            f"  }},\n"
            f"{sources_schema}\n"
            '  "rewrite_script": {\n'
            '    "full_text": "string"\n'
            "  },\n"
            '  "srt": [\n'
            "    {\n"
            '      "index": 1,\n'
            '      "start": "00:00:00,000",\n'
            '      "end": "00:00:05,000",\n'
            '      "text": "Subtitle text"\n'
            "    }\n"
            "  ],\n"
            '  "video_segments": [\n'
            "    {\n"
            '      "segment_id": 1,\n'
            '      "order": 1,\n'
            '      "source_id": "source_1",\n'
            '      "source_start": "00:00:12.000",\n'
            '      "source_end": "00:00:17.000",\n'
            '      "subtitle_start": 1,\n'
            '      "subtitle_end": 1,\n'
            '      "scene_description": "Mô tả khách quan cảnh được chọn"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "\n"
            f"youtube_url PHẢI là URL YouTube thật copy từ input (vd: {example_url}). "
            "KHÔNG BAO GIỜ dùng placeholder như ... hoặc {VIDEO_ID} — URL đó sẽ fail khi tải video.\n"
            "\n"
            "FINAL LITERAL VALUES:\n"
            f"  metadata.target_language = \"{target_language}\"\n"
            f"  metadata.target_market = \"{target_market}\"\n"
            "\n"
            "Schema trên là bắt buộc tuyệt đối. Không thêm, không bớt, không đổi tên field."
        )
