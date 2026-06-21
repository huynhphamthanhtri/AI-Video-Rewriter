import { BookOpen, Brain, Clock, Flame, Gauge, Globe2, Languages, Megaphone, Repeat, Scissors, Users } from 'lucide-react';

export const optionGroups = {
  rewrite_style: { label: 'Phong cách viết lại', icon: BookOpen, values: ['Giữ nguyên phong cách gốc', 'Chuyên gia phân tích', 'Storytelling', 'Viral', 'Drama', 'Hài hước', 'Truyền cảm hứng', 'Podcast', 'Documentary', 'Điều tra', 'Tin tức', 'Review chuyên sâu', 'Sports Highlights', 'Phản biện', 'Tranh luận'] },
  target_audience: { label: 'Đối tượng khán giả', icon: Users, values: ['Đại chúng', 'US sports fans', 'Người mới', 'Sinh viên', 'Chuyên gia', 'Chủ doanh nghiệp', 'Nhà đầu tư', 'Developer', 'Marketer', 'Content Creator'] },
  tone: { label: 'Giọng điệu', icon: Megaphone, values: ['Chuyên nghiệp', 'Thân thiện', 'Nghiêm túc', 'Năng lượng cao', 'Energetic, dramatic, broadcast-style', 'Hài hước', 'Cảm xúc', 'Sang trọng', 'Gay cấn'] },
  target_duration: { label: 'Độ dài video mục tiêu', icon: Clock, values: ['Tự đề xuất thời lượng phù hợp với kịch bản remake', '1-3 phút', '3-5 phút', '5-10 phút', '10-20 phút'] },
  retention_mode: { label: 'Chiến lược giữ chân', icon: Gauge, values: ['Bình thường', 'Cao', 'Cực cao'] },
  hook_style: { label: 'Kiểu Hook mở đầu', icon: Flame, values: ['Cảnh đắt giá', 'Gây tò mò', 'Gây sốc', 'Đặt câu hỏi', 'Kể chuyện', 'Thống kê', 'Gây tranh cãi'] },
  clip_strategy: { label: 'Chiến lược chọn clip', icon: Scissors, values: ['Chỉ các đoạn hay nhất', 'Ưu tiên cảm xúc', 'Ưu tiên dữ kiện', 'Ưu tiên câu chuyện', 'Giữ đầy đủ ngữ cảnh'] },
  reuse_level: { label: 'Mức độ tái sử dụng video gốc', icon: Repeat, values: ['Thấp', 'Trung bình', 'Cao'] },
  content_density: { label: 'Mật độ nội dung', icon: Brain, values: ['Thấp', 'Trung bình', 'Cao'] },
} as const;

export const localizationSelectGroups = {
  target_language: { label: 'Ngôn ngữ đích', icon: Languages, values: ['Tiếng Việt', 'English', 'Japanese', 'Korean', 'Chinese', 'Spanish', 'French', 'German', 'Portuguese', 'Hindi', 'Thai', 'Indonesian'] },
  target_market: { label: 'Thị trường đích', icon: Globe2, values: ['Việt Nam', 'Hoa Kỳ', 'United States', 'Anh Quốc', 'Canada', 'Úc', 'Nhật Bản', 'Hàn Quốc', 'Ấn Độ', 'Đức', 'Pháp', 'Tây Ban Nha', 'Brazil', 'Mexico', 'Toàn cầu'] },
  localization_level: { label: 'Mức độ địa phương hóa', icon: Globe2, values: [{ value: 'none', label: 'Không localize' }, { value: 'light', label: 'Nhẹ' }, { value: 'medium', label: 'Trung bình' }, { value: 'heavy', label: 'Mạnh' }] },
  adaptation_mode: { label: 'Chế độ chuyển thể', icon: BookOpen, values: [{ value: 'faithful', label: 'Giữ sát bản gốc' }, { value: 'localized', label: 'Bản địa hóa' }, { value: 'inspired', label: 'Lấy cảm hứng' }] },
  narrator_persona: { label: 'Persona người kể chuyện', icon: Megaphone, values: [{ value: 'neutral_narrator', label: 'Người kể trung lập' }, { value: 'funny_friend', label: 'Người bạn hài hước' }, { value: 'drama_storyteller', label: 'Người kể chuyện drama' }, { value: 'movie_reviewer', label: 'Reviewer phim' }, { value: 'news_anchor', label: 'Biên tập viên tin tức' }, { value: 'expert_analyst', label: 'Chuyên gia phân tích' }, { value: 'detective', label: 'Thám tử' }, { value: 'teacher', label: 'Giáo viên' }, { value: 'podcast_host', label: 'Host podcast' }, { value: 'tech_reviewer', label: 'Reviewer công nghệ' }, { value: 'investor', label: 'Nhà đầu tư' }] },
} as const;

export const localizationSwitches = [
  ['rename_characters', 'Đổi tên nhân vật'], ['adapt_culture', 'Điều chỉnh bối cảnh văn hóa'], ['adapt_currency', 'Quy đổi tiền tệ'], ['adapt_units', 'Quy đổi đơn vị đo'], ['adapt_company_names', 'Đổi tên công ty/thương hiệu hư cấu'],
] as const;

export const presetNames = ['Tùy chỉnh thủ công', 'Mặc Định', 'US COPS Documentary', 'TikTok Viral 60s', 'YouTube Shorts Review', 'Review Công Nghệ', 'Podcast Tóm Tắt', 'Documentary Mini', 'Tin Tức Nhanh', 'Drama Kể Chuyện', 'Phân Tích Chuyên Gia', 'Content Giáo Dục', 'Nhà Đầu Tư', 'Marketing Case Study', 'Reaction Hài Hước', 'Tranh Luận/Góc Nhìn Trái Chiều'];
