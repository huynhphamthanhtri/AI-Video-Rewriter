from __future__ import annotations

import json

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.output_schema_block import OutputSchemaBlock
from app.services.prompt_blocks.validation_block import ValidationBlock
from app.services.prompt_blocks.domain_rules_block import DomainRulesBlock


class PromptComposer:
    def __init__(self, data: PromptGenerateRequest) -> None:
        self.data = data

    def _source_urls(self) -> list[str]:
        urls = [str(url) for url in (self.data.youtube_urls or [])]
        if not urls:
            urls = [str(self.data.youtube_url)]
        return urls

    def compose_intro(self) -> str:
        data = self.data
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))

        lines = [
            "LỚP 1 — VAI TRÒ, NGUỒN VIDEO VÀ CHỐNG BỊA NỘI DUNG",
            "",
            "Bạn là biên kịch remake video và chuyên gia viết voiceover có khả năng giữ chân người xem.",
            "",
            "Hãy xem toàn bộ nội dung từ các video YouTube sau:",
            source_block,
            "Lưu ý: Tuyệt đối không được bịa nội dung nếu không xem được link. Nghiêm cấm bịa nội dung.",
        ]

        if data.source_mode == "multi" and len(urls) > 1:
            lines.append("")
            lines.append("QUY TẮC NHIỀU NGUỒN (MULTI-SOURCE):")
            for i in range(1, len(urls) + 1):
                lines.append(f"- URL #{i} → source_{i}")
            source_ids = ", ".join(f"source_{i}" for i in range(1, len(urls) + 1))
            lines.append("")
            lines.append(f"sources[] bắt buộc phải có đúng {len(urls)} items, mỗi item với source_id tương ứng.")
            lines.append(f"Mỗi video_segment.source_id phải tham chiếu một trong các source_id hợp lệ: {source_ids}.")

        lines.append("")
        lines.append("Nếu video có bình luận công khai và có thể truy cập, hãy đọc để hiểu phản ứng")
        lines.append("khán giả, ngữ cảnh và chi tiết đáng chú ý.")
        lines.append("")
        lines.append("Chỉ đưa phản ứng khán giả vào kịch bản nếu nó giúp video hấp dẫn hơn.")
        lines.append("Không bịa bình luận cụ thể. Nếu không xác minh được bình luận, chỉ dùng nhận")
        lines.append("định chung dựa trên nội dung video, không giả vờ đã đọc bình luận.")
        lines.append("")
        lines.append("Trước khi viết, hãy tự phân tích toàn bộ video nguồn như một biên kịch remake.")
        lines.append("")
        lines.append("Hãy tự xác định:")
        lines.append("- Nội dung chính của video là gì.")
        lines.append("- Mạch sự kiện quan trọng từ đầu đến cuối.")
        lines.append("- Các cảnh biểu tượng hoặc cảnh không thể bỏ.")
        lines.append("- Cảnh mở đầu, cảnh leo thang, cảnh cao trào và cảnh kết.")
        lines.append("- Điểm khiến người xem muốn xem tiếp.")
        lines.append("- Bình luận khán giả có cung cấp ngữ cảnh hữu ích hay không.")
        lines.append("")
        lines.append("Không cần xuất phần phân tích này ra ngoài, chỉ dùng để tạo kịch bản cuối cùng.")
        lines.append("")
        lines.append(f"Hãy biến nội dung video này thành một bản remake voiceover hấp dẫn bằng {data.target_language},")
        lines.append("có khả năng giữ chân người xem cao.")
        lines.append("")
        lines.append(
            "Cắt bỏ các cảnh thừa, cảnh dở. "
            "Cân nhắc để không cắt mạch truyện. "
            "Cắt vừa vặn để làm mới nội dung nhưng không bị mất đi mạch truyện, giá trị nội dung của video. "
            "Tránh trường hợp video chưa hết ngữ cảnh đã bị cắt làm người xem không hiểu gì. "
            "Cảnh không mô tả hết ý của voiceover."
        )

        if data.user_instruction:
            lines.append("")
            lines.append("NGƯỜI DÙNG HƯỚNG DẪN THÊM:")
            lines.append(data.user_instruction)

        lines.append("")
        lines.append("Khi có hướng dẫn bổ sung từ người dùng, hãy dùng chúng như định hướng sáng tạo,")
        lines.append("không dùng như luật cứng nếu chúng làm hỏng chất lượng câu chuyện.")
        lines.append("")
        lines.append("Thứ tự ưu tiên:")
        lines.append("1. Giữ đúng mạch logic và nội dung chính của video nguồn.")
        lines.append("2. Không bỏ cảnh quan trọng, cảnh biểu tượng, cảnh cao trào hoặc cảnh giải quyết.")
        lines.append("3. Tạo kịch bản remake hấp dẫn, có nhịp kể và khả năng giữ chân người xem.")
        lines.append("4. Áp dụng hướng dẫn bổ sung của người dùng ở mức phù hợp.")
        lines.append("5. Xuất đúng JSON schema.")

        lines.append("")
        lines.append(
            "Hãy tự chọn giọng kể phù hợp nhất với nội dung nguồn và hướng dẫn bổ sung."
        )
        lines.append("")
        lines.append(
            "Có thể dùng hài hước, châm biếm, mỉa mai, kịch tính, cảm xúc hoặc nghiêm túc"
        )
        lines.append(
            "nếu phù hợp. Tuy nhiên, không được áp dụng một phong cách quá cứng nhắc"
        )
        lines.append(
            "nếu nó làm mất mạch truyện, giảm độ hấp dẫn hoặc khiến kịch bản bị gượng."
        )
        lines.append("")
        lines.append("Hãy tự quyết định:")
        lines.append('- Độ dài video remake phù hợp nhất nếu trong phần "Hướng dẫn thêm" không yêu cầu độ dài. Lưu ý: Tránh video quá dài hoặc quá nguyên bản – Ví dụ sử dụng lại các segment quá dài vì như vậy sẽ không đảm bảo được tiêu chí remake video')
        lines.append('- Giọng kể và sắc thái cảm xúc nếu trong phần "Hướng dẫn thêm" không yêu cầu Giọng kể và sắc thái cảm xúc cụ thể.')
        lines.append('- Nhịp cắt cảnh, tốc độ dẫn chuyện nếu trong phần "Hướng dẫn thêm" không yêu cầu Nhịp cắt cảnh, tốc độ dẫn chuyện cụ thể.')
        lines.append("- Cách sử dụng bình luận khán giả nếu chúng giúp câu chuyện hấp dẫn hơn.")
        lines.append("* Lưu ý về khớp cảnh và voiceover: Mỗi cảnh được chọn phải có thời lượng phù hợp với lời dẫn tương ứng, nhưng không được rút ngắn lời dẫn chỉ để vừa khít thời lượng cảnh. Hãy để độ dài câu tự nhiên theo mức độ quan trọng, cảm xúc và lượng thông tin thật của cảnh.")
        lines.append("")
        lines.append("QUY TẮC BẮT BUỘC — CÂN BẰNG THỜI LƯỢNG CẢNH & VOICEOVER:")
        lines.append("- Mỗi video_segment sẽ được kiểm tra theo thời lượng voiceover tương ứng.")
        lines.append("- Không viết voiceover kiểu liệt kê mốc cảnh hoặc câu cụt ngủn chỉ để khớp timing.")
        lines.append("- Hãy tự cân bằng độ dài lời dẫn theo nội dung thật của từng cảnh: cảnh đơn giản có thể ngắn, cảnh quan trọng cần đủ ngữ cảnh và cảm xúc.")
        lines.append("- Nếu cảnh cần lời dẫn dài hơn để kể đủ ý, hãy viết đủ ý và chọn source range phù hợp hơn thay vì bóp câu cho ngắn.")
        lines.append("- Tool render có thể đồng bộ voice/video sau đó, nên ưu tiên kịch bản tự nhiên, rõ ý và hấp dẫn trước khi tối ưu độ khít tuyệt đối.")
        lines.append("- Không tạo pattern máy móc kiểu mọi cảnh đều có thời lượng giống nhau hoặc lời dẫn dài/ngắn giống nhau.")
        lines.append("- Chỉ tránh cảnh dư vô nghĩa khi lời dẫn đã hết ý và hình ảnh không còn đóng góp cho câu chuyện.")
        lines.append("- Không để voiceover bị ép nhanh hoặc thiếu ý chỉ vì source_duration ban đầu quá ngắn.")
        lines.append("")
        lines.append("TỰ KIỂM TRA THỜI LƯỢNG TỪNG SEGMENT TRƯỚC KHI XUẤT JSON:")
        lines.append("- Với mỗi video_segments[i], tính source_duration = source_end - source_start.")
        lines.append("- Ước lượng voice_estimate của subtitle_start..subtitle_end theo nhịp đọc tự nhiên, không theo công thức số từ cứng.")
        lines.append("- Nếu lời dẫn cần nhiều thời gian hơn cảnh, ưu tiên mở rộng source range hoặc chọn cảnh phù hợp hơn trước khi rút ngắn câu.")
        lines.append("- Nếu cảnh dài hơn lời dẫn nhưng vẫn còn giá trị hình ảnh, có thể giữ để nhịp kể tự nhiên; chỉ cắt khi phần dư không còn giá trị.")
        lines.append("- Tránh lời dẫn tràn cảnh bằng cách chọn source range hợp lý, chia segment hợp lý hoặc viết lại cho rõ ý hơn, không cắt cụt ý.")
        lines.append("- Lời dẫn nên liên tục theo mạch cảm xúc và logic câu chuyện, tránh ngắt quãng vô lý.")
        lines.append("")
        lines.append(
            "video_segments phải được chia theo nhịp cảnh thật và giá trị dựng video,"
        )
        lines.append("không chia đều máy móc.")
        lines.append("")
        lines.append(
            "source_start và source_end phải bao phủ đủ các phần quan trọng của video"
        )
        lines.append("từ đầu đến cuối, không chỉ lấy phần mở đầu.")
        lines.append("")
        lines.append("Yêu cầu output:")
        lines.append("1. rewrite_script.full_text — toàn bộ kịch bản remake")
        lines.append(f"2. srt[] — subtitle với timing, viết bằng {data.target_language}")
        lines.append("3. video_segments[] — danh sách các đoạn cần lấy từ video nguồn")
        lines.append(f"4. metadata.video_title — tiêu đề mới bằng {data.target_language}")

        return "\n".join(lines)

    def compose(self) -> str:
        parts: list[str] = [
            self.compose_intro(),
        ]

        if self.data.domain == "sports":
            parts.append(DomainRulesBlock().render(self.data))

        lang = self.data.target_language or "Tiếng Việt"
        market = self.data.target_market or "Việt Nam"

        parts.extend([
            "VALIDATION CRITICAL — SELF-CHECK BEFORE OUTPUT:",
            "SEGMENT ALIGNMENT HARD RULES (Không được vi phạm):",
            "- source_start MUST be strictly before source_end.",
            "- subtitle_start MUST be <= subtitle_end.",
            "- subtitle_start và subtitle_end phải tham chiếu index có thực trong srt[].",
            "- Không map subtitle_start > subtitle_end.",
            "",
            "- For every video_segments item:",
            "    duration_video = source_end - source_start.",
            "    duration_srt = srt[subtitle_end].end - srt[subtitle_start].start.",
            "    abs(duration_video - duration_srt) MUST be <= 2 seconds.",
            "",
            "- Never map a short video segment to a long subtitle range.",
            "- Never map a long subtitle range to a short visual clip.",
            "- Before final output, scan every video_segments item and verify each alignment metric.",
            f"{self._subtitle_range_guard()}",
            "- Nếu lệch quá 2 giây, JSON sẽ bị reject trước khi render.",
            "- Do not rely on renderer to fix invalid JSON. The final JSON must pass validation before render.",
            "",
            "LANGUAGE METADATA HARD RULE:",
            f'- metadata.target_language MUST be exactly "{lang}".',
            f'- metadata.target_market MUST be exactly "{market}".',
            "- Do NOT output a language code or alternate spelling; copy the exact values above.",
            "- Nếu sai language/market, JSON sẽ bị reject trước khi render.",
            ValidationBlock().render(self.data),
            OutputSchemaBlock().render(self.data),
        ])
        return "\n\n".join(parts)

    @staticmethod
    def _subtitle_range_guard() -> str:
        return "\n".join([
            "SUBTITLE RANGE HARD CHECK:",
            "- For every video_segments[i], subtitle_start and subtitle_end are SRT index references.",
            "- subtitle_start MUST be <= subtitle_end.",
            "- If the segment uses exactly one subtitle, set subtitle_start = subtitle_end = that srt.index.",
            '- INVALID: {"subtitle_start": 25, "subtitle_end": 24}',
            '- VALID: {"subtitle_start": 24, "subtitle_end": 25} or {"subtitle_start": 25, "subtitle_end": 25}',
            "- Before returning JSON, scan all video_segments[] and fix any reversed subtitle range.",
            "- Do NOT return JSON if any video_segments item has subtitle_start > subtitle_end.",
        ])

    def compose_analysis(self) -> str:
        data = self.data
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        lines = [
            "PHÂN TÍCH SÂU — PASS 1: PHÂN TÍCH CẢNH VÀ THOẠI",
            "",
            "Bạn là đạo diễn phân tích video remake.",
            "Hãy xem toàn bộ nội dung từ các video YouTube sau:",
            source_block,
            "",
            "Nhiệm vụ pass này: CHỈ phân tích cảnh, thoại/narration và mạch nội dung để pass 2 viết voiceover + chọn cảnh remake.",
            "Không viết kịch bản final trong pass này.",
            "Không viết voiceover final, không tạo SRT, không tạo metadata/rewrite_script/video_segments final.",
            "Phân tích theo diễn biến thật của video, không theo quota cố định.",
            "Không bịa nội dung nếu không xem được link; nếu không xem được video, set source_access.can_access_video=false và không invent content.",
            "- Phân tích toàn bộ video từ đầu đến cuối, không chỉ phần mở đầu.",
            "- Bóc tách scene_beats theo nhịp câu chuyện/thao tác thật: opening, setup, progression, climax, ending, context, payoff.",
            "- Với sitcom, hài kịch, MV ca nhạc hoặc nội dung ngắn: vẫn phải tạo tối thiểu 10 scene_beats bằng cách tách các beat thoại/cảnh/quay riêng biệt, ngay cả khi nhiều cảnh xảy ra trong cùng một bối cảnh.",
            "- Mỗi scene beat phải ghi rõ hình ảnh đang thấy, thoại/narration chính nếu có, hành động quan trọng và vì sao đáng dùng trong remake.",
            "- Bắt buộc có beat ở phần cuối video nếu video có kết quả/final reveal/payoff.",
            "- must_keep_moments phải là timestamp cụ thể, ưu tiên khoảnh khắc visual rõ ràng.",
            "- youtube_url phải là URL thuần, không dùng markdown link.",
            "",
            "STRICT OUTPUT CONTRACT:",
            "- Return ONLY valid JSON. Ký tự đầu là {, cuối là }.",
            "- Không markdown, không code fence, không giải thích ngoài JSON.",
            "- Không thêm field ngoài schema dưới đây.",
            "- Timestamp video dùng HH:MM:SS.mmm.",
            "",
            "Schema bắt buộc:",
            "{",
            '  "analysis_version": 2,',
            '  "source_access": {"can_access_video": true, "reason": "string"},',
            f'  "source": {{"source_id": "source_1", "youtube_url": "{urls[0] if urls else ""}", "estimated_duration": "HH:MM:SS.mmm", "source_title": "string"}},',
            '  "story_summary": {"overall_summary": "string", "core_story": "string", "opening": "string", "middle": "string", "climax": "string", "ending": "string"},',
            '  "scene_beats": [',
            '    {"beat_id": "b001", "start": "00:00:00.000", "end": "00:01:07.000", "story_role": "opening/setup/progression/climax/ending/context/payoff", "visual_description": "string", "dialogue_or_narration": "string", "important_actions": ["string"], "why_it_matters": "string", "keep_priority": "high/medium/low", "remake_use": "hook/context/action/emotion/payoff/cut"}',
            "  ],",
            '  "must_keep_moments": [',
            '    {"timestamp": "00:00:00.000", "reason": "string"}',
            "  ],",
            '  "weak_or_repetitive_parts": [',
            '    {"start": "00:00:00.000", "end": "00:00:00.000", "reason": "string"}',
            "  ],",
            '  "quality_notes": ["string"]',
            "}",
        ]
        if data.user_instruction:
            lines.extend(["", "NGƯỜI DÙNG HƯỚNG DẪN THÊM:", data.user_instruction])
        return "\n".join(lines)

    @staticmethod
    def _truncate_text(value: object, limit: int) -> object:
        if not isinstance(value, str) or len(value) <= limit:
            return value
        return value[: limit - 3].rstrip() + "..."

    def _compact_analysis_json(self, analysis_json: dict) -> dict:
        if analysis_json.get("analysis_version") == 2 or isinstance(analysis_json.get("scene_beats"), list):
            compact_v2 = {
                "analysis_version": 2,
                "source_access": analysis_json.get("source_access", {}),
                "source": analysis_json.get("source", {}),
                "story_summary": analysis_json.get("story_summary", {}),
                "scene_beats": [],
                "must_keep_moments": analysis_json.get("must_keep_moments", [])[:40] if isinstance(analysis_json.get("must_keep_moments"), list) else [],
                "weak_or_repetitive_parts": analysis_json.get("weak_or_repetitive_parts", [])[:40] if isinstance(analysis_json.get("weak_or_repetitive_parts"), list) else [],
                "quality_notes": analysis_json.get("quality_notes", [])[:5] if isinstance(analysis_json.get("quality_notes"), list) else [],
            }
            beats = analysis_json.get("scene_beats", [])
            if isinstance(beats, list):
                for beat in beats:
                    if not isinstance(beat, dict):
                        continue
                    item = dict(beat)
                    item["visual_description"] = self._truncate_text(item.get("visual_description", ""), 520)
                    item["dialogue_or_narration"] = self._truncate_text(item.get("dialogue_or_narration", ""), 420)
                    item["why_it_matters"] = self._truncate_text(item.get("why_it_matters", ""), 260)
                    compact_v2["scene_beats"].append(item)
            return compact_v2
        compact = {
            "analysis_version": analysis_json.get("analysis_version", 1),
            "sources": analysis_json.get("sources", []),
            "overall_summary": self._truncate_text(analysis_json.get("overall_summary", ""), 900),
            "story_arc": analysis_json.get("story_arc", {}),
            "segments": [],
            "must_keep_moments": analysis_json.get("must_keep_moments", [])[:30] if isinstance(analysis_json.get("must_keep_moments"), list) else [],
            "weak_or_repetitive_parts": analysis_json.get("weak_or_repetitive_parts", [])[:30] if isinstance(analysis_json.get("weak_or_repetitive_parts"), list) else [],
            "quality_notes": analysis_json.get("quality_notes", [])[:5] if isinstance(analysis_json.get("quality_notes"), list) else [],
        }
        segments = analysis_json.get("segments", [])
        if isinstance(segments, list):
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                item = dict(segment)
                item["description"] = self._truncate_text(item.get("description", ""), 700)
                compact["segments"].append(item)
        return compact

    @staticmethod
    def _compact_story_plan_json(story_plan_json: dict) -> dict:
        compact = dict(story_plan_json)
        selected = compact.get("selected_moments", [])
        if isinstance(selected, list):
            compact["selected_moments"] = selected[:60]
        notes = compact.get("quality_notes", [])
        if isinstance(notes, list):
            compact["quality_notes"] = notes[:5]
        return compact

    @staticmethod
    def _json_compact(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _compact_chapter_analyses(chapter_analyses: list[dict]) -> list[dict]:
        compact: list[dict] = []
        for analysis in chapter_analyses:
            item = dict(analysis)
            beats = item.get("beats", [])
            compact_beats: list[dict] = []
            if isinstance(beats, list):
                for beat in beats:
                    if not isinstance(beat, dict):
                        continue
                    beat_item = dict(beat)
                    for key in ("visual_action", "what_changes_on_screen", "why_it_may_matter", "notes_for_voiceover"):
                        if isinstance(beat_item.get(key), str) and len(beat_item[key]) > 420:
                            beat_item[key] = beat_item[key][:417].rstrip() + "..."
                    compact_beats.append(beat_item)
            item["beats"] = compact_beats
            compact.append(item)
        return compact

    @staticmethod
    def _beat_catalog(chapter_analyses: list[dict]) -> list[dict]:
        catalog: list[dict] = []
        for analysis in chapter_analyses:
            chapter_index = analysis.get("chapter_index")
            for beat in analysis.get("beats", []) if isinstance(analysis.get("beats"), list) else []:
                if not isinstance(beat, dict):
                    continue
                catalog.append({
                    "chapter_index": chapter_index,
                    "beat_index": beat.get("beat_index"),
                    "start": beat.get("start"),
                    "end": beat.get("end"),
                    "role": beat.get("story_role"),
                    "keep": beat.get("keep_potential"),
                    "visual": PromptComposer._truncate_text(beat.get("visual_action", ""), 180),
                    "change": PromptComposer._truncate_text(beat.get("what_changes_on_screen", ""), 160),
                })
        return catalog

    def compose_timeline_scout(self) -> str:
        data = self.data
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        lines = [
            "PHÂN TÍCH SÂU FULL — PASS 1: TIMELINE SCOUT",
            "",
            "Bạn là đạo diễn phân tích cấu trúc video trước khi remake.",
            "Hãy xem toàn bộ video nhưng chỉ tạo bản đồ timeline cấp chapter.",
            "Không viết script, không tạo SRT, không tạo final EDL, không chọn cảnh final.",
            "Mục tiêu là chia nhỏ video thành các chapter tự nhiên để các pass sau phân tích từng phần sâu hơn.",
            "Nguồn video:",
            source_block,
            "",
            "QUY TẮC:",
            "- Chia chapter theo mạch thật của video, không chia đều máy móc.",
            "- Mỗi chapter phải có start/end rõ ràng, summary và analysis_instruction cho pass sau.",
            "- Với video dài, chia đủ sâu nhưng giữ gọn: ưu tiên 6-8 chapter chính, tối đa 9 chapter.",
            "- Không bịa nếu không xem được video; ghi rõ trong quality_notes.",
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON, no markdown, no code fence.",
            "Schema:",
            "{",
            '  "timeline_version": 1,',
            '  "source_id": "source_1",',
            f'  "youtube_url": "{urls[0] if urls else ""}",',
            '  "estimated_duration": "HH:MM:SS.mmm",',
            '  "chapters": [',
            '    {"chapter_index": 1, "start": "00:00:00.000", "end": "00:04:30.000", "story_role": "setup/progression/climax/ending/context", "summary": "string", "analysis_instruction": "string"}',
            "  ],",
            '  "quality_notes": ["string"]',
            "}",
        ]
        if data.user_instruction:
            lines.extend(["", "NGƯỜI DÙNG HƯỚNG DẪN THÊM:", data.user_instruction])
        return "\n".join(lines)

    def compose_chapter_analysis(self, timeline_json: dict, chapter: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — PASS 2: CHAPTER ANALYSIS",
            "",
            "Bạn chỉ phân tích chapter được chỉ định. Không viết final script, không tạo EDL.",
            "Bóc tách chapter thành visual beats cụ thể để pass sau chọn cảnh và viết voiceover khớp hình.",
            "Giữ gọn: mỗi chapter nên có 3-5 beats quan trọng nhất, không liệt kê mọi micro-action.",
            "Mỗi beat phải nói rõ hình ảnh/hành động đang thấy và điều gì thay đổi trên màn hình.",
            "",
            "REQUESTED_CHAPTER:",
            self._json_compact(chapter),
            "",
            "TIMELINE_JSON:",
            self._json_compact(timeline_json),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON, no markdown, no code fence.",
            "Schema:",
            "{",
            '  "chapter_analysis_version": 1,',
            '  "source_id": "source_1",',
            '  "chapter_index": 1,',
            '  "chapter_start": "00:00:00.000",',
            '  "chapter_end": "00:04:30.000",',
            '  "beats": [',
            '    {"beat_index": 1, "start": "00:00:08.000", "end": "00:00:28.000", "story_role": "hook/setup/progression/climax/ending/context", "visual_action": "string", "what_changes_on_screen": "string", "why_it_may_matter": "string", "emotional_or_story_value": "string", "keep_potential": "high/medium/low", "notes_for_voiceover": "string"}',
            "  ],",
            '  "chapter_summary": "string",',
            '  "quality_notes": ["string"]',
            "}",
        ])

    def compose_coverage_review(self, timeline_json: dict, chapter_analyses: list[dict]) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — PASS 3: COVERAGE REVIEW",
            "",
            "Bạn là reviewer chất lượng phân tích. Hãy đánh giá timeline + chapter analyses đã đủ dữ liệu để dựng remake chất lượng chưa.",
            "Nếu thiếu, chỉ rõ chapter cần phân tích lại và retry_instruction cụ thể. Không viết final script.",
            "",
            "TIMELINE_CHAPTERS:",
            self._json_compact(timeline_json.get("chapters", [])),
            "",
            "BEAT_CATALOG:",
            self._json_compact(self._beat_catalog(chapter_analyses)),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "coverage_review_version": 1,',
            '  "passed": true,',
            '  "overall_assessment": "string",',
            '  "coverage_quality": "strong/acceptable/weak",',
            '  "missing_or_weak_chapters": [{"chapter_index": 1, "problem": "string", "retry_instruction": "string"}],',
            '  "important_story_threads": ["string"],',
            '  "must_not_lose_context": ["string"],',
            '  "quality_notes": ["string"]',
            "}",
        ])

    def compose_edit_strategy(self, timeline_json: dict, chapter_analyses: list[dict], coverage_review: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — PASS 4: DURATION & EDIT STRATEGY",
            "",
            "Bạn là đạo diễn dựng. Hãy tự đề xuất độ dài remake tối ưu và chiến lược chọn cảnh.",
            "Không bị ép theo công thức; hãy cân bằng đủ ý, hấp dẫn, không quá dài, không quá nông.",
            "Nếu video dài nhưng output ngắn, phải giải thích vì sao vẫn đủ ý.",
            "",
            "TIMELINE_JSON:",
            self._json_compact(timeline_json),
            "",
            "COVERAGE_REVIEW_JSON:",
            self._json_compact(coverage_review),
            "",
            "CHAPTER_ANALYSES_JSON_COMPACT:",
            self._json_compact(self._compact_chapter_analyses(chapter_analyses)),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "edit_strategy_version": 1,',
            '  "recommended_duration_seconds": 420,',
            '  "min_acceptable_duration_seconds": 330,',
            '  "max_acceptable_duration_seconds": 540,',
            '  "strategy_summary": "string",',
            '  "pacing_style": "string",',
            '  "selection_principles": ["string"],',
            '  "chapter_priorities": [{"chapter_index": 1, "priority": "high/medium/low", "reason": "string", "suggested_screen_time_seconds": 40}],',
            '  "risks_if_too_short": ["string"],',
            '  "risks_if_too_long": ["string"]',
            "}",
        ])

    def compose_story_assembly(self, timeline_json: dict, chapter_analyses: list[dict], coverage_review: dict, strategy: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — PASS 5: STORY ASSEMBLY",
            "",
            "Bạn là đạo diễn dựng. Hãy chọn beats tốt nhất để tạo remake hấp dẫn, đủ mạch và không mất ngữ cảnh.",
            "Chưa viết SRT final. Chỉ lập assembly plan cho các chunk sau.",
            "",
            "EDIT_STRATEGY_JSON:",
            self._json_compact(strategy),
            "",
            "COVERAGE_REVIEW_JSON:",
            self._json_compact(coverage_review),
            "",
            "TIMELINE_JSON:",
            self._json_compact(timeline_json),
            "",
            "CHAPTER_ANALYSES_JSON_COMPACT:",
            self._json_compact(self._compact_chapter_analyses(chapter_analyses)),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "assembly_version": 1,',
            '  "target_duration_seconds": 420,',
            '  "selected_beats": [',
            '    {"selection_index": 1, "chapter_index": 1, "beat_index": 2, "source_start_hint": "00:00:12.000", "source_end_hint": "00:00:30.000", "story_purpose": "hook/setup/progression/climax/ending", "voiceover_intent": "string", "visual_requirement": "string", "estimated_screen_time_seconds": 18}',
            "  ],",
            '  "story_flow": ["opening", "setup", "progression", "climax", "ending"],',
            '  "why_this_selection_works": "string",',
            '  "quality_notes": ["string"]',
            "}",
        ])

    def compose_director_plan(self, timeline_json: dict, chapter_analyses: list[dict]) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — DIRECTOR PLAN",
            "",
            "Bạn là đạo diễn dựng. Dựa trên timeline và beat catalog, hãy gộp 3 việc trong một lần:",
            "1. Đánh giá coverage có đủ dữ liệu dựng chưa.",
            "2. Tự chọn độ dài/chiến lược dựng tối ưu.",
            "3. Chọn beats vào bản dựng final.",
            "Không viết SRT/EDL final trong pass này.",
            "Tool chỉ chia task; quyết định độ dài/chọn cảnh là của bạn, nhưng phải giải thích đủ rõ.",
            "",
            "TIMELINE_CHAPTERS:",
            self._json_compact(timeline_json.get("chapters", [])),
            "",
            "BEAT_CATALOG_COMPACT:",
            self._json_compact(self._beat_catalog(chapter_analyses)),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "director_plan_version": 1,',
            '  "coverage_assessment": {"passed": true, "overall_assessment": "string", "missing_context": ["string"], "important_story_threads": ["string"]},',
            '  "edit_strategy": {"recommended_duration_seconds": 420, "min_acceptable_duration_seconds": 330, "max_acceptable_duration_seconds": 540, "strategy_summary": "string", "pacing_style": "string", "selection_principles": ["string"]},',
            '  "selected_beats": [',
            '    {"selection_index": 1, "chapter_index": 1, "beat_index": 2, "source_start_hint": "00:00:12.000", "source_end_hint": "00:00:30.000", "story_purpose": "hook/setup/progression/climax/ending", "voiceover_intent": "string", "visual_requirement": "string", "estimated_screen_time_seconds": 18}',
            "  ],",
            '  "story_flow": ["opening", "middle", "climax", "ending"],',
            '  "why_this_selection_works": "string",',
            '  "quality_notes": ["string"]',
            "}",
        ])

    def compose_final_chunk(self, chunk_name: str, selected_beats: list[dict], chapter_analyses: list[dict], strategy: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — PASS 6: FINAL EDL CHUNK",
            "",
            f"Chỉ tạo EDL cho chunk: {chunk_name}.",
            f"Viết bằng {self.data.target_language}. Không tạo toàn bộ video, chỉ chunk này.",
            "Chỉ dùng selected beats của chunk này và chapter analysis liên quan.",
            "Giữ chunk ngắn gọn, không viết quá dài trong một lần; chunk chỉ cần đủ phần được giao.",
            "Mỗi câu voiceover phải khớp cảnh đang hiển thị. Không summarize cảnh chưa xuất hiện.",
            "Không thêm field ngoài schema chunk.",
            "",
            "EDIT_STRATEGY_JSON:",
            self._json_compact(strategy),
            "",
            "SELECTED_BEATS_FOR_THIS_CHUNK:",
            self._json_compact(selected_beats),
            "",
            "RELEVANT_CHAPTER_ANALYSES_JSON:",
            self._json_compact(self._compact_chapter_analyses(chapter_analyses)),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "chunk_version": 1,',
            f'  "chunk_name": "{chunk_name}",',
            '  "rewrite_text": "string",',
            '  "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:05,000", "text": "string"}],',
            '  "video_segments": [{"source_id": "source_1", "source_start": "00:00:12.000", "source_end": "00:00:17.000", "subtitle_start": 1, "subtitle_end": 1, "scene_description": "visual cụ thể đang khớp voiceover", "importance_score": 90}]',
            "}",
        ])

    def compose_alignment_audit(self, final_payload: dict, timeline_json: dict, chapter_analyses: list[dict], strategy: dict, assembly: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — PASS 7: ALIGNMENT AUDIT",
            "",
            "Bạn là final reviewer. Đánh giá final JSON có đủ ý, đúng mạch, voiceover khớp cảnh không.",
            "Nếu fail, chỉ ra chunk/segment cần sửa. Nếu đạt, cho render.",
            "",
            "FINAL_JSON:",
            self._json_compact(final_payload),
            "",
            "EDIT_STRATEGY_JSON:",
            self._json_compact(strategy),
            "",
            "ASSEMBLY_JSON:",
            self._json_compact(assembly),
            "",
            "TIMELINE_JSON:",
            self._json_compact(timeline_json),
            "",
            "RELEVANT_CHAPTER_ANALYSES_JSON:",
            self._json_compact(self._compact_chapter_analyses(chapter_analyses)),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "alignment_audit_version": 1,',
            '  "passed": true,',
            '  "overall_quality": "strong/acceptable/weak",',
            '  "duration_quality": "good/too_short/too_long",',
            '  "coverage_quality": "good/missing_context/missing_ending/too_shallow",',
            '  "scene_voice_alignment": "good/mixed/poor",',
            '  "issues": [{"severity": "high/medium/low", "chunk_name": "progression", "segment_index": 3, "problem": "string", "repair_instruction": "string"}],',
            '  "final_recommendation": "render/repair/stop"',
            "}",
        ])

    def compose_compact_alignment_audit(self, final_payload: dict, director_plan: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — COMPACT ALIGNMENT AUDIT",
            "",
            "Bạn là final reviewer. Dùng DIRECTOR_PLAN và FINAL_JSON để quyết định render/repair/stop.",
            "Kiểm tra: đủ ý theo plan, độ dài hợp lý, voiceover khớp cảnh, không mất ending/payoff.",
            "",
            "DIRECTOR_PLAN_JSON:",
            self._json_compact(director_plan),
            "",
            "FINAL_JSON:",
            self._json_compact(final_payload),
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            "Schema:",
            "{",
            '  "alignment_audit_version": 1,',
            '  "passed": true,',
            '  "overall_quality": "strong/acceptable/weak",',
            '  "duration_quality": "good/too_short/too_long",',
            '  "coverage_quality": "good/missing_context/missing_ending/too_shallow",',
            '  "scene_voice_alignment": "good/mixed/poor",',
            '  "issues": [{"severity": "high/medium/low", "chunk_name": "chunk_1", "segment_index": 3, "problem": "string", "repair_instruction": "string"}],',
            '  "final_recommendation": "render/repair/stop"',
            "}",
        ])

    def compose_source_access_check(self) -> str:
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        return "\n".join([
            "GEMINI SOURCE ACCESS CHECK",
            "",
            "Hãy kiểm tra bạn có xem/truy cập được nội dung video YouTube dưới đây không.",
            "Không phân tích nội dung. Chỉ trả JSON ngắn.",
            source_block,
            "",
            "STRICT OUTPUT CONTRACT: Return ONLY valid JSON.",
            '{"source_access_version":1,"can_access_video":true,"reason":"string"}',
        ])

    def compose_repair_chunk(self, chunk_name: str, previous_chunk: dict, audit_json: dict, selected_beats: list[dict], chapter_analyses: list[dict], strategy: dict) -> str:
        return "\n".join([
            "PHÂN TÍCH SÂU FULL — REPAIR CHUNK ONCE",
            "",
            f"Chỉ sửa chunk: {chunk_name}. Không viết lại toàn bộ video.",
            "Sửa theo audit issues, giữ schema chunk, giữ strategy và selected beats.",
            "",
            "AUDIT_JSON:",
            self._json_compact(audit_json),
            "",
            "PREVIOUS_CHUNK_JSON:",
            self._json_compact(previous_chunk),
            "",
            "EDIT_STRATEGY_JSON:",
            self._json_compact(strategy),
            "",
            "SELECTED_BEATS_FOR_THIS_CHUNK:",
            self._json_compact(selected_beats),
            "",
            "CHAPTER_ANALYSES_JSON:",
            self._json_compact(self._compact_chapter_analyses(chapter_analyses)),
            "",
            "Return ONLY repaired chunk JSON with the same schema as FINAL EDL CHUNK.",
        ])

    def compose_story_plan_from_analysis(self, analysis_json: dict) -> str:
        analysis_text = json.dumps(self._compact_analysis_json(analysis_json), ensure_ascii=False, separators=(",", ":"))
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        return "\n".join([
            "PHÂN TÍCH SÂU — PASS 2A: LẬP STORY PLAN / EDITING BLUEPRINT",
            "",
            "Bạn là đạo diễn dựng lại video từ bản phân tích nguồn.",
            "Hãy dùng ANALYSIS_JSON để quyết định mạch kể, cảnh cần giữ, cảnh cần bỏ và điểm neo timestamp.",
            "Chưa viết SRT, chưa tạo final video_segments, chưa tạo metadata/rewrite_script final.",
            "Chỉ trả JSON story plan nhỏ gọn để pass cuối xuất EDL nhanh hơn.",
            "Nguồn video:",
            source_block,
            "",
            "STRICT OUTPUT CONTRACT:",
            "- Return ONLY valid JSON. Ký tự đầu là {, cuối là }.",
            "- Không markdown, không code fence, không giải thích ngoài JSON.",
            "- Không thêm field ngoài schema dưới đây.",
            "- timestamp_hint dùng HH:MM:SS.mmm và phải bám các timestamp/range trong analysis.",
            "",
            "Schema bắt buộc:",
            "{",
            '  "plan_version": 1,',
            '  "story_outline": ["string"],',
            '  "selected_moments": [',
            '    {"source_id": "source_1", "analysis_index": 1, "timestamp_hint": "00:00:00.000", "purpose": "hook/setup/progression/climax/ending/payoff", "voiceover_point": "string"}',
            "  ],",
            '  "target_structure": {"opening": "string", "middle": "string", "climax": "string", "ending": "string"},',
            '  "quality_notes": ["string"]',
            "}",
            "",
            "ANALYSIS_JSON:",
            analysis_text,
        ])

    def compose_from_analysis(self, analysis_json: dict) -> str:
        analysis_text = json.dumps(self._compact_analysis_json(analysis_json), ensure_ascii=False, separators=(",", ":"))
        parts = [
            self.compose_intro(),
            "PHÂN TÍCH SÂU — PASS 2: TẠO JSON FINAL TỪ BẢN PHÂN TÍCH",
            "",
            "Dưới đây là bản phân tích cảnh + thoại/narration của video nguồn từ pass 1. Hãy dùng nó làm bản đồ dựng video.",
            "Không bỏ qua opening/setup/progression/climax/ending/payoff nếu bản phân tích có các phần đó.",
            "Hãy viết voiceover thật hay, tự nhiên, hấp dẫn bằng ngôn ngữ đích; không biến scene_beats thành danh sách tóm tắt khô.",
            "Số lượng srt[] và video_segments[] do bạn tự quyết định theo độ phức tạp của bản dựng final, không theo quota cố định.",
            "",
            "TTS-SAFE SUBTITLE RULE (Không được vi phạm):",
            "- Vietnamese voiceover phải đọc được bởi TTS ở tốc độ tự nhiên.",
            "- Target CPS: 5-8 characters/giây. Soft max: 10 CPS. Hard max: 12 CPS.",
            "- Target 80-120 ký tự tiếng Việt cho mỗi 7-10 giây slot.",
            "- Nếu một ý quá dày, tách thành nhiều SRT cues nối tiếp thay vì gộp chung.",
            "- Không nén nhiều dữ kiện, tên người, số liệu vào một subtitle.",
            "- Ưu tiên nhiều SRT ngắn hơn là ít SRT nhưng mỗi cái dày đặc.",
            "",
            "Nếu cần khớp cảnh-lời tốt hơn, hãy tách lời dẫn thành nhiều SRT/segment nhỏ hơn thay vì gộp nhiều thao tác vào một subtitle dài.",
            "Phải có ít nhất một segment từ phần cuối/final reveal/final test/payoff nếu analysis có ending hoặc climax ở cuối video.",
            "Chỉ chọn cảnh từ các timestamp đã phân tích hoặc nằm trong range hợp lý của scene_beats/segments phân tích.",
            "Với video dài, không rút thành bản 1-2 phút nếu người dùng không yêu cầu short-form.",
            "Không dùng markdown link trong sources[].youtube_url.",
            "Không tự thêm field phụ như source_start_ms, source_end_ms, duration_ms, duration_seconds hoặc bất kỳ field nào ngoài schema.",
            "",
            "CÁCH DÙNG ANALYSIS_JSON:",
            "1. Dùng story_summary/story_arc để giữ mạch tổng thể.",
            "2. Dùng scene_beats[] hoặc segments[] để chọn các cảnh cần xuất hiện trong final.",
            "3. Dùng dialogue_or_narration để hiểu lời thoại/nội dung gốc, nhưng hãy viết lại thành voiceover remake hay hơn.",
            "4. Dùng must_keep_moments[] làm điểm neo timestamp cho các khoảnh khắc quan trọng.",
            "5. Dùng weak_or_repetitive_parts[] để tránh chọn các đoạn lặp dài không có giá trị.",
            "6. Khi viết srt.text, mỗi câu phải có video_segment tương ứng đang hiển thị đúng hành động/cảnh mà câu đó nói tới.",
            "",
            "QUY TẮC KHỚP CẢNH VỚI LỜI DẪN:",
            "- Dùng analysis như bản đồ dựng cảnh, nhưng vẫn phải đối chiếu video gốc khi chọn timestamp final.",
            "- Không copy nguyên range của analysis segment làm final video_segment nếu subtitle chỉ nói về một phần nhỏ trong range đó.",
            "- Final video_segments[].source_start/source_end phải là đoạn hình cụ thể khớp trực tiếp với srt.text được tham chiếu.",
            "- Final video_segments[].source_start/source_end nên có thời lượng gần với tổng thời lượng SRT được tham chiếu.",
            "- Có thể dài hơn nếu hình ảnh còn giá trị rõ ràng như thao tác đang hoàn tất, ASMR quan trọng, reveal, reaction hoặc transition.",
            "- Nếu source range dài hơn lời dẫn đáng kể mà không có giá trị visual rõ, hãy rút ngắn source range hoặc tách segment.",
            "- Không chọn clip dài chỉ vì analysis segment dài.",
            "- Nếu subtitle nói về thao tác nào, cảnh phải đang hiển thị đúng thao tác đó.",
            "- Mỗi video_segment chỉ nên tham chiếu subtitle nói về cùng một visual beat.",
            "- Nếu một subtitle chứa hai thao tác không nằm trong cùng đoạn hình liên tục, hãy tách subtitle hoặc tách video_segment.",
            "- scene_description phải mô tả đúng visual trong đoạn cắt cuối cùng, không mô tả chung cả analysis segment.",
            "",
            "ANALYSIS_JSON:",
            analysis_text,
        ]

        if self.data.domain == "sports":
            parts.append(DomainRulesBlock().render(self.data))

        parts.extend([
            "VALIDATION CRITICAL — SELF-CHECK BEFORE OUTPUT:\n"
            "- For every video_segments item, calculate duration_video = source_end - source_start.\n"
            "- Calculate duration_srt = srt[subtitle_end].end - srt[subtitle_start].start.\n"
            "- If abs(duration_video - duration_srt) > 2 seconds, fix source_start/source_end or SRT timing before returning JSON.\n"
            f"{self._subtitle_range_guard()}\n"
            "- Nếu lệch quá 2 giây, JSON sẽ bị reject trước khi render.\n"
            "- Do not rely on renderer to fix invalid JSON. The final JSON must pass validation before render.",
            ValidationBlock().render(self.data),
            OutputSchemaBlock().render(self.data),
        ])
        return "\n\n".join(parts)

    def compose_from_story_plan(self, analysis_json: dict, story_plan_json: dict) -> str:
        analysis_text = json.dumps(self._compact_analysis_json(analysis_json), ensure_ascii=False, separators=(",", ":"))
        story_plan_text = json.dumps(self._compact_story_plan_json(story_plan_json), ensure_ascii=False, separators=(",", ":"))
        urls = self._source_urls()
        source_block = "\n".join(f"{index}. {url}" for index, url in enumerate(urls, start=1))
        parts = [
            "PHÂN TÍCH SÂU — PASS 2B: TẠO JSON FINAL TỪ STORY PLAN",
            "",
            "Bạn là biên kịch remake video và editor EDL. Hãy tạo JSON final đúng schema để render video.",
            "Nguồn video:",
            source_block,
            "",
            "Dùng STORY_PLAN_JSON làm quyết định dựng chính; dùng ANALYSIS_JSON làm bản đồ timestamp để chọn source_start/source_end cụ thể.",
            "Không phân tích lại toàn bộ từ đầu. Không tạo thêm field ngoài schema.",
            "Mỗi srt.text phải có video_segment tương ứng đang hiển thị đúng cảnh/thao tác mà câu đó nói tới.",
            "Nếu một câu chứa nhiều thao tác/cảnh khác nhau, tách thành nhiều SRT hoặc video_segment nhỏ hơn.",
            "Final video_segments[].source_start/source_end nên gần duration SRT nhưng có thể dài hơn nếu visual còn giá trị rõ.",
            "Không để source_end - source_start dài hơn duration của subtitle được tham chiếu quá 2 giây; nếu cần giữ hình lâu hơn, hãy kéo dài SRT timing tương ứng hoặc tách segment.",
            "Nếu source range dài hơn lời dẫn đáng kể mà không có visual payoff rõ, rút ngắn source_end để JSON validate trước khi render.",
            "Không dùng markdown link trong sources[].youtube_url.",
            "",
            "STORY_PLAN_JSON:",
            story_plan_text,
            "",
            "ANALYSIS_JSON:",
            analysis_text,
        ]

        if self.data.domain == "sports":
            parts.append(DomainRulesBlock().render(self.data))

        parts.extend([
            "VALIDATION CRITICAL — SELF-CHECK BEFORE OUTPUT:\n"
            "- For every video_segments item, calculate duration_video = source_end - source_start.\n"
            "- Calculate duration_srt = srt[subtitle_end].end - srt[subtitle_start].start.\n"
            "- If abs(duration_video - duration_srt) > 2 seconds, fix source_start/source_end or SRT timing before returning JSON.\n"
            f"{self._subtitle_range_guard()}\n"
            "- Nếu lệch quá 2 giây, JSON sẽ bị reject trước khi render.\n"
            "- Do not rely on renderer to fix invalid JSON. The final JSON must pass validation before render.",
            ValidationBlock().render(self.data),
            OutputSchemaBlock().render(self.data),
        ])
        return "\n\n".join(parts)
