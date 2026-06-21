# Preset System Documentation

## Tổng quan

- **15 built-in presets** + unlimited custom presets
- **24 field preset** (PresetBase): 9 content + 10 localization/persona + 3 version + 2 meta
- **3-tier grouping** (Intent / Strategy / Constraints) — `@computed_field` trên `PresetRead`
- **3 version fields** (schema, prompt template, JSON output) — mặc định `CURRENT_PRESET_SCHEMA_VERSION` (từ `app/core/versions.py`)

---

## I. 3-tier grouping (PresetRead computed fields)

### Intent
`{rewrite_style, tone, target_audience}`

### Strategy
`{retention_mode, hook_style, clip_strategy, reuse_level, content_density}`

### Constraints
`{target_duration, target_language, target_market, localization_level, rename_characters, adapt_culture, adapt_currency, adapt_units, adapt_company_names, adaptation_mode, narrator_persona}`

---

## II. PresetBase — 22 fields

| Field | Type | Default | Ghi chú |
|---|---|---|---|
| `name` | `str` | required | unique, 1-255 ký tự |
| `description` | `str` | `""` | max 500 |
| `rewrite_style` | `str` | required | |
| `target_audience` | `str` | required | |
| `tone` | `str` | required | |
| `target_duration` | `str` | required | |
| `retention_mode` | `str` | required | |
| `hook_style` | `str` | required | |
| `clip_strategy` | `str` | required | |
| `reuse_level` | `str` | required | |
| `content_density` | `str` | required | |
| `target_language` | `str` | `"Tiếng Việt"` | |
| `target_market` | `str` | `"Việt Nam"` | |
| `localization_level` | `Literal` | `"medium"` | `none`/`light`/`medium`/`heavy` |
| `rename_characters` | `bool` | `True` | |
| `adapt_culture` | `bool` | `True` | |
| `adapt_currency` | `bool` | `True` | |
| `adapt_units` | `bool` | `True` | |
| `adapt_company_names` | `bool` | `True` | |
| `adaptation_mode` | `Literal` | `"localized"` | `faithful`/`localized`/`inspired` |
| `narrator_persona` | `Literal` | `"neutral_narrator"` | 11 personas |
| `preset_schema_version` | `int` | `1` | |
| `prompt_template_version` | `int` | `1` | |
| `json_output_schema_version` | `int` | `1` | |

---

## III. 15 Built-in Presets

### 1. Mặc Định (`builtin-mac-dinh`)
| Field | Value |
|---|---|
| description | Preset đa năng, chất lượng cao, phù hợp mọi thể loại nội dung. |
| rewrite_style | Storytelling |
| target_audience | Đại chúng |
| tone | Thân thiện |
| target_duration | 3-5 phút |
| retention_mode | Cao |
| hook_style | Cảnh đắt giá |
| clip_strategy | Giữ đầy đủ ngữ cảnh |
| reuse_level | Trung bình |
| content_density | Trung bình |
| *localization* | *(all defaults)* |

### 2. TikTok Viral 60s (`builtin-tiktok-viral-60s`)
| Field | Value |
|---|---|
| description | Nội dung viral chất lượng, nhịp nhanh nhưng có chiều sâu. |
| rewrite_style | Viral |
| tone | Năng lượng cao |
| target_duration | 1-3 phút |
| clip_strategy | Chỉ các đoạn hay nhất |
| narrator_persona | drama_storyteller |
| *còn lại* | *(defaults)* |

### 3. YouTube Shorts Review (`builtin-youtube-shorts-review`)
| Field | Value |
|---|---|
| description | Review ngắn, tự nhiên, dễ tiếp cận. |
| rewrite_style | Review chuyên sâu |
| target_duration | 1-3 phút |
| clip_strategy | Ưu tiên dữ kiện |
| *còn lại* | *(defaults)* |

### 4. Review Công Nghệ (`builtin-review-cong-nghe`)
| Field | Value |
|---|---|
| description | Phân tích công nghệ có chiều sâu, dễ hiểu. |
| rewrite_style | Chuyên gia phân tích |
| tone | Chuyên nghiệp |
| target_duration | 5-10 phút |
| clip_strategy | Ưu tiên dữ kiện |
| narrator_persona | tech_reviewer |

