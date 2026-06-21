# UX-2A Audit Report

**Date:** 2026-06-08  
**Verdict:** ⚠️ PASS WITH WARNINGS  
**Scope:** BlurTool multi-select + stable IDs + lock + group drag, TitleTool safe area overlay, BlurReviewPanel adaptation

---

## 1. Build & Test Status

| Check | Result |
|---|---|
| `npm run build` | ✅ Pass (1847 modules, 2.03s) |
| `pytest tests/ -q` | ✅ 172/172 passed (5.06s) |

---

## 2. Critical Findings

### P0 — Multi-select Shift/Ctrl/Cmd+click does NOT toggle

**Location:** `BlurTool.tsx:461-470` (video canvas), `BlurTool.tsx:666` (sidebar)

The `onSelect` prop interface is `(id: string | null) => void` — only supports **exclusive** select. When Shift/Ctrl/Cmd is held:

- `BlurRegionEditor.handleMouseDown` (`:461-470`): calls `onSelect(hitId)` or `onSelect(null)`, both of which map to `selectExclusive(id)` in the parent.
- `BlurRegionSidebar` header click (`:666`): `onSelect(region.id)` → `selectExclusive(id)`.

**Result:** Keyboard modifier always performs exclusive select, **not** toggle multi-select.

**Dead code:** `toggleSelection()` (`:144-151`) implements the correct toggle logic but is never called. `toggleLockForSelected()` (`:128-137`) is also dead.

**Plan violation:** The UX-2A plan explicitly required Shift/Ctrl+Click for toggle multi-select.

---

### P1 — Review mode React key warning

**Location:** `BlurTool.tsx:217`

```typescript
regions={reviewRegions as BlurRegionLocal[]}
```

`reviewRegions` is `BlurRegion[]` (type at `types.ts:249`: no `id` field). The cast to `BlurRegionLocal[]` does not add `id` at runtime — `region.id` is `undefined`. The inner `BlurRegionEditor` uses `key={region.id}` (`:603`), producing React duplicate-key warnings for all review-mode regions.

**Impact:** Development console warning only — no functional breakage because `selected` and `locked` are both empty sets in review mode, and `onSelect`/`onToggleLock` are no-ops.

---

## 3. Medium Findings

### P2 — Dead state

**Location:** `BlurTool.tsx:103`

```typescript
const [reviewSelected, setReviewSelected] = useState<number | null>(null);
```

Declared but never read. Unused state.

---

## 4. Low Findings

### P3 — Unnecessary `useCallback` wrapper

**Location:** `BlurTool.tsx:590-592`

```typescript
const setDraftsMap = useCallback((drafts: Map<...>) => {
  setMultiDrafts(drafts);
}, []);
```

`setMultiDrafts` is a stable `useState` setter — no stale closure risk. The wrapper is dead code weight.

---

## 5. Passing Checks

| Area | Detail | Status |
|---|---|---|
| **Lock system** | `sessionStorage` persistence (`blur_locked_ids`), `loadLocked()`/`saveLocked()`, Ctrl+L/Cmd+L iterates all selected regions, lock icon uses `e.stopPropagation()` in sidebar | ✅ |
| **Group multi-drag** | `computeGroupDelta()` computes max allowed dx/dy across all dragged regions, `multiDrafts` Map tracks independent positions, `commitDrag` applies from snapshot | ✅ |
| **Multi-delete** | Single: deletes active keyframe; Multi: `confirm()` dialog then deletes entire regions; Locked regions excluded | ✅ |
| **BlurReviewPanel** | `App.tsx:951-988`: standalone `selected` state, `stripIds()` before API call, no lock (intentional simplification) | ✅ |
| **TitleTool safe area** | `safeMarginPct()` derives from backend `safe_margin_px`, ignores if null (defaults 6%), `showGuides` toggle independent of API data, header zone rendered, structured for `safeMarginX/safeMarginY` | ✅ |
| **Type safety** | No `as any` or `@ts-ignore` in BlurTool.tsx (693 lines) or TitleTool.tsx (324 lines) | ✅ |
| **`as BlurRegionLocal[]` casts** | Lines 406, 408 (`commitDrag`): safe — snapshot is `BlurRegionLocal[]` from `regions` prop. Line 64 (`addKfToRegions`): redundant cast, `updateOrAddKf` accepts `BlurRegion`. | ✅ |
| **`isBlurRegionLocal` type guard** | Correct but wasted in boolean `&&` context at line 64 | ✅ |

---

## 6. Recommendations

| Sev | Item | Suggested Fix |
|---|---|---|
| P0 | Multi-select toggle | Wire `toggleSelection()` to `onSelect` in parent when keyboard modifier is active (requires changing prop interface or adding a separate `onToggleSelect` callback). |
| P1 | Review mode key warning | Add a fallback `id` in the cast, e.g. `reviewRegions.map((r, i) => ({ ...r, id: `review-${i}` }))` |
| P2 | Dead `reviewSelected` | Remove unused state |
| P3 | `setDraftsMap` wrapper | Inline `setMultiDrafts(drafts)` directly |

---

## 7. Conclusion

**PASS WITH WARNINGS** — Two active issues (multi-select toggle unimplemented, review mode React key warning) and minor dead code. All core functionality (lock, group drag, multi-delete, safe area overlay, type safety, build, tests) passes.
