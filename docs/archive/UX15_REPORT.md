# UX-1.5 Stabilization Sprint — Report

**Date:** 2026-06-08  
**Branch:** RC (feature freeze — stabilization only)  
**Scope:** Fix bugs, reduce risk, increase reliability for UX-1 features. No new features.

---

## Overview

| Task | Status | Deliverable |
|------|--------|-------------|
| 1. Fix API Path Drift | ✅ Done | 3 endpoints fixed |
| 2. Prompt Preview Request Cancellation | ✅ Done | AbortController + sequence guard |
| 3. Prompt Preview Performance Benchmark | ✅ Done | `UX15_PERFORMANCE.md` |
| 4. Preset Compare Robustness | ✅ Done | 3 new tests + Unicode casefold fix |
| 5. Recommendation Card Wiring Audit | ✅ Done | `RECOMMENDATION_AUDIT.md` |

---

## Task 1 — API Path Drift

**Bug:** 3 frontend helpers used `${API_BASE}/api/...` resulting in double `/api/api/...` prefix.

| Function | Line | Before (broken) | After (fixed) |
|---|---|---|---|
| `fetchTitleLayoutPreview` | 317 | `${API_BASE}/api/title/layout-preview` | `${API_BASE}/title/layout-preview` |
| `fetchPromptRunStats` | 328 | `${API_BASE}/api/prompt/runs/stats` | `${API_BASE}/prompt/runs/stats` |
| `fetchPresetRecommendations` | 337 | `${API_BASE}/api/prompt/recommend` | `${API_BASE}/prompt/recommend` |

**Verification:** `grep` for `${API_BASE}/api/` in `api.ts` returns 0 results.

**File:** `frontend/src/api.ts`

---

## Task 2 — Prompt Preview Request Cancellation

**Problem:** 500ms debounce existed but no `AbortController`. Fast-typing could cause stale responses from earlier requests to overwrite newer results.

**Fix:**
1. `fetchPromptPreview` in `api.ts` now accepts optional `AbortSignal` parameter
2. `PromptPreviewCard` creates a new `AbortController` on each effect run
3. Previous in-flight request is aborted before starting a new one
4. Request sequence counter (`requestIdRef`) guards state updates:
   - Only the response matching the latest `requestId` can update `preview`, `error`, or `loading`
   - Stale responses are silently discarded

**No React warnings or memory leaks.** AbortController is cleaned up in the effect's return function.

**Files:**
- `frontend/src/api.ts` — added `signal?: AbortSignal`
- `frontend/src/components/PromptPreviewCard.tsx` — added `abortRef`, `requestIdRef`, sequence guard

---

## Task 3 — Prompt Preview Performance Benchmark

**Method:** 10 iterations × 3 payload sizes (small/medium/large) via `POST /api/prompt/preview`.

**Results:**

| Size | Min (ms) | Avg (ms) | Max (ms) |
|------|----------|----------|----------|
| small | 1.26 | 14.14 | 82.48 |
| medium | 1.59 | 7.88 | 25.12 |
| large | 1.34 | 6.18 | 25.18 |

**Conclusion:** Average 9.40ms — well below 100ms threshold. **No cache needed.**

**File:** `UX15_PERFORMANCE.md`

---

## Task 4 — Preset Compare Robustness

**Bug:** SQLite ILIKE only folds ASCII (A-Z → a-z). Vietnamese accented characters (Ô→ô, Ệ→ệ) were not matched case-insensitively. "REVIEW CÔNG NGHỆ" would not find "review công nghệ".

**Fix in `preset_compare.py`:**
Added a third fallback step in `_lookup_preset`:
```python
target = preset_id_or_name.casefold()
for row in db.query(PresetORM).all():
    if row.name.casefold() == target:
        return row
```
Python's `str.casefold()` handles full Unicode case folding, including accented Vietnamese characters and the German ß→ss, etc.

**New tests:**
| Test | Input | Expected |
|------|-------|----------|
| `test_compare_vietnamese_case_ascii_only` | "Review Công Nghệ" vs id | match (ILIKE path) |
| `test_compare_vietnamese_uppercase_accented` | "REVIEW CÔNG NGHỆ" vs id | match (casefold fallback) |
| `test_compare_vietnamese_mixed_case_accented` | "REVIEW công nghệ" vs id | match (ILIKE or casefold) |

**Files:**
- `backend/app/services/preset_compare.py` — `_lookup_preset` casefold fallback
- `tests/test_preset_compare.py` — 3 new tests (+10 total)

---

## Task 5 — Recommendation Card Wiring Audit

**Finding:** `PresetRecommendationCard` receives `youtubeUrl` but NOT `videoTitle` from `App.tsx`. The component works correctly via YouTube metadata fallback. `videoTitle` prop is optional and unwired.

**Decision:** No code changes. Documented in `RECOMMENDATION_AUDIT.md`.

**File:** `RECOMMENDATION_AUDIT.md`

---

## Validation Results

### Tests

```
python -m pytest tests/ -q
172 passed in 3.16s
```

**Count change:** 169 → 172 (+3 Vietnamese robustness tests)

### Build

```
npm run build
✓ built in 2.08s
```

No TypeScript errors. No warnings.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/api.ts` | Fixed 3 API paths; added `signal` param to `fetchPromptPreview` |
| `frontend/src/components/PromptPreviewCard.tsx` | Added `AbortController`, `requestIdRef`, sequence guard |
| `backend/app/services/preset_compare.py` | Added Unicode `casefold()` fallback in `_lookup_preset` |
| `tests/test_preset_compare.py` | Added 3 Vietnamese Unicode/case tests |

## Files Created

| File | Purpose |
|------|---------|
| `UX15_PERFORMANCE.md` | Latency benchmark results |
| `RECOMMENDATION_AUDIT.md` | Recommendation card wiring audit |
| `UX15_REPORT.md` | This report |

## Remaining Warnings (unchanged)

1. `PresetRecommendationCard` prop `videoTitle` unwired — documented, no action
2. `fetchTitleLayoutPreview`, `fetchPromptRunStats` double `/api/api/` — **FIXED** in this sprint
3. `README_USER.txt` may still say "beta" — packaging issue, not in scope
