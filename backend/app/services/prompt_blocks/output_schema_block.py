from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class OutputSchemaBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        sources_schema = (
            '  "sources": [\n'
            '    {\n'
            '      "source_id": "source_1",\n'
            '      "youtube_url": "https://www.youtube.com/watch?v=...",\n'
            '      "label": "Mô tả ngắn nguồn video"\n'
            "    }\n"
            "  ],"
            if data.source_mode == "multi"
            else '  "sources": [\n'
            '    {\n'
            '      "source_id": "source_1",\n'
            '      "youtube_url": "https://www.youtube.com/watch?v=...",\n'
            '      "label": "Video nguồn chính"\n'
            "    }\n"
            "  ],"
        )
        return (
            '═══════════════════════════════════════════════════════════════\n'
            '⚠  STRICT OUTPUT CONTRACT — ĐỌC KỸ TRƯỚC KHI TRẢ JSON  ⚠\n'
            '═══════════════════════════════════════════════════════════════\n'
            'MANDATORY RULES (VI PHẠM = INVALID):\n'
            '1. Return ONLY valid JSON — tuyệt đối không markdown, không code fence, không ```json.\n'
            '2. Ký tự đầu tiên của response PHẢI là {{, ký tự cuối cùng PHẢI là }}.\n'
            '3. Không thêm bất kỳ field nào ngoài schema bên dưới. Extra fields = REJECTED.\n'
            '4. Không thêm comments, không giải thích, không ghi chú bên ngoài JSON.\n'
            '5. Các trường KHÔNG được null hoặc undefined — nếu không có dữ liệu, dùng giá trị mặc định phù hợp.\n'
            '6. Không dùng markdown links trong youtube_url — URL thuần, không []().\n'
            '7. Schema bên dưới là bắt buộc tuyệt đối. Không thêm, không bớt, không đổi tên field.\n'
            'VIOLATION → TOÀN BỘ RESPONSE BỊ REJECT, PHẢI LÀM LẠI TỪ ĐẦU.\n'
            '═══════════════════════════════════════════════════════════════\n'
            '\n'
            "Schema bắt buộc:\n"
            "{{\n"
            '  "metadata": {{\n'
            '    "video_title": "string",\n'
            '    "rewrite_style": "string",\n'
            '    "target_audience": "string",\n'
            '    "tone": "string",\n'
            '    "target_duration": "string",\n'
            '    "target_language": "string",\n'
            '    "target_market": "string",\n'
            '    "localization_level": "string",\n'
            '    "adaptation_mode": "string",\n'
            '    "narrator_persona": "string"\n'
            f"  }},\n"
            f"{sources_schema}\n"
            '  "rewrite_script": {{\n'
            '    "full_text": "string"\n'
            "  }},\n"
            '  "srt": [\n'
            "    {{\n"
            '      "index": 1,\n'
            '      "start": "00:00:00,000",\n'
            '      "end": "00:00:05,000",\n'
            '      "text": "Subtitle text"\n'
            "    }}\n"
            "  ],\n"
            '  "video_segments": [\n'
            "    {{\n"
            '      "segment_id": 1,\n'
            '      "order": 1,\n'
            '      "source_id": "source_1",\n'
            '      "source_start": "00:00:12.000",\n'
            '      "source_end": "00:00:17.000",\n'
            '      "subtitle_start": 1,\n'
            '      "subtitle_end": 1,\n'
            '      "scene_description": "Mô tả ngắn cảnh được chọn",\n'
            '      "importance_score": 95\n'
            "    }}\n"
            "  ]\n"
            "}}"
        )
