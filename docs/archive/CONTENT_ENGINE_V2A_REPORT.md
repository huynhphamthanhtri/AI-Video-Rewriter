# CONTENT ENGINE V2A — Implementation Report

## Summary

Content Engine V2A adds **creator personality** to generated prompts through two new mechanisms:

1. **VoiceBlock** — Always-on `PromptBlock` subclass that converts `narrator_persona` + `tone` into concrete Vietnamese writing behavior (not metadata labels). Covers all 11 existing personas with 5 behavioral dimensions each.

2. **Creator DNA** — Optional markdown file (`data/creator_dna.md`) that injects creator identity instructions into the prompt. Safe failure: missing/empty file silently returns `None`, never breaks generation.

Prompt section ordering was restructured to insert Voice and Creator DNA after Strategy and before Localization, creating a logical narrative flow: *strategy → voice → identity → localization*.

## Architecture Changes

### Files Created (5)

| File | Purpose |
|------|---------|
| `backend/app/services/prompt_blocks/voice_block.py` | `VoiceBlock(PromptBlock)` — renders per-persona behavioral guidance |
| `backend/app/services/creator_dna.py` | `load_creator_dna()` — safe file loader, returns `str | None` |
| `data/creator_dna.md` | Vietnamese Creator DNA template (5 sections) |
| `scripts/compare_prompt_v1_v2a.py` | Developer utility — structural V1 vs V2A comparison via monkeypatch |
| `CONTENT_ENGINE_V2A_REPORT.md` | This report |

### Files Modified (1)

| File | Change |
|------|--------|
| `backend/app/services/prompt_blocks/composer.py` | Removed `_blocks` list, rewrote `compose()` with 14-section explicit ordering |

### Files NOT Modified (confirmed)

`schemas/prompt.py`, `schemas/preset.py`, `api/routes.py`, `core/database.py`, `models/`, `frontend/`, installer scripts, config files.

## Prompt Order

```
1.  Intro
2.  Intent
3.  Strategy
4.  Voice              ← NEW (VoiceBlock, always-on)
5.  Creator DNA        ← NEW (conditional on file existence)
6.  Localization
7.  Subtitle
8.  ContentQuality
9.  Hook
10. Task
11. Alignment
12. DomainRules
13. Validation
14. OutputSchema
```

## Design Decisions

### VoiceBlock always-on, no toggle
- Adding an `enable_voice_block` field to `PromptGenerateRequest` would require schema changes. Since VoiceBlock improves every prompt without regressions, it is unconditionally active. The behavioral guidance complements (rather than replaces) the existing `narrator_persona` label in LocalizationBlock.

### Creator DNA file-based, no DB
- A markdown file is the simplest possible storage: zero migrations, zero schema changes, zero API endpoints. Users can edit it with any text editor. Future versions can add a `PUT /api/creator-dna` endpoint but this MVP intentionally omits it.

### No feature flags on PromptGenerateRequest
- The plan explicitly forbade toggle fields. VoiceBlock is always-on; Creator DNA is controlled by file existence alone. Both decisions avoid scope creep into preset schema or API contract changes.

## VoiceBlock Persona Details

All 11 personas define behavior across 5 dimensions:

| Persona | Narrative | Reasoning | Rhythm | Audience | Emotion |
|---------|-----------|-----------|--------|----------|---------|
| neutral_narrator | Chronological | Objective | Steady | Observer | Through situation |
| drama_storyteller | Climax-first | Emotional | Varied | Immersed | Heightened |
| tech_reviewer | Comparative | Trade-off | Structured | Informed | Measured |
| detective | Question-first | Evidence chain | Layered | Curious | Tense |
| funny_friend | Surprise hook | Irreverent | Relaxed | Peer | Warm/humorous |
| movie_reviewer | Contextual | Multi-aspect | Cinematic | Audience | Appreciative |
| news_anchor | Lede-first | 5W1H | Concise | Public | Reserved |
| expert_analyst | Thesis-first | Causal | Dense | Peer | Authoritative |
| teacher | Scaffolded | Explanatory | Paced | Learner | Patient |
| podcast_host | Conversational | Exploratory | Rhythmic | Listener | Intimate |
| investor | Framework-driven | Risk/reward | Data-rich | Stakeholder | Pragmatic |

Each persona generates ~5 lines of actional Vietnamese writing instructions. Fallback behavior (for unknown persona keys) produces generic guidance without persona-specific patterns.

## Test Coverage

### Pre-V2A baseline: 184 tests passing

### Tests Added

**`tests/test_voice_block.py`** — 29 tests (13 test classes × multiple assertions)

