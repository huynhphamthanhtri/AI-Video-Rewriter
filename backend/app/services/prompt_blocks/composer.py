from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.creator_dna import load_creator_dna
from app.services.prompt_blocks.intent_block import IntentBlock
from app.services.prompt_blocks.localization_block import LocalizationBlock
from app.services.prompt_blocks.output_schema_block import OutputSchemaBlock
from app.services.prompt_blocks.strategy_block import StrategyBlock
from app.services.prompt_blocks.validation_block import ValidationBlock
from app.services.prompt_blocks.voice_block import VoiceBlock


class PromptComposer:
    def __init__(self, data: PromptGenerateRequest) -> None:
        self.data = data

    def compose_intro(self) -> str:
        data = self.data
        urls = [str(url) for url in (data.youtube_urls or [])]
        if not urls:
            urls = [str(data.youtube_url)]
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        source_instruction = (
            "Hãy phân tích toàn bộ các video YouTube sau:\n"
            f"{source_block}\n\n"
            "MULTI-SOURCE RULES:\n"
            "- Root JSON bắt buộc có sources[].\n"
            "- Mỗi source có source_id duy nhất dạng source_1, source_2... theo đúng thứ tự link ở trên.\n"
            "- Mỗi item video_segments[] bắt buộc có source_id.\n"
            "- source_id phải tham chiếu đúng một item trong sources[].\n"
            "- source_start/source_end là timestamp trong video nguồn tương ứng, không phải timeline video cuối.\n"
            "- Hãy phối hợp cảnh từ nhiều nguồn nếu giúp remake hấp dẫn hơn."
            if data.source_mode == "multi"
            else f"Hãy phân tích toàn bộ video YouTube từ URL sau: {urls[0]}"
        )
        return f"Bạn là chuyên gia biên tập video, biên kịch và dựng phim hậu kỳ.\n{source_instruction}"

    def compose_subtitle_block(self) -> str:
        return (
            "RÀNG BUỘC SUBTITLE / SUBTITLE CONSTRAINTS (BẮT BUỘC / MANDATORY):\n"
            "- Mỗi subtitle chỉ được tối đa 2 dòng (max 2 lines per subtitle).\n"
            "- Mỗi dòng tối đa 40 ký tự (max 40 chars per line, tổng tối đa 80 ký tự / subtitle).\n"
            "- Tốc độ tối đa: 3.0 từ/giây (max 3.0 words/sec). Nếu vượt, phải tách thành nhiều SRT item.\n"
            f"- Mật độ nội dung \"{self.data.content_density}\":\n"
            "  - Thấp (Low): 2.0 words/sec — minimal text, more visuals.\n"
            "  - Trung bình (Medium): 2.8 words/sec\n"
            "  - Cao (High): 3.5 words/sec\n"
            "- Ưu tiên câu ngắn, dễ đọc nhanh. Tránh câu ghép dài >25 từ trong 1 subtitle."
        )

    def compose_content_quality_block(self) -> str:
        return (
            "CHẤT LƯỢNG NỘI DUNG / CONTENT QUALITY (QUAN TRỌNG):\n"
            f"- Viết bằng {self.data.target_language} tự nhiên, giàu cảm xúc, như một người đang kể chuyện cho bạn nghe.\n"
            f"- Write naturally in {self.data.target_language}, rich in emotion, as if telling a story.\n"
            "- Tránh liệt kê khô khan, tránh câu quá dài, tránh từ ngữ sáo rỗng.\n"
            "- Mỗi câu đều phải có giá trị thông tin hoặc cảm xúc — không chêm filler.\n"
            "- Kể chuyện có nhịp: dẫn dắt → cao trào → kết luận/cảm xúc.\n"
            " - Subtitle phải tuân thủ RÀNG BUỘC SUBTITLE ở phần cấu hình phía trên "
            "(tối đa 2 dòng, 40 ký tự/dòng, 3.0 từ/giây).\n"
            " - Sử dụng câu hỏi tu từ, cảm thán nhẹ, biến đổi nhịp câu để tạo cảm giác tự nhiên.\n"
            " - Use rhetorical questions, light exclamations, and varied sentence rhythm.\n"
            "- Không dùng quá nhiều dữ kiện số trong một câu — hãy diễn giải, so sánh để người xem dễ hình dung.\n"
            "- Giữa các segment, đảm bảo có sự liên kết về mặt nội dung và cảm xúc, không bị ngắt quãng."
        )

    def compose_hook_block(self) -> str:
        return (
            "HOOK BẮT BUỘC - CẢNH ĐẮT GIÁ:\n"
            "- Mở video bằng cảnh có visual/action/emotion/information beat mạnh nhất trong toàn bộ nguồn, "
            "không nhất thiết là cảnh đầu timeline gốc.\n"
            "- Segment đầu tiên phải là cảnh đắt giá này.\n"
            "- Cảnh hook phải là sự kiện nhìn thấy rõ trên màn hình: bắt quả tang, va chạm, truy đuổi, "
            "phát hiện quan trọng, phản ứng sốc, twist chính, pha cứu nguy, khoảnh khắc cao trào, "
            "hoặc bằng chứng then chốt.\n"
            "- Subtitle đầu tiên phải mô tả đúng điều đang thấy trong cảnh hook, không giới thiệu bối cảnh dài dòng.\n"
            "- Sau hook, các segment tiếp theo được phép quay lại bối cảnh trước đó để giải thích "
            "chuyện gì dẫn tới khoảnh khắc này.\n"
            "- Không chọn cảnh đẹp nhưng thiếu ý nghĩa làm hook.\n"
            "- Nếu có nhiều cảnh mạnh, chọn cảnh có tổng điểm tốt nhất: visual rõ, hiểu được trong 3-6 giây, "
            "tạo tò mò, và liên quan trực tiếp đến câu chuyện chính.\n"
            "- Với nội dung tin tức/giáo dục/tư liệu nhẹ, 'cảnh đắt giá' có thể là dữ kiện, hình ảnh, phát hiện, "
            "biểu đồ, lời nói hoặc khoảnh khắc then chốt nhất, không cần gây sốc giả tạo."
        )

    def compose_task_block(self) -> str:
        return (
            f"Nhiệm vụ:\n"
            f"1. Phân tích video gốc, chọn các đoạn hình ảnh quan trọng nhất để dựng lại video mới.\n"
            f"2. Viết rewrite_script.full_text bằng {self.data.target_language}.\n"
            f"3. Tạo subtitle SRT bằng {self.data.target_language}.\n"
            f"4. Tạo danh sách video_segments[] để renderer cắt trực tiếp từ video gốc.\n"
            f"5. metadata.video_title BẮT BUỘC phải viết bằng đúng ngôn ngữ đích ({self.data.target_language}) "
            f"và phù hợp thị trường đích ({self.data.target_market}); "
            f"không giữ title gốc nếu title gốc khác ngôn ngữ đích."
        )

    def compose_alignment_block(self) -> str:
        return (
            "SRT-SCENE ALIGNMENT RULES:\n"
            "- Mỗi video_segments[] phải tương ứng trực tiếp với nội dung subtitle được tham chiếu.\n"
            "- Subtitle text phải mô tả đúng hành động/cảm xúc/đối tượng đang xuất hiện trong "
            "source_start/source_end.\n"
            "- Không dùng subtitle nói trước cảnh hoặc nói sau cảnh; lời kể phải bám visual beat hiện tại.\n"
            "- Không ghép nhiều sự kiện khác nhau vào cùng một subtitle nếu visual segment chỉ có một sự kiện.\n"
            "- Nếu một ý kể có nhiều hành động liên tiếp, hãy tách thành nhiều srt item ngắn và nhiều "
            "video_segments tương ứng.\n"
            "- Prefer 3-6 second segments for fast actions. Avoid segments longer than 8 seconds unless "
            "it is continuous context, replay, or celebration.\n"
            "- scene_description phải mô tả cùng sự kiện với subtitle text, không mô tả cảnh khác.\n"
            "- srt items KHÔNG được overlap thời gian: srt[N].end PHẢI nhỏ hơn hoặc bằng srt[N+1].start.\n"
            "- Từng srt item phải kết thúc hoàn toàn trước khi srt item tiếp theo bắt đầu."
        )

    def compose_domain_rules_block(self) -> str:
        return (
            "DOMAIN RULES FOR SPORTS / ALL GOALS & HIGHLIGHTS:\n"
            "- Với bóng đá/highlights, hãy tách pha quan trọng thành các beat: "
            "buildup/context, pass/assist, shot, ball crossing line/save, celebration/replay/reaction.\n"
            "- Subtitle của từng beat chỉ nói về thứ đang thấy trong beat đó.\n"
            "- Không nói final score khi đang chiếu cảnh tranh chấp giữa sân không liên quan.\n"
            "- Nếu đang chiếu replay, subtitle phải nói replay/aftermath hoặc mô tả lại đúng hành động trong replay.\n"
            "- Nếu đang chiếu HLV/cầu thủ phản ứng, subtitle phải nói về reaction, "
            "không nói như thể cú sút đang diễn ra."
        )

    def compose(self) -> str:
        voice_text = VoiceBlock().render(self.data)
        dna_text = load_creator_dna()

        parts: list[str] = [
            self.compose_intro(),
            IntentBlock().render(self.data),
            StrategyBlock().render(self.data),
            voice_text,
        ]

        if dna_text:
            parts.append("CREATOR DNA / BẢN SẮC NGƯỜI KỂ:\n" + dna_text)

        parts.extend([
            LocalizationBlock().render(self.data),
            self.compose_subtitle_block(),
            self.compose_content_quality_block(),
            self.compose_hook_block(),
            self.compose_task_block(),
            self.compose_alignment_block(),
            self.compose_domain_rules_block(),
            ValidationBlock().render(self.data),
            OutputSchemaBlock().render(self.data),
        ])

        return "\n\n".join(parts)