### 5. Podcast Tóm Tắt (`builtin-podcast-tom-tat`)
| Field | Value |
|---|---|
| description | Tóm lược podcast mạch lạc. |
| rewrite_style | Podcast |
| target_audience | Người mới |
| target_duration | 10-20 phút |
| retention_mode | Bình thường |
| reuse_level | Cao |
| narrator_persona | podcast_host |

### 6. Documentary Mini (`builtin-documentary-mini`)
| Field | Value |
|---|---|
| description | Tư liệu ngắn, mạch lạc và giàu bối cảnh. |
| rewrite_style | Documentary |
| tone | Nghiêm túc |
| target_duration | 5-10 phút |
| content_density | Cao |
| narrator_persona | teacher |

### 7. Tin Tức Nhanh (`builtin-tin-tuc-nhanh`)
| Field | Value |
|---|---|
| description | Bản tin nhanh, chính xác, phù hợp thị trường Việt. |
| rewrite_style | Tin tức |
| tone | Chuyên nghiệp |
| target_duration | 1-3 phút |
| reuse_level | Cao |
| clip_strategy | Ưu tiên dữ kiện |
| rename_characters | **False** |
| adapt_culture | **False** |
| adapt_company_names | **False** |
| narrator_persona | news_anchor |

### 8. US COPS Documentary (`builtin-us-cops-documentary`)
| Field | Value |
|---|---|
| description | Kể lại documentary/cops reality theo hướng căng thẳng, rõ bối cảnh, tôn trọng dữ kiện. |
| rewrite_style | Điều tra |
| tone | Nghiêm túc |
| target_duration | 5-10 phút |
| reuse_level | Cao |
| rename_characters | **False** |
| adapt_culture | True |
| adapt_currency | True |
| adapt_units | True |
| adapt_company_names | **False** |
| adaptation_mode | faithful |
| narrator_persona | detective |

### 9. Reaction Hài Hước (`builtin-reaction-hai-huoc`)
| Field | Value |
|---|---|
| description | Bình luận hài hước, sáng tạo, có chất. |
| rewrite_style | Hài hước |
| tone | Hài hước |
| target_duration | 3-5 phút |
| clip_strategy | Ưu tiên cảm xúc |
| adaptation_mode | inspired |
| narrator_persona | funny_friend |

### 10. Drama Kể Chuyện (`builtin-drama-ke-chuyen`)
| Field | Value |
|---|---|
| description | Kể chuyện kịch tính, cảm xúc, lôi cuốn. |
| rewrite_style | Drama |
| tone | Cảm xúc |
| target_duration | 5-10 phút |
| clip_strategy | Ưu tiên câu chuyện |
| narrator_persona | drama_storyteller |

### 11. Phân Tích Chuyên Gia (`builtin-phan-tich-chuyen-gia`)
| Field | Value |
|---|---|
| description | Phân tích sâu sắc, góc nhìn chuyên môn. |
| rewrite_style | Chuyên gia phân tích |
| target_audience | Chuyên gia |
| tone | Chuyên nghiệp |
| retention_mode | Bình thường |
| clip_strategy | Ưu tiên dữ kiện |
| content_density | Cao |
| narrator_persona | expert_analyst |

### 12. Content Giáo Dục (`builtin-content-giao-duc`)
| Field | Value |
|---|---|
| description | Giải thích dễ hiểu, giàu giá trị. |
| rewrite_style | Storytelling |
| target_audience | Sinh viên |
| tone | Thân thiện |
| reuse_level | Cao |
| narrator_persona | teacher |

### 13. Nhà Đầu Tư (`builtin-nha-dau-tu`)
| Field | Value |
|---|---|
| description | Phân tích thị trường, cơ hội đầu tư. |
| rewrite_style | Chuyên gia phân tích |
| target_audience | Nhà đầu tư |
| tone | Chuyên nghiệp |
| content_density | Cao |
| narrator_persona | investor |

