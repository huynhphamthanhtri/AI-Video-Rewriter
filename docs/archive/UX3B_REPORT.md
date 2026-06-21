# UX-3B — Subtitle Style Compare Mode

## Files Changed

| File | Lines | Change |
|---|---|---|
| `frontend/src/components/SubtitlePreviewCard.tsx` | 81 (+13) | Added optional `onSelect`, `selected` props; conditional click handler + ring classes |
| `frontend/src/components/SubtitleGallery.tsx` | 218 (+118) | Added `compareEnabled`/`compareA`/`compareB` derived state; compare view with diff table; Apply/Swap buttons; selection logic on cards |
| `frontend/src/App.tsx` | 1 | Passed `onChange={updateOptions}` to `<SubtitleGallery>` |

## Design Decisions

### Derived State (no mode enum)
- `compareEnabled: boolean` — toggles compare mode on/off
- `compareA: string | null` — first selected style key
- `compareB: string | null` — second selected style key
- All view states derived from combinations of these three values

### Compare Flow
1. User clicks "So sánh style" → `compareEnabled=true`, cards become clickable
2. First click → `compareA` set, green ring appears on card
3. Second click on different card → `compareB` set, blue ring on second card, compare view renders
4. Compare view: two large cards side-by-side + diff table + Apply buttons
5. "Đổi vị trí" swaps `compareA`/`compareB`
6. "Áp dụng Style A/B" calls `onChange({ subtitle_style })`, exits compare
7. "Thoát" resets all compare state

### Diff Table (cell-level highlighting)
| Column | Matching | Differing |
|---|---|---|
| Style A | `text-white/60` | `text-emerald-300` |
| Style B | `text-white/60` | `text-blue-300` |

Only individual cells highlight when their value differs from the paired column. Entire rows are never highlighted.

## Validation

| Check | Result |
|---|---|
| `npx tsc --noEmit` | 0 errors |
| `npm run build` | 419 KB JS, 0 errors |
| `python -m pytest tests/ -q` | 184 passed |

## Manual QA Checklist

| # | Test | Status |
|---|---|---|
| 1 | Gallery grid renders 6 cards (no regression) | ✅ |
| 2 | Click "So sánh style" → cards become clickable | ✅ |
| 3 | First card click → green ring (A), second card click → blue ring (B), compare view appears | ✅ |
| 4 | Diff table shows correct differences, only differing cells highlighted | ✅ |
| 5 | "Đổi vị trí" swaps A and B cards + labels | ✅ |
| 6 | "Áp dụng Style A" → dropdown reflects new style, gallery re-renders | ✅ |
| 7 | "Áp dụng Style B" → same | ✅ |
| 8 | "Thoát so sánh" → returns to grid, selections cleared | ✅ |
| 9 | Sample text input works in both modes | ✅ |
| 10 | Outline/shadow/box toggles update compare previews | ✅ |
| 11 | Clicking same card twice when selecting A/B is ignored (no-op) | ✅ |
| 12 | Existing gallery dropdown (SubtitleStyleSelector) unchanged | ✅ |
| 13 | Can re-enter compare after applying a style | ✅ |

## Known Limitations
- Compare only two styles at a time (no N-way)
- Diff is CSS-level, not pixel-perfect ASS rendering
- Apply sets only `subtitle_style` key; toggles (outline/shadow/box/font size) remain independent
- No keyboard shortcuts for compare flow
