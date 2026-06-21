from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class ValidationBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        source_segment_rule = (
            "- video_segments[].source_id là bắt buộc và phải tồn tại trong sources[]."
            if data.source_mode == "multi"
            else "- Với một nguồn video, video_segments[].source_id có thể dùng source_1 để tương thích renderer."
        )
        return (
            "QUY TẮC JSON BẮT BUỘC:\n"
            "- Return ONLY valid JSON as a raw JSON object.\n"
            "- Ký tự đầu tiên của response PHẢI là {{.\n"
            "- Ký tự cuối cùng của response PHẢI là }}.\n"
            "- Tuyệt đối không bọc JSON trong code fence.\n"
            "- Không dùng ```json, không dùng ```, không dùng markdown, không giải thích ngoài JSON.\n"
            "- Nếu bạn định dùng code block, hãy bỏ code block và chỉ trả object JSON thô.\n"
            "- Root object chỉ được có các key: metadata, sources, rewrite_script, srt, video_segments.\n"
            "- Root object nên có sources[] để mô tả nguồn video. Với multi-source, sources[] là bắt buộc.\n"
            "- metadata.video_title phải là title mới đã localize bằng đúng target_language, dùng được để burn trực tiếp lên đầu video.\n"
            "- DO NOT return clips. Trường clips[] là format cũ và INVALID.\n"
            "- DO NOT return timeline. Trường timeline[] là format cũ và INVALID.\n"
            "- Nếu cần biểu diễn timeline, hãy đưa trực tiếp vào video_segments[].\n"
            "- sources[].youtube_url phải là URL thuần, không dùng Markdown link.\n"
            '- Đúng: "https://www.youtube.com/watch?v=abc123". Sai: "[https://www.youtube.com/watch?v=abc123](https://www.youtube.com/watch?v=abc123)".\n'
            "- Tất cả timestamp SRT phải dùng định dạng HH:MM:SS,mmm.\n"
            "- Tất cả timestamp video source phải dùng định dạng HH:MM:SS.mmm.\n"
            "- srt[].index phải là số nguyên dương, không trùng nhau.\n"
            "- video_segments[].segment_id phải là số nguyên dương, không trùng nhau.\n"
            "- video_segments[].order phải là số nguyên dương, không trùng nhau.\n"
            f"{source_segment_rule}\n"
            "- video_segments[].subtitle_start và subtitle_end phải tham chiếu index có thật trong srt[].\n"
            "- source_start phải nhỏ hơn source_end.\n"
            "- subtitle_start phải nhỏ hơn hoặc bằng subtitle_end.\n"
            "- Maximum duration difference allowed: 2 seconds.\n"
            "- Duration của mỗi video segment phải khớp duration subtitle range tương ứng: "
            "source_end - source_start ≈ srt[subtitle_end].end - srt[subtitle_start].start.\n"
            "- Không tạo clip dài rồi gán subtitle ngắn. Hãy trim source_end để khớp thời lượng subtitle.\n"
            "\n"
            "Ví dụ duration hợp lệ:\n"
            "- srt index 1 chạy từ 00:00:00,000 đến 00:00:05,000, duration = 5 giây.\n"
            "- video segment tham chiếu subtitle_start=1 và subtitle_end=1 phải có source duration "
            "khoảng 5 giây, ví dụ source_start=00:00:12.000 và source_end=00:00:17.000."
        )