### 14. Marketing Case Study (`builtin-marketing-case-study`)
| Field | Value |
|---|---|
| description | Phân tích case study marketing thực tế. |
| rewrite_style | Storytelling |
| target_audience | Marketer |
| tone | Chuyên nghiệp |
| target_duration | 3-5 phút |
| clip_strategy | Ưu tiên dữ kiện |
| narrator_persona | expert_analyst |

### 15. Tranh Luận / Góc Nhìn Trái Chiều (`builtin-tranh-luan-goc-nhin-trai-chieu`)
| Field | Value |
|---|---|
| description | Góc nhìn đa chiều, phân tích trái ngược. |
| rewrite_style | Tranh luận |
| tone | Năng lượng cao |
| target_duration | 5-10 phút |
| narrator_persona | detective |

---

## IV. Frontend — All Option Values

### rewrite_style (15 values)
`Giữ nguyên phong cách gốc` | `Chuyên gia phân tích` | `Storytelling` | `Viral` | `Drama` | `Hài hước` | `Truyền cảm hứng` | `Podcast` | `Documentary` | `Điều tra` | `Tin tức` | `Review chuyên sâu` | `Sports Highlights` | `Phản biện` | `Tranh luận`

### target_audience (10 values)
`Đại chúng` | `US sports fans` | `Người mới` | `Sinh viên` | `Chuyên gia` | `Chủ doanh nghiệp` | `Nhà đầu tư` | `Developer` | `Marketer` | `Content Creator`

### tone (9 values)
`Chuyên nghiệp` | `Thân thiện` | `Nghiêm túc` | `Năng lượng cao` | `Energetic, dramatic, broadcast-style` | `Hài hước` | `Cảm xúc` | `Sang trọng` | `Gay cấn`

### target_duration (5 values)
`Tự đề xuất...` | `1-3 phút` | `3-5 phút` | `5-10 phút` | `10-20 phút`

### retention_mode (3 values)
`Bình thường` | `Cao` | `Cực cao`

### hook_style (7 values)
`Cảnh đắt giá` | `Gây tò mò` | `Gây sốc` | `Đặt câu hỏi` | `Kể chuyện` | `Thống kê` | `Gây tranh cãi`

### clip_strategy (5 values)
`Chỉ các đoạn hay nhất` | `Ưu tiên cảm xúc` | `Ưu tiên dữ kiện` | `Ưu tiên câu chuyện` | `Giữ đầy đủ ngữ cảnh`

### reuse_level (3 values)
`Thấp` | `Trung bình` | `Cao`

### content_density (3 values)
`Thấp` | `Trung bình` | `Cao`

### target_language (12 values)
`Tiếng Việt` | `English` | `Japanese` | `Korean` | `Chinese` | `Spanish` | `French` | `German` | `Portuguese` | `Hindi` | `Thai` | `Indonesian`

### target_market (15 values)
`Việt Nam` | `Hoa Kỳ` | `United States` | `Anh Quốc` | `Canada` | `Úc` | `Nhật Bản` | `Hàn Quốc` | `Ấn Độ` | `Đức` | `Pháp` | `Tây Ban Nha` | `Brazil` | `Mexico` | `Toàn cầu`

### localization_level (4 values)
`none` | `light` | `medium` | `heavy`

### adaptation_mode (3 values)
`faithful` | `localized` | `inspired`

### narrator_persona (11 values)
`neutral_narrator` | `funny_friend` | `drama_storyteller` | `movie_reviewer` | `news_anchor` | `expert_analyst` | `detective` | `teacher` | `podcast_host` | `tech_reviewer` | `investor`

---

## V. API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/presets` | Lấy tất cả presets (tự động seed builtin) |
| `POST` | `/api/presets` | Tạo custom preset |
| `PUT` | `/api/presets/{id}` | Sửa preset (builtin bị chặn) |
| `DELETE` | `/api/presets/{id}` | Xóa preset (builtin bị chặn) |
| `GET` | `/api/presets/sync-status` | Trạng thái sync builtin |
| `POST` | `/api/presets/sync` | Force re-sync builtin |
| `POST` | `/api/presets/validate-conflicts` | Validate conflict rules |
| `POST` | `/api/generate-prompt` | Generate prompt từ form + preset fields |
| `POST` | `/api/validate-json/strict` | Validate JSON với `extra="forbid"` |

