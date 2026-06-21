# UX-2A Fix Report

**Date:** 2026-06-08
**Files Changed:** 1 (`frontend/src/components/BlurTool.tsx`)

---

## P0 — Multi-select toggle wired

**Problem:** Shift/Ctrl/Cmd+click always performed exclusive select instead of toggle. `toggleSelection()` and `toggleLockForSelected()` were dead code.

**Fix:**
- Changed `onSelect` prop interface from `(id: string | null) => void` to `(id: string | null, mode?: 'exclusive' | 'toggle') => void` in both `BlurRegionEditor` and `BlurRegionSidebar`.
- `BlurTool` parent dispatches to `toggleSelection(id)` or `selectExclusive(id)` based on `mode`.
- Video canvas `handleMouseDown` (line 449): Shift/Ctrl/Cmd+click now calls `onSelect(hitId, 'toggle')`.
- Sidebar header click (line 643): same modifier support.
- Removed dead `toggleLockForSelected()` and `lockedRef`.
- `toggleSelection()` is now wired and active.

**Verification:**
- Regular click → `selectExclusive(id)` (single select only)
- Shift/Ctrl/Cmd+click → `toggleSelection(id)` (toggle in/out of set)
- Multi-select drag uses `selected.size > 1` → works with toggled set
- Ctrl+L/Cmd+L iterates `selected` Set → works with multi-selection

---

## P1 — Review mode key warning fixed

**Problem:** `reviewRegions as BlurRegionLocal[]` cast produced `undefined` `id` at runtime, triggering React duplicate-key warnings.

**Fix:**
- Added `reviewRegionsLocal` via `useMemo`:
  ```typescript
  const reviewRegionsLocal = useMemo(() =>
    reviewRegions.map((r, i) => ({ ...r, id: `review-${i}` })),
  [reviewRegions]);
  ```
- Review mode now passes `reviewRegionsLocal` (stable `id: "review-N"`) instead of the cast expression.
- `stripIds()` strips the synthetic `id` before API submission — unchanged and correct.

---

## P2 — Dead `reviewSelected` removed

**File:** Line 103 `const [reviewSelected, setReviewSelected] = useState<number | null>(null);` — removed.

---

## P3 — `setDraftsMap` wrapper removed

**Before:**
```typescript
const setDraftsMap = useCallback((drafts) => { setMultiDrafts(drafts); }, []);
// ...
setDraftsMap(drafts);
```

**After:**
```typescript
setMultiDrafts(drafts);
```

The `useCallback` wrapper was unnecessary since `setMultiDrafts` is a stable `useState` setter.

---

## Validation Results

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ No errors |
| `npm run build` | ✅ 2.01s, 409 KB JS |
| `python -m pytest tests/ -q` | ✅ 172/172 passed (3.00s) |

---

## Lines Changed

| Line(s) | Change |
|---|---|
| 1 | `useCallback` restored to import (still used elsewhere); `useMemo` added |
| 102 | Removed `reviewSelected` state |
| 111 | Added `reviewRegionsLocal` with `useMemo` |
| 112 | Persist lock `useEffect` (unchanged, just lost the old comment) |
| 114-123 | Removed `toggleLockForSelected()` and `lockedRef` |
| 203 | Review mode uses `reviewRegionsLocal` instead of `... as BlurRegionLocal[]` |
| 208-209 | `onSelect` handlers now dispatch to `toggleSelection` vs `selectExclusive` by mode |
| 215 | `BlurRegionEditor` `onSelect` prop updated to accept `mode` |
| 449 | `handleMouseDown` calls `onSelect(hitId, 'toggle')` for shift/ctrl/meta |
| 527 | `setDraftsMap(drafts)` → `setMultiDrafts(drafts)` |
| 572-575 | Removed `setDraftsMap` wrapper |
| 586 | `BlurRegionSidebar` `onSelect` prop updated to accept `mode` |
| 643 | Sidebar header click handles modifier → `onSelect(region.id, 'toggle')` |
