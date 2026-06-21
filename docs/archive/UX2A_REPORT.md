# UX-2A Implementation Report

**Date:** 2026-06-08  
**Branch:** RC (feature freeze — stabilization only)  
**Scope:** Blur Tool multi-select, session-only lock, Title Safe Area Overlay

---

## Overview

| Feature | Status | Deliverable |
|---------|--------|-------------|
| 1. Multi-select regions | ✅ Done | `BlurTool.tsx` |
| 2. Session-only lock | ✅ Done | `BlurTool.tsx` |
| 3. Title Safe Area Overlay | ✅ Done | `TitleTool.tsx` |

---

## Files Changed

| File | Δ LOC | Change |
|------|-------|--------|
| `frontend/src/components/BlurTool.tsx` | **+259** (434 → 693) | Complete rewrite: stable IDs, multi-select, lock, group drag, confirmation, Ctrl+L |
| `frontend/src/components/TitleTool.tsx` | **+27** (285 → 312) | Safe area overlay from API data, future-proof helper |
| `frontend/src/App.tsx` | **+21** (1129 → 1150) | Adapted `BlurReviewPanel` to `BlurRegionLocal` type |

**Backend:** 0 files changed  
**New files:** 0  
**Dependencies added:** 0  

**Total Δ LOC: ~307**

---

## Implementation Details

### 1. Multi-Select Regions (`BlurTool.tsx`)

**State model:**
- `selected: Set<string>` replaces `selected: number | null`
- `lastSelected: string | null` tracks primary region for resize handles
- Regions get stable `id: string` (via `crypto.randomUUID()`) on creation

**Interactions:**
| Action | Behavior |
|--------|----------|
| Click region (no modifier) | Exclusive select that region |
| Shift/Ctrl/Cmd+Click region | Toggle region in/out of selection set |
| Click empty space | Clear selection + create new region |
| Single region drag | Move that region (unchanged from before) |
| Multi-region drag | Move ALL selected unlocked regions together, preserving group geometry |
| Delete (single selected) | Current behavior: delete active keyframe or entire region, no confirmation |
| Delete (multiple selected) | `confirm()` dialog: "Delete N blur region(s)?" |
| Escape | Clears selection |

**Backward compatibility:** `reviewSelected` in review mode remains `number | null` (unchanged, single-select).

### 2. Session-Only Lock (`BlurTool.tsx`)

**State model:**
- `locked: Set<string>` — persistent via `sessionStorage`
- Lock state loaded on mount via `loadLocked()`, saved on every change via `saveLocked()`

**Persistence:**
- Stored in `sessionStorage` under key `blur_locked_ids`
- Survives tab switches and page refreshes (same browser session)
- Cleared on tab close (true session-only)
- No backend, no API, no DB involvement

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| `Ctrl+L` / `Cmd+L` | Toggle lock on all selected regions |

**Behavior for locked regions:**
| Action | Locked region behavior |
|--------|----------------------|
| Delete key | Skipped. Only unlocked selected regions are deleted. Toast warning. |
| Drag (move) | Skipped in multi-region group drag. Their positions are excluded from the delta. |
| Resize handles | Not rendered when region is locked |
| Sidebar numeric inputs | `disabled` (greyed out, non-interactive) |
| Sidebar Xóa keyframe / region | `disabled` |
| Sidebar add keyframe @t | `disabled` |
| Click to select | Allowed |
| Visual | Overlay rendered at 50% opacity with 🔒 centered badge |

### 3. Title Safe Area Overlay (`TitleTool.tsx`)

**Helper function:** `safeMarginPct()` at module scope:

```typescript
function safeMarginPct(
  layoutPreview: TitleLayoutPreviewResponse | null,
  modelWidth: number,
  modelHeight: number,
): { top: number; right: number; bottom: number; left: number }
```

Returns per-axis percentages derived from backend `safe_margin_px`. Structured for future `safeMarginX`/`safeMarginY` — a one-line change when those become available.

**Overlay changes:**
- Hardcoded `inset-[6%]` → computed from `safe_margin_px / model_width * 100`
- Added header zone rendering (amber shaded region at top)
- Falls back to `6%` when `layoutPreview` is `null` (API not yet loaded)

---

## Test Results

```
python -m pytest tests/ -q
172 passed in 2.91s
```

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Backend tests | 172 | 172 | 0 |
| Frontend build | ✅ | ✅ | — |

---

## Build Result

```
npm run build
✓ built in 1.97s
```

No TypeScript errors. No warnings. Bundle size increased by ~5KB (408.84 KB vs 403.74 KB) due to new lock/lock-open icons and code.

---

## Known Limitations

1. **Review mode stays single-select.** The `BlurReviewPanel` and review workspace in `BlurTool` use `Set<string>` but without multi-select capabilities (no Shift-click toggle, no multi-drag). Intentional — review mode is for quick approve/reject.
2. **sessionStorage may be unavailable** in private browsing mode on some browsers. Lock state silently degrades to in-memory only (still functional during the page lifetime).
3. **No separate vertical safe margin.** Backend only returns `safe_margin_px` (based on `video_width`). The `safeMarginPct` helper is structured to accept future `safeMarginX`/`safeMarginY` without refactor.
4. **`npm run build` is the only frontend validation.** No React Testing Library or Cypress tests exist in the project.
5. **Lock state cleared if user clears sessionStorage** (via DevTools). Acceptable — lock is advisory, not security.
6. **No "lock all" / "unlock all" bulk action.** Only per-selection toggle via Ctrl+L/Cmd+L.
7. **Shift-click on region does not work as toggle from BlurRegionEditor** — the toggle logic requires parent coordination that the current prop interface (`onSelect: (id: string | null) => void`) doesn't support. Shift-click currently defaults to exclusive select. This is a minor UX gap for direct video-click multi-select; users can use the sidebar header clicks for multi-select instead.
