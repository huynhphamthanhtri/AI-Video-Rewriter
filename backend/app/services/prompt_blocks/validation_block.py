from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class ValidationBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        return (
            "Chỉ trả về một JSON object hợp lệ.\n"
            "Không dùng Markdown.\n"
            "Không dùng code fence.\n"
            "Không thêm lời giải thích trước hoặc sau JSON.\n"
            "Ký tự đầu tiên phải là { và ký tự cuối cùng phải là }.\n"
            "\n"
            "Root object chỉ được có các key:\n"
            "  metadata\n"
            "  sources\n"
            "  rewrite_script\n"
            "  srt\n"
            "  video_segments\n"
            "\n"
            "Không được:\n"
            "- Thêm field ngoài schema.\n"
            "- Đổi tên field.\n"
            "- Bỏ field.\n"
            "- Dùng clips.\n"
            "- Dùng timeline.\n"
            "- Dùng tts_text.\n"
            "- Dùng scene_beats.\n"
            "- Dùng output_start, output_end.\n"
            "- Dùng story_role, selection_reason, editing_instruction, audio_instruction.\n"
            "- Dùng text_overlay, transition, playback_speed.\n"
            "- Dùng analysis_status, analysis_note, opening_strategy.\n"
            "- Dùng comment trong JSON.\n"
            "- Dùng trailing comma.\n"
            "- Dùng duplicate key.\n"
            "- Dùng null hoặc undefined.\n"
            "\n"
            "Nếu không có dữ liệu:\n"
            "  Dùng chuỗi rỗng cho string.\n"
            "  Dùng mảng rỗng cho array.\n"
            "  Không dùng null.\n"
            "\n"
            "youtube_url phải là URL thuần được copy chính xác từ input.\n"
            'Mọi dấu nháy kép bên trong string value phải được escape thành ".\n'
            "Không áp bất kỳ giới hạn phần tử tùy ý hoặc hardcoded nào cho srt[] hoặc video_segments[]. "
            "Tổng số phần tử phải được quyết định bằng Dynamic Pacing và công thức toán học phủ dòng thời gian mục tiêu "
            "dựa trên target_duration và độ phức tạp narrative. "
            "Nghiêm cấm đóng JSON sớm hoặc bỏ phần kết luận để giảm phần tử.\n"
            "Với một nguồn video, video_segments[].source_id có thể dùng source_1 để tương thích renderer.\n"
            "\n"
            "Mỗi srt item phải có text và timing hợp lệ.\n"
            "Mỗi video_segments item phải có scene_description mô tả khách quan cảnh được chọn.\n"
            "FINAL ARITHMETIC GATE: parse metadata.target_duration thành giây và so sánh với srt[-1].end; "
            "với target chính xác, hai giá trị phải bằng nhau trước khi output.\n"
            "FINAL TEXT GATE: rewrite_script.full_text chỉ được copy từ phép ghép nguyên văn srt[].text theo index; "
            "không được soạn hai phiên bản độc lập."
        )
