from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock


class DomainRulesBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
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
