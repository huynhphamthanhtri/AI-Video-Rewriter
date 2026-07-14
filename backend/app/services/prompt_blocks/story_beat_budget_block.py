from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class StoryBeatBudgetBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        return (
            "STORY BEAT BUDGETING / DEFAULT GENERATION MODE (BẮT BUỘC):\n"
            "- Default Generation Mode: Luôn tự hiểu nội dung nguồn, tự chọn phong cách kể chuyện phù hợp nhất "
            "dựa trên toàn bộ cấu hình được cung cấp, và tạo một bản remake hoàn chỉnh. "
            "Nếu không có chỉ dẫn style rõ ràng, vẫn phải tự suy luận best-fit style, không được fallback "
            "sang recap/highlight extraction.\n"
            "- Core Engine: Story Understanding → Story Beat Extraction → Beat Scoring → "
            "Runtime Budget → Visual Planning → Rewrite Script → SRT → Video Segments.\n"
            "- Style Layer (Preset, Template, Creator DNA, Additional Instructions) chỉ là gợi ý về "
            "tone/vocabulary/pacing. KHÔNG được override beat preservation, runtime allocation hoặc narrative coverage.\n"
            f"- Target duration: {data.target_duration}. Dùng làm runtime budget thực tế, không tạo highlight ngắn.\n"
            "\n"
            "STORY BEAT EXTRACTION:\n"
            "- Extract toàn bộ story beat chain trước. Không quyết định giữ/bỏ ở bước này.\n"
            "- Beat types: setup, context, transition, tension, evidence, discovery, payoff, aftermath/reaction.\n"
            "- Mỗi script phải có đủ chuỗi setup → tension → discovery → payoff, không thiếu bước nào.\n"
            ""
            "\n"
            "QUY TẮC CẮT GỌN (AGGRESSIVE CUTTING):\n"
            "- Loại bỏ thẳng tay các phân đoạn lặp lại ý, lời thoại thừa (à, ừ, chào hỏi, kêu gọi tương tác).\n"
            "- Loại bỏ nhánh nội dung phụ (sub-plots) không đóng góp trực tiếp vào kết quả (Payoff) của mạch truyện chính.\n"
            "- Setup/Context KHÔNG bị xóa, nhưng phải được NÉN thành 1-2 câu tóm tắt cốt lõi (Ai? Làm gì? Tại sao?).\n"
            "\n"
            "BEAT SCORING:\n"
            "- Chấm điểm nội bộ từng beat theo: importance, tension, evidence, emotional value, visual value, "
            "continuity/context value.\n"
            "- Điểm thấp nghĩa là beat ngắn hơn, KHÔNG nghĩa là beat bị xoá.\n"
            "\n"
            "RUNTIME BUDGET PLANNING:\n"
            "- Phân bổ allocated_seconds nội bộ cho từng beat để tổng runtime gần target duration.\n"
            ""
            "- Với target 5-10 phút từ source 15-25 phút, output chỉ 10-20 visual moments thường là dấu hiệu recap; "
            "hãy tăng số beat/visual moments hợp lý để giữ story coverage.\n"
            "- Budget phải được phản ánh qua srt[] duration và video_segments[], không thêm allocated_seconds vào JSON.\n"
            "\n"
            "VISUAL PLANNING:\n"
            "- Mỗi planned beat phải có visual coverage tương ứng bằng một hoặc nhiều video_segments[].\n"
            "- Subtitle phải bám đúng visual beat hiện tại; không nhảy từ setup sang payoff mà thiếu tension/discovery bridge.\n"
            "\n"
            "INTERNAL COVERAGE REPORT (KHÔNG XUẤT RA JSON):\n"
            "- Trước khi trả JSON, tự kiểm tra nội bộ: setup coverage, tension coverage, discovery coverage, payoff coverage.\n"
            "- Nếu thiếu coverage nào, hãy revise srt[] và video_segments[] trước khi trả final JSON.\n"
            "- Do not include this report in final JSON. Không thêm story_beats, beat_scores, runtime_budget, "
            "coverage_report hoặc allocated_seconds vào schema output.\n"
        )
