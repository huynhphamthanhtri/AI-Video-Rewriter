# UX-3A — Subtitle Style Preview Gallery

## Deliverables

### Backend
| File | Lines | Purpose |
|---|---|---|
| `backend/app/schemas/subtitle.py` | 35 | Request/response Pydantic models |
| `backend/app/services/subtitle_preview.py` | 65 | Style → CSS resolution service |
| `backend/app/api/routes.py` | +5 | `POST /api/subtitle/preview-style` endpoint (line 1155) |

### Frontend
| File | Lines | Purpose |
|---|---|---|
| `frontend/src/types.ts` | +17 | `SubtitleStyleCss`, `SubtitleStylePreviewItem`, `SubtitlePreviewStyleResponse` |
| `frontend/src/api.ts` | +16 | `fetchSubtitleStylePreviews()` client function |
| `frontend/src/components/SubtitlePreviewCard.tsx` | 48 | Single style card with CSS-based preview rendering |
| `frontend/src/components/SubtitleGallery.tsx` | 69 | Gallery container with debounced API call + sample text input |
| `frontend/src/App.tsx` | +2 | Import + wire gallery beneath SubtitleStyleSelector |

### Tests
| File | Tests | Status |
|---|---|---|
| `tests/test_subtitle_preview.py` | 12 | All passing |

## How It Works

1. User types sample text and adjusts subtitle toggles (outline/shadow/box/font size/alignment/position)
2. `SubtitleGallery` debounces 300ms then calls `POST /api/subtitle/preview-style`
3. Backend resolves every requested style with current override options via `SubtitleStyler._resolve_style()`
4. Returns structured CSS data (font family, size, outline/stroke, shadow, background, text alignment)
5. Frontend renders each style as a card with:
   - 16:9 aspect ratio preview pane
   - CSS-based text rendering using `-webkit-text-stroke`, `text-shadow`, `background-color`
   - Style label + description below

## Edge Cases Handled

- Empty state: loading spinner + error message shown when API fails
- Outline/shadow disabled: respective CSS props set to 0/transparent
- Box disabled: background becomes `transparent`
- Font size clamped at 36px for card fit (original size preserved in data)
- ASS color format (`&HAABBGGRR`) properly converted to `rgba()`
- All 6 styles default to `center` text alignment

## Validation

```
184 passed in 2.98s    (+12 subtitle preview tests)
npm run build → 414 KB JS, 0 errors
```
