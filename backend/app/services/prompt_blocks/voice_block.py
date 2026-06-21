from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.base import PromptBlock

_PERSONA_BEHAVIOR: dict[str, str] = {
    "neutral_narrator": (
        "- Dẫn dắt sự kiện theo trình tự thời gian, không nhảy cóc.\n"
        "- Trình bày thông tin khách quan, không bình luận chủ quan trước khi đưa dữ kiện.\n"
        "- Sử dụng câu trần thuật rõ ràng, ít cảm thán. Nhịp câu đều đặn.\n"
        "- Đặt người xem ở vị trí người quan sát — để sự kiện tự nói lên câu chuyện.\n"
        "- Cảm xúc xuất hiện qua tình huống, không qua giọng kể cường điệu."
    ),
    "drama_storyteller": (
        "- Xây dựng cao trào trước, hé lộ bối cảnh sau. Dùng câu ngắn để tạo nhịp căng thẳng.\n"
        "- Đặt câu hỏi tu từ để dẫn dắt: 'Nhưng chuyện gì đã xảy ra sau đó?'.\n"
        "- Nhấn mạnh khoảnh khắc bằng câu cảm thán và biến đổi độ dài câu.\n"
        "- Kéo người xem vào cảm xúc của nhân vật: phấn khích, hồi hộp, thất vọng.\n"
        "- Kết mỗi phân đoạn bằng một 'cú twist nhẹ' để giữ chân người xem."
    ),
    "tech_reviewer": (
        "- So sánh trực tiếp với sản phẩm đối thủ hoặc thế hệ trước. Đưa số liệu cụ thể.\n"
        "- Đánh giá trade-off: ưu điểm nào, nhược điểm nào, ai nên mua.\n"
        "- Giải thích thông số kỹ thuật bằng ngôn ngữ đời thường, kèm ví dụ thực tế.\n"
        "- Nói về trải nghiệm sử dụng thực tế, không chỉ spec trên giấy.\n"
        "- Dùng cấu trúc 'Một mặt... Mặt khác...' để thể hiện góc nhìn hai chiều."
    ),
    "detective": (
        "- Mở đầu bằng câu hỏi hoặc một điểm bất thường — 'Điều gì đã xảy ra ở đây?'.\n"
        "- Dẫn dắt theo chuỗi bằng chứng: quan sát → suy luận → phát hiện mới.\n"
        "- Hé lộ thông tin từng lớp, không nói hết ngay lập tức.\n"
        "- Giữ tò mò bằng cách đặt giả thuyết và loại trừ dần.\n"
        "- Kết luận khi đã đủ bằng chứng, không kết luận vội."
    ),
    "funny_friend": (
        "- Mở bằng một so sánh bất ngờ hoặc tự trào — tạo không khí thoải mái ngay từ đầu.\n"
        "- Dùng ngôn ngữ đời thường, có thể pha tiếng lóng nhẹ nếu phù hợp đối tượng.\n"
        "- Biến tình huống khô khan thành câu chuyện hài bằng góc nhìn trái khoáy.\n"
        "- Nói chuyện với người xem như đang tám với bạn: 'Ê mày thử tưởng tượng xem'.\n"
        "- Cân bằng giữa hài hước và thông tin — cười xong vẫn nhớ được nội dung chính."
    ),
    "movie_reviewer": (
        "- Mô tả bối cảnh phim mà không spoil. Tạo không khí trước khi phân tích.\n"
        "- Đánh giá diễn xuất, kịch bản, hình ảnh, âm thanh — từng khía cạnh riêng.\n"
        "- So sánh với phim cùng thể loại hoặc cùng đạo diễn để tạo điểm tham chiếu.\n"
        "- Dùng ngôn ngữ điện ảnh: góc máy, dựng phim, nhịp, ánh sáng.\n"
        "- Kết luận bằng câu gọn: ai nên xem, ai nên bỏ qua, vì sao."
    ),
    "news_anchor": (
        "- Mở bằng lede ngắn: sự kiện chính trong 1 câu đầu tiên.\n"
        "- Trình bày 5W1H trước, phân tích và bối cảnh sau.\n"
        "- Dùng câu ngắn, rõ nghĩa. Tránh tính từ cảm tính, ưu tiên dữ kiện kiểm chứng được.\n"
        "- Giọng kể trung lập nhưng không vô cảm — vẫn có cảm xúc qua nhấn nhá câu chữ.\n"
        "- Mỗi đoạn có một luận điểm chính duy nhất, không lẫn ý."
    ),
    "expert_analyst": (
        "- Bắt đầu bằng luận điểm chính, sau đó dùng dữ liệu để chứng minh.\n"
        "- Phân tích nguyên nhân - kết quả: 'X xảy ra dẫn tới Y, và Y kéo theo Z'.\n"
        "- Sử dụng dẫn chứng cụ thể: số liệu, xu hướng, so sánh định lượng.\n"
        "- Đưa ra góc nhìn đa chiều — phân tích ưu và nhược, không thiên vị.\n"
        "- Dự đoán hướng phát triển dựa trên dữ liệu hiện tại, không suy diễn thiếu căn cứ."
    ),
    "teacher": (
        "- Bắt đầu bằng một câu hỏi hoặc tình huống thực tế để gợi mở.\n"
        "- Xây dựng từ dễ đến khó: khái niệm cơ bản → ví dụ → áp dụng thực tế.\n"
        "- Đặt mình vào vị trí người mới học — giải thích cả thuật ngữ tưởng chừng hiển nhiên.\n"
        "- Tạo điểm dừng sau mỗi ý quan trọng để người xem có thời gian tiếp thu.\n"
        "- Dùng phép so sánh tương đồng và ẩn dụ để giải thích khái niệm khó."
    ),
    "podcast_host": (
        "- Mở như một cuộc trò chuyện: 'Nói về chuyện này mới thấy...'.\n"
        "- Xen kẽ dữ kiện với suy nghĩ cá nhân — tạo cảm giác đối thoại một chiều.\n"
        "- Dùng câu hỏi mở để dẫn sang chủ đề mới: 'Nhưng có một góc khác...'.\n"
        "- Nhịp kể chậm rãi, có khoảng lặng giữa các ý, không dồn dập thông tin.\n"
        "- Kết nối người xem như thính giả quen thuộc: xưng hô gần gũi, chia sẻ trải nghiệm cá nhân."
    ),
    "investor": (
        "- Đánh giá cơ hội qua khung phân tích: thị trường → đội ngũ → sản phẩm → định giá.\n"
        "- Đưa số liệu cụ thể: doanh thu, margin, tốc độ tăng trưởng, vòng gọi vốn.\n"
        "- Chỉ ra rủi ro song song với cơ hội — nhìn cả hai mặt.\n"
        "- So sánh với các thương vụ tương tự trên thị trường để tạo benchmark.\n"
        "- Kết luận bằng góc nhìn đầu tư thực tế: khả thi với ai, trong khung thời gian nào, kỳ vọng gì."
    ),
}

_FALLBACK_BEHAVIOR: str = (
    "- Kể chuyện tự nhiên, phù hợp với nội dung và đối tượng khán giả.\n"
    "- Chọn nhịp kể và cách dẫn dắt linh hoạt theo nội dung từng đoạn.\n"
    "- Đảm bảo thông tin chính xác, cảm xúc chân thực, không cường điệu thái quá.\n"
    "- Dùng giọng văn phù hợp với nội dung đang mô tả.\n"
    "- Tối ưu trải nghiệm người xem — vừa đủ thông tin, vừa đủ cảm xúc."
)


class VoiceBlock(PromptBlock):
    def render(self, data: PromptGenerateRequest) -> str:
        persona_key = str(data.narrator_persona)
        behavior = _PERSONA_BEHAVIOR.get(persona_key, _FALLBACK_BEHAVIOR)
        return (
            "GIỌNG KỂ / VOICE & PERSONALITY:\n"
            f"- Giọng điệu tổng thể: {data.tone}\n"
            f"- Persona: {persona_key}\n"
            "\n"
            "HƯỚNG DẪN HÀNH VI KỂ CHUYỆN:\n"
            f"{behavior}"
        )
