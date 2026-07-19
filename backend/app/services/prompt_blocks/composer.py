from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.dynamic_pacing_block import DynamicPacingBlock
from app.services.prompt_blocks.output_schema_block import OutputSchemaBlock
from app.services.prompt_blocks.validation_block import ValidationBlock


class PromptComposer:
    def __init__(self, data: PromptGenerateRequest) -> None:
        self.data = data

    def _source_urls(self) -> list[str]:
        urls = [str(url) for url in (self.data.youtube_urls or [])]
        if not urls:
            urls = [str(self.data.youtube_url)]
        return urls

    def compose_simple_editor(self) -> str:
        data = self.data
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        target_language = data.target_language or "Tiếng Việt"

        lines = [
            "SIMPLE EDITOR — VERIFIED REMAKE VIDEO ONE-SHOT",
            "",
            "Bạn là một chuyên gia biên kịch, nhà sáng tạo nội dung video và video editor chuyên nghiệp.",
            f"Nhiệm vụ của bạn là phân tích video YouTube được cung cấp và tạo một kịch bản remake hoàn chỉnh bằng {target_language}, sử dụng chính các đoạn cắt từ video gốc làm chất liệu hình ảnh.",
            "Kết quả phải vừa có chất lượng sáng tạo đủ tốt để con người duyệt, vừa có cấu trúc dữ liệu chính xác để hệ thống tự động cắt, dựng, tạo voiceover và subtitle.",
            "",
            "NGUỒN VIDEO",
            source_block,
            "",
            "═══════════════════════════════════════════════════════════════",
            "I. NGUYÊN TẮC XÁC MINH NGUỒN",
            "═══════════════════════════════════════════════════════════════",
            "Chỉ mô tả những hình ảnh, hành động, nhân vật, lời thoại hoặc sự kiện thực sự xác minh được từ video nguồn.",
            "Tuyệt đối không:",
            "- Đoán nội dung từ tiêu đề hoặc thumbnail.",
            "- Tạo timestamp giả.",
            "- Mô tả cảnh chưa thực sự quan sát được.",
            "- Giả vờ đã xem video khi không thể truy cập hoặc phân tích video.",
            "",
            "Nếu không thể truy cập hoặc xác minh nội dung video:",
            "- rewrite_script.full_text phải là chuỗi rỗng.",
            "- srt và video_segments phải là mảng rỗng.",
            "- Vẫn phải trả JSON hợp lệ theo đúng schema.",
            "",
            "Nếu chỉ xác minh được một phần video:",
            "- Chỉ sử dụng những đoạn đã xác minh.",
            "- Không điền nội dung cho những phần chưa xem được.",
            "",
            "═══════════════════════════════════════════════════════════════",
            "II. MỤC TIÊU SÁNG TẠO",
            "═══════════════════════════════════════════════════════════════",
            "Video remake phải có một câu chuyện hoàn chỉnh. Bám sát nội dung video gốc.",
            "Giữ 100% mạch truyện cốt lõi, thematic beats và storytelling framework để câu chuyện hoàn chỉnh. "
            "Cho phép compact montage, flashback và archival clips thành các visual block hợp nhất.",
        ]

        if data.user_instruction:
            lines.append("")
            lines.append("Hướng dẫn bổ sung từ người dùng:")
            lines.append(data.user_instruction)

        lines.extend([
            "",
            "═══════════════════════════════════════════════════════════════",
            DynamicPacingBlock().render(data),
            "═══════════════════════════════════════════════════════════════",
            "",
            "═══════════════════════════════════════════════════════════════",
            "IV. QUY TẮC TIMING VÀ VOICEOVER",
            "═══════════════════════════════════════════════════════════════",
            "Tốc độ đọc mục tiêu:",
            "- Trung bình: 2.5–3 từ Tiếng Việt mỗi giây.",
            "- Cảnh căng thẳng hoặc cần nhấn mạnh: có thể chậm hơn.",
            "- Cảnh montage nhanh: có thể nhanh hơn nhẹ, nhưng lời vẫn phải rõ và tự nhiên.",
            "",
            "Với mỗi subtitle:",
            "- Tính số từ để bảo đảm đọc hết trong khoảng start–end.",
            "- Không nhồi quá nhiều từ.",
            "- Không chia subtitle ở vị trí làm gãy nghĩa câu.",
            "- Ưu tiên mỗi subtitle chứa một ý hoàn chỉnh.",
            "- Subtitle phải dễ đọc và phù hợp để tạo voiceover.",
            "- Subtitle MEDIUM/COMPACT sau khi wrap ở boundary 80 ký tự không được vượt quá 3 dòng.",
            "- Nếu text clustered vượt giới hạn 3 dòng, phải chia sạch thành 2 SRT liên tiếp thay vì nhồi chữ.",
            "- Clustering phải giữ tốc độ đọc tự nhiên 2.5-3 từ mỗi giây và không làm gãy ngữ nghĩa.",
            "",
            "Với mỗi video segment:",
            "- Hình ảnh phải trực tiếp hỗ trợ subtitle được tham chiếu.",
            "- Tổng thời gian xuất hiện trên timeline remake phải đủ bao phủ voiceover liên quan.",
            "- Voiceover không được tiếp tục sau khi các segment hỗ trợ nó đã kết thúc, trừ trường hợp segment tiếp theo tiếp tục cùng subtitle range.",
            "- Không sử dụng cùng một thời lượng mặc định cho mọi segment.",
            "",
            "Cho phép khoảng lặng có chủ ý khi:",
            "- Cần nghe âm thanh gốc.",
            "- Cần tạo suspense.",
            "- Cần nhấn mạnh phản ứng.",
            "- Cần tạo payoff bằng hình ảnh.",
            "- Cần dành thời gian cho text overlay.",
            "Khoảng lặng có chủ ý phải được mô tả rõ trong scene_description.",
            "Profile COMPACT 10-15 giây phục vụ visual continuity và montage; không bắt buộc text phải dài tương ứng.",
            "",
            "Cho phép nhiều video segment cùng tham chiếu một subtitle khi dựng montage.",
            "Cho phép một video segment tham chiếu nhiều subtitle liên tiếp khi cảnh đủ dài và vẫn phù hợp với toàn bộ nội dung lời dẫn.",
            "Wide-range mapping (subtitle_start < subtitle_end) chỉ hợp lệ khi một visual block liên tục hỗ trợ toàn bộ dải subtitle.",
            "Không mass-wrap các subtitle rời rạc hoặc không liên quan để chữa cháy khoảng trống timeline.",
            "Không để hai subtitle chồng thời gian lên nhau.",
            "Subtitle đầu tiên phải bắt đầu tại \"00:00:00,000\".",
            "source_start phải nhỏ hơn source_end.",
            "",
            "═══════════════════════════════════════════════════════════════",
            "V. TÍNH NHẤT QUÁN GIỮA CÁC PHẦN",
            "═══════════════════════════════════════════════════════════════",
            "rewrite_script.full_text phải bằng nội dung của toàn bộ srt[].text ghép lại theo thứ tự index.",
            "Có thể thay đổi dấu xuống đoạn trong full_text, nhưng không được:",
            "- Thêm ý không có trong srt.",
            "- Bỏ ý có trong srt.",
            "- Viết khác nội dung voiceover.",
            "",
            "Mọi subtitle_start và subtitle_end phải tham chiếu index tồn tại trong srt[].",
            "Nếu segment chỉ dùng một subtitle:",
            "  subtitle_start phải bằng subtitle_end.",
            "Nếu segment dùng nhiều subtitle:",
            "  subtitle_start phải nhỏ hơn subtitle_end và tất cả index trong khoảng phải tồn tại.",
            "",
            "Thứ tự video segment trên timeline được xác định bằng video_segments[].order.",
            "video_segments[].order phải tăng liên tục từ 1.",
            "video_segments[].segment_id phải là số nguyên dương, không trùng nhau.",
            "srt[].index phải tăng liên tục từ 1 và không trùng nhau.",
            "video_segments[].source_id phải tồn tại trong sources[].",
            "SRT cuối cùng phải chứa phần kết luận thực sự của rewrite_script.full_text.",
            "Video segment cuối theo order phải có subtitle_end bằng index cuối cùng của srt[].",
            "Mọi SRT index phải được ít nhất một video segment bao phủ trong khoảng subtitle_start đến subtitle_end.",
            "",
            "═══════════════════════════════════════════════════════════════",
            "VI. ĐỊNH DẠNG TIMESTAMP",
            "═══════════════════════════════════════════════════════════════",
            "Timestamp subtitle:",
            "  Dùng định dạng HH:MM:SS,mmm.",
            '  Ví dụ hợp lệ: "00:00:15,000", "00:01:05,250".',
            '  Ví dụ không hợp lệ: "00:15,000", "00:00:15.000".',
            "",
            "Timestamp video nguồn (source_start, source_end):",
            "  Dùng định dạng HH:MM:SS.mmm.",
            '  Ví dụ hợp lệ: "00:00:12.000", "00:01:05.250".',
        ])

        lines.extend([
            "",
            "═══════════════════════════════════════════════════════════════",
            "VII. OUTPUT CONTRACT",
            "═══════════════════════════════════════════════════════════════",
            ValidationBlock().render(data),
            "═══════════════════════════════════════════════════════════════",
            "VIII. SCHEMA BẮT BUỘC",
            "═══════════════════════════════════════════════════════════════",
            OutputSchemaBlock().render(data),
            "═══════════════════════════════════════════════════════════════",
            "IX. FINAL SELF-CHECK TRƯỚC KHI OUTPUT",
            "═══════════════════════════════════════════════════════════════",
            "- JSON parse được.",
            "- Không có field thừa.",
            "- Không có field thiếu.",
            "- Không có duplicate key.",
            "- Không có trailing comma.",
            "- Không có timestamp sai định dạng.",
            "- Không có dấu nháy kép chưa escape.",
            "- normalize_whitespace(rewrite_script.full_text) bằng normalize_whitespace(srt[].text ghép theo index).",
            "- Segment cuối trỏ đúng SRT cuối và không có SRT index chưa được cover.",
            "- Không có markdown hoặc văn bản ngoài JSON.",
            "- Nếu bất kỳ điều kiện nào chưa đạt, phải sửa trước khi trả kết quả.",
        ])

        return "\n".join(lines)

    def compose(self) -> str:
        return self.compose_simple_editor()