---

## VI. Conflict Validation Rules

1. `reuse_level=Cao` + `rewrite_style=Sáng tạo hoàn toàn` → warning
2. `reuse_level=Cao` + `rewrite_style=Highly Original/Sáng tạo` → warning
3. `localization_level≠none` + `target_language=''` → warning
4. `localization_level≠none` + `target_market=''` → warning
5. Short duration + high density / context clip strategy / low reuse → warning (runtime)

---

## VII. Prompt Health Score

`POST /api/prompt/health-score` — đánh giá preset trước khi gửi Gemini.

| Score range | Level | Màu |
|---|---|---|
| 85-100 | excellent | 🟢 |
| 70-84 | good | 🟡 |
| 50-69 | risky | 🟠 |
| 0-49 | weak | 🔴 |

**Strengths** (+10 mỗi): hook cụ thể, retention cao, audience chuyên biệt, localization đầy đủ, persona không default, rewrite_style cụ thể.

**Warnings** (-10 mỗi): conflict validator warnings, duration không chọn, tone mặc định.

## VIII. Prompt Generator Architecture (P5)

```
backend/app/services/prompt_blocks/
├── base.py                  # PromptBlock ABC
├── intent_block.py          # rewrite_style, audience, tone, duration
├── strategy_block.py        # retention, hook, clip, reuse, density
├── localization_block.py    # All localization fields
├── validation_block.py      # JSON rules (QUY TẮC JSON BẮT BUỘC)
├── output_schema_block.py   # STRICT OUTPUT CONTRACT + Schema JSON
└── composer.py              # PromptComposer — joins all blocks
```

`PromptGenerator.generate()` gọi `PromptComposer(data).compose()`.

## IX. Version Constants (P0)

File: `backend/app/core/versions.py`

```python
CURRENT_PRESET_SCHEMA_VERSION: int = 1
CURRENT_PROMPT_TEMPLATE_VERSION: int = 1
CURRENT_JSON_OUTPUT_SCHEMA_VERSION: int = 1
```

Dùng trong: `schemas/preset.py`, `models/preset.py`, `database.py`.

## X. Conflict Validator Rules (P1)

| Rule | Warning |
|---|---|
| `reuse_level=Cao + adaptation_mode=inspired` | Mâu thuẫn reuse nhiều vs inspired |
| `adaptation_mode=faithful + rename_characters=True` | Faithful không nên đổi tên |
| `localization_level≠none + target_language=''` | Localize cần target_language |
| `localization_level≠none + target_market=''` | Localize cần target_market |
| Duration-based: short + high density | Video ngắn khó chứa mật độ cao |
| Duration-based: short + full context | Clip strategy không phù hợp |

## XI. Relevant Files

| File | Mô tả |
|---|---|
| `backend/app/schemas/preset.py` | 3-tier `@computed_field` groups + version fields |
| `backend/app/models/preset.py` | 3 Integer ORM columns cho version fields |
| `backend/app/core/database.py` | `PRESET_VERSION_COLUMNS` + migration |
| `backend/app/services/preset_service.py` | `validate_preset_conflicts()` + built-in seeds |
| `backend/app/services/prompt_generator.py` | STRICT OUTPUT CONTRACT + JSON schema |
| `backend/app/api/routes.py` | Conflict validation + strict JSON endpoints |
| `frontend/src/types.ts` | `PresetIntent`, `PresetStrategy`, `PresetConstraints` |
| `frontend/src/App.tsx` | `PresetPreview`, builtin protection, conflict check |
| `frontend/src/api.ts` | `validatePresetConflicts()`, mock presets |
| `frontend/src/components/BlurTool.tsx` | Drag/resize handles, aspect ratio lock |
| `tests/test_preset_service.py` | Unit tests cho preset service |