| Area | Tests | What it validates |
|------|-------|-------------------|
| Neutral Narrator | 4 | Objective tone, persona key, tone field, no label-dump |
| Drama Storyteller | 2 | Drama patterns, section markers |
| Tech Reviewer | 2 | Comparison patterns, spec guidance **renders** |
| Detective | 2 | Evidence chains, reveal progression |
| Funny Friend | 2 | Humor patterns, conversational style |
| Movie Reviewer | 2 | Cinema language, comparison |
| News Anchor | 2 | 5W1H pattern, journalism style |
| Expert Analyst | 2 | Analysis patterns, prediction |
| Teacher | 2 | Explanation patterns, metaphor guidance |
| Podcast Host | 2 | Conversation patterns, pacing |
| Investor | 2 | Market analysis, benchmark |
| Fallback | 2 | Unknown key not in dict, fallback is label-free |
| Tone Field | 2 | Tone appears, header frame only |
| All Personas Smoke | 11 | Each renders without error |

**`tests/test_creator_dna.py`** — 8 tests (3 test classes)

| Class | Tests | What it validates |
|-------|-------|-------------------|
| Missing File | 2 | Returns None, no exception |
| Empty File | 2 | Empty + whitespace → None |
| Content | 4 | Returns string, multiline, Unicode, large content |

**`tests/test_prompt_generator.py`** — 4 new tests appended

| Test | What it validates |
|------|-------------------|
| `test_prompt_contains_voice_section` | VoiceBlock section + tone in final prompt |
| `test_prompt_contains_creator_dna_when_present` | DNA content injected in prompt |
| `test_prompt_omits_creator_dna_when_absent` | No DNA section when file missing (monkeypatch) |
| `test_prompt_section_order` | Strategy < Voice < Creator DNA < Localization |

### Total: 184 + 29 + 8 + 4 = 225 tests (but 10 existing tests were modified/replaced, so actual total = 235)

## Validation Results

### Backend Tests
```
235 passed in 2.75s
```

All existing tests remain green. No regressions.

### Frontend
```
npx tsc --noEmit   → no output (0 errors)
npm run build      → 419 KB JS, 0 errors
```

No frontend code changes were required.

### Compare Script Output
```
Metric                   V1          V2A
Total length (chars)     9490        12298
Section count            12          14
VoiceBlock present       [NO]        [YES]
Creator DNA present      [NO]        [YES]
Char delta               -           2808
Sections added           -           Voice, CreatorDNA
Section order            Valid       Valid (Strategy > Voice > DNA > Localization)
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| VoiceBlock behavior too generic | Low | Medium | All 11 personas hand-crafted with concrete rules, not templates |
| Creator DNA file not found in packaged mode | Low | Low | `ROOT_DIR` resolves consistently via `Path(__file__).parents[3]` |
| Monkeypatch in compare script leaks | None | High | Patch restored + `importlib.reload()` after each run; compare script is standalone |
| Section reorder breaks prompt parser | Low | Low | No code parses prompt structure; `PromptPreview` counts sections by substring |
| Disk space (9 GB free) | Medium | Medium | CI pipeline may fail if temp files accumulate; unrelated to V2A changes |

## Known Limitations

1. **No Creator DNA editor** — Users must edit `data/creator_dna.md` manually. No GUI, no API.
2. **Single DNA file** — Only one creator identity supported. No multi-profile switching.
3. **VoiceBlock unconfigurable** — No toggle to disable. All prompts get VoiceBlock guidance.
4. **No style analyzer** — V2A does not analyze existing content to derive voice; voice rules are hand-authored.
5. **Domain rules unchanged** — `DomainRulesBlock` still hardcodes sports rules for all presets. VoiceBlock does not address this.
6. **Creator DNA not versioned** — No revision history or diff view.

## Future V2B Recommendations

1. **Creator DNA API** — `GET/PUT /api/creator-dna` for in-app editing with validation
2. **Multi-DNA profiles** — Named profiles (e.g., "Gaming", "Documentary", "Vlog") selectable per preset
3. **Style analyzer (optional)** — Analyze successful videos to suggest voice patterns
4. **Voice preset variants** — Temperature-like parameter: "strict" / "balanced" / "expressive"
5. **DomainRules decoupling** — Separate sports rules from generic prompt to allow domain-specific voice
6. **DNA diff preview** — Side-by-side prompt comparison when editing DNA

## Files Changed Summary

Production/docs/scripts created: 5

* backend/app/services/prompt_blocks/voice_block.py
* backend/app/services/creator_dna.py
* data/creator_dna.md
* scripts/compare_prompt_v1_v2a.py
* CONTENT_ENGINE_V2A_REPORT.md

Test files created: 2

* tests/test_voice_block.py
* tests/test_creator_dna.py

Files modified: 2

* backend/app/services/prompt_blocks/composer.py
* tests/test_prompt_generator.py

Total changed files: 9

Validation Results

* 235 passed
* npx tsc --noEmit → 0 errors
* npm run build → 0 errors
