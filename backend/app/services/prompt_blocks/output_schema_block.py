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
            '═══════════════════════════════════════════════════════════════\n'
            '⚠  STRICT OUTPUT CONTRACT — ĐỌC KỸ TRƯỚC KHI TRẢ JSON  ⚠\n'
            '═══════════════════════════════════════════════════════════════\n'
            'MANDATORY RULES (VI PHẠM = INVALID):\n'
            '1. Return ONLY valid JSON — tuyệt đối không markdown, không code fence, không ```json.\n'
            '2. Ký tự đầu tiên của response PHẢI là {, ký tự cuối cùng PHẢI là }.\n'
            '3. Không thêm bất kỳ field nào ngoài schema bên dưới. Extra fields = REJECTED.\n'
            '4. Không thêm comments, không giải thích, không ghi chú bên ngoài JSON.\n'
            '5. Các trường KHÔNG được null hoặc undefined — nếu không có dữ liệu, dùng giá trị mặc định phù hợp.\n'
            '6. Không dùng markdown links trong youtube_url — URL thuần, không []().\n'
            '7. Schema bên dưới là bắt buộc tuyệt đối. Không thêm, không bớt, không đổi tên field.\n'
            '8. Không thêm tts_text vào srt item.\n'
            '9. Subtitle phải dễ đọc, tự nhiên và không cắt gãy nghĩa câu.\n'
            '10. Mỗi subtitle phải có timing đủ để voiceover đọc hết nội dung.\n'
             '11. Strings containing double quotes must escape them as \\". '
             'Sai: "text": "Tên hắn là "Edward Wilson".". '
             'Đúng: "text": "Tên hắn là \\"Edward Wilson\\".".\n'
            '12. No duplicate keys in any object level.\n'
            '13. No unescaped control characters (\\n, \\t allowed inside string values only).\n'
            '14. No trailing commas in arrays or objects.\n'
             '15. Array limit: srt[] và video_segments[] KHÔNG ĐƯỢC VƯỢT QUÁ 90 phần tử. '
              'Nếu nội dung quá dài, hãy NÉN và gộp câu thay vì tăng số lượng.\n'
             f'16. youtube_url PHẢI là URL YouTube thật copy từ input (vd: {example_url}). '
              'KHÔNG BAO GIỜ dùng placeholder như ... hoặc {VIDEO_ID} — URL đó sẽ fail khi tải video.\n'
             'VIOLATION → TOÀN BỘ RESPONSE BỊ REJECT, PHẢI LÀM LẠI TỪ ĐẦU.\n'
            '═══════════════════════════════════════════════════════════════\n'
            '\n'
            'FINAL LITERAL VALUES — COPY EXACTLY:\n'
            f'  metadata.target_language = "{target_language}"\n'
            f'  metadata.target_market = "{target_market}"\n'
            '\n'
            'SRT timestamp examples:\n'
            '  VALID:   "00:00:15,000"\n'
            '  VALID:   "00:01:05,000"\n'
            '  INVALID: "00:15,000"\n'
            '  INVALID: "00:00:15.000"\n'
            '\n'
            'scene_beats.story_role allowed values:\n'
            '  "hook", "opening", "setup", "context", "progression", "climax", "payoff", "ending"\n'
            "  Do NOT use: \"action\", \"emotion\".\n"
            '\n'
            "Schema bắt buộc:\n"
            "{\n"
            '  "metadata": {\n'
            '    "video_title": "string",\n'
            '    "rewrite_style": "string",\n'
            '    "target_audience": "string",\n'
            '    "tone": "string",\n'
            '    "target_duration": "string",\n'
            '    "target_language": "string",\n'
            '    "target_market": "string",\n'
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
            '      "scene_description": "Mô tả ngắn cảnh được chọn",\n'
            '      "importance_score": 95\n'
            "    }\n"
            "  ]\n"
            "}"
        )
