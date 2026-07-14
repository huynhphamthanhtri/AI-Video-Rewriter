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
            "- Root object chỉ được có các key: metadata, sources, rewrite_script, srt, video_segments.\n"
            "- Root object bắt buộc phải có sources[] để mô tả nguồn video.\n"
            "- metadata.video_title phải viết bằng đúng target_language.\n"
            "- DO NOT return clips. Trường clips[] là format cũ và INVALID.\n"
            "- DO NOT return timeline. Trường timeline[] là format cũ và INVALID.\n"
            "- Nếu cần biểu diễn timeline, hãy đưa trực tiếp vào video_segments[].\n"
            "- sources[].youtube_url phải là URL thuần, không dùng Markdown link.\n"
            '- Đúng: "https://www.youtube.com/watch?v=abc123". Sai: "[https://www.youtube.com/watch?v=abc123](https://www.youtube.com/watch?v=abc123)".\n'
            '- Mọi dấu nháy kép bên trong string value phải được escape thành \\", đặc biệt là trong rewrite_script.full_text và srt[].text.\n'
            "- Tất cả timestamp SRT phải dùng định dạng HH:MM:SS,mmm (dùng dấu phẩy).\n"
            "- Tất cả timestamp video source (source_start, source_end) phải dùng định dạng HH:MM:SS.mmm (dùng dấu chấm, KHÔNG dùng dấu phẩy).\n"
            "- srt[].index phải là số nguyên dương, không trùng nhau.\n"
            "- video_segments[].segment_id phải là số nguyên dương, không trùng nhau.\n"
            "- video_segments[].order phải là số nguyên dương, không trùng nhau.\n"
            f"{source_segment_rule}\n"
            "- video_segments[].subtitle_start và subtitle_end phải tham chiếu index có thật trong srt[].\n"
            "- source_start phải nhỏ hơn source_end.\n"
            "- subtitle_start phải nhỏ hơn hoặc bằng subtitle_end.\n"
            "- Tổng thời lượng các subtitle (subtitle_start→subtitle_end) phải "
            "được bao phủ bởi thời lượng source_start→source_end của segment đó.\n"
            "- Không để voiceover của subtitle tiếp tục sau khi video_segment tương ứng kết thúc."
        )
