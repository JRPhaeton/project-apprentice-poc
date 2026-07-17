# Saga-Inspired Browser RPG — POC Master Plan (v2)

Working codename: **Project Apprentice**. Final title chosen in M1; it must not reference "The 7th Saga", "Elnard", or any Enix/Square Enix property (see §0).

This document supersedes the original brief (kept verbatim in the repo root as `The 7th Saga-Inspired Browser RPG Proof of Concept — Autonomous Multi-Agent Development Plan (1).md`). v2 keeps v1's scope and aesthetic north star and fixes its structural weaknesses. It is written to be executed by a Claude orchestrator with subagents, and to be decomposable into GitHub issues without further clarification.

## What changed from v1

1. **IP/legal guardrails added** (§0) — v1 had none, and this project ships publicly.
2. **Combat spec now has concrete v0 numbers and turn-resolution pseudocode** (§5) — v1 deferred all numbers, which blocks test-writing and lets agents invent divergent balance.
3. **The single-hero contradiction is resolved** (§5.1) — v1's centerpiece mechanic ("enemies act immediately after the character they target") is degenerate with one hero. v2 names the actual source of the bait-and-read loop for a 1-hero POC: enemy tells + Defend timing.
4. **Placeholder-first asset strategy** (§6) — the game build never blocks on the AI art pipeline. CC0 placeholder assets ship the vertical slice; final art swaps in via a one-file manifest diff.
5. **Deterministic pure-TypeScript combat core** (§4) — battle logic is a Phaser-free module with seeded RNG, unit-testable headless in CI. The Phaser battle scene only renders events.
6. **Milestones reordered around a walking skeleton** (§9) — deployed URL and green CI on day one; design lock happens in parallel, not as a gate in front of all code.
7. **Risk register, test strategy, and hard budgets added** (§8, §10, §11).
8. **Agent orchestration rewritten around real Claude Code primitives** (§7) — orchestrator + subagents + git worktrees + CI as merge arbiter, contracts-first. v1 cited hooks that don't exist (`TeammateIdle`) and hand-waved "agent teams messaging each other."
9. **v1's footnote numbering was broken** (citation markers didn't match the reference list). v2 drops footnotes for a curated resource list (§12).

## 0. IP and Legal Guardrails (hard rules, enforced in review)

Game mechanics are not copyrightable; expression is. This project clones a *feel*, never assets or identity.

- No ripped or traced sprites, tilesets, music, SFX, fonts, or text from The 7th Saga or any commercial game. No ROM-derived material of any kind, ever, including "just for placeholder."
- No use of the names "The 7th Saga", "Elnard", character names (Kamil, Esuna, Olvan, Lux, Valsu, Wilme, Lejes), location names, or item names from the original.
- Marketing/trailer copy may say "inspired by 1990s SNES JRPGs"; it may not name the source game as an affiliation or use its box art/footage.
- All AI-generated assets must be checked for accidental resemblance to the source game's named designs before merge (Art review checklist item).
- Placeholder assets must be CC0 or equivalently licensed, with license recorded in `assets/CREDITS.md`.

## 1. North Star and Non-Goals

Unchanged from v1 §1 and still correct — replicate: Defend-as-tactical-choice, buff-centric combat, large partially-animated enemy sprites with readable tells, tonally heavy music, lethal-both-ways encounters. Avoid: high encounter rate, itemization busywork, grind walls, systems-stripping.

The POC target: **one stage, 2–3 mobs, one boss, one hero, at high polish** — nail the feel of a single combat/exploration loop.

## 2. Scope (locked)

v1 §2 table stands as written. Additions:

**Definition of Done for the POC:**
- 10–15 minutes of play: title → explore → 4–6 encounters → boss → victory screen.
- Deployed at a public URL; loads to title screen in < 5 s on a mid-range laptop.
- Steady 60 fps in Chrome and Firefox on integrated graphics; playable in Safari.
- All CI gates green (lint, typecheck, unit, smoke, asset-lint, size budget).
- README with play link, demo GIF, controls, and architecture pointer.

**Hard budgets:** total shipped assets ≤ 8 MB (audio-dominated); initial load ≤ 3 MB; per-sprite palette ≤ 16 colors; all art on a 16×16 grid (bosses 32×32 or 64×64 composites).

## 3. Technical Stack (pinned)

| Layer | Choice | Notes |
|---|---|---|
| Engine | Phaser 3, latest 3.x, **pinned exact version** | Official `phaserjs/template-vite-ts` starter. Phaser 4 not required; revisit only for a blocking feature. |
| Language | TypeScript, `strict: true` | No `any` in `src/core/**`. |
| Maps | Tiled (pin 1.10+), JSON export, **embedded tilesets** | Embedding avoids loader path bugs; loaded via `load.tilemapTiledJSON`. |
| Data validation | zod | Every JSON content file has a schema; validated in tests and at boot in dev builds. |
| Unit tests | vitest | Headless, runs the combat core with seeded RNG. |
| E2E | Playwright | Chromium smoke path in CI; Firefox/WebKit weekly. |
| Build/host | Vite + GitHub Pages via Actions | `base` path configured for Pages. |
| Art cleanup | Aseprite (CLI scriptable) + pngquant/ImageMagick | Deterministic normalization pass, §6. |
| Audio | OGG Vorbis primary + M4A fallback (Safari) | Phaser accepts a URL array per key. |

SNES authenticity constraints from v1 §3 (8×8 hardware tiles, 4bpp/16-color sprite palettes, 16×16 working grid) are encoded as the asset-lint rules in §6, not prose.

## 4. Architecture

**Scene graph:** `Boot → Preload → Title → Overworld ⇄ Battle → Victory/Defeat`, with a `UIOverlay` scene running in parallel for dialogue/HUD. Cross-scene state lives in a typed registry, not scene-to-scene ad-hoc data.

**The combat core is pure TypeScript, no Phaser imports:**

```ts
// src/core/battle/resolver.ts
resolveAction(state: BattleState, action: Action, rng: Rng):
  { state: BattleState; events: BattleEvent[] }
```

- `Rng` is seeded (mulberry32). Every battle logs its seed; any battle is replayable in a unit test.
- `BattleEvent` is a discriminated union (`damage`, `heal`, `buffApplied`, `tellStarted`, `phaseChanged`, `fled`, `defeated`, …). The Phaser `BattleScene` consumes the event list and animates it; it never computes outcomes.
- Enemy AI is a pure function `chooseAction(state, enemyId, rng): Action` driven by data in `enemies.json` (see §5.3), so QA can table-test it.

**Data-driven content.** All balance and content in `src/data/*.json` with zod schemas: `enemies.json`, `spells.json`, `items.json`, `encounters.json`, `dialogue.json`, `audio-manifest.json`, `art-manifest.json`. The art manifest maps logical IDs (`enemy.spider.idle`) to files — the placeholder→final art swap in M4 is a manifest diff, not a code change.

**Save:** JSON to `localStorage`, autosave on scene transition and victory. Save schema versioned from day one (`{ v: 1, ... }`).

**Debug hooks (dev builds only):** query params `?seed=`, `?scene=battle&enemy=spider&level=3` for direct scene entry. These make Playwright fast and let QA agents reproduce exact battles.

## 5. Combat Specification v0 (concrete, testable)

These numbers are the starting point M1 locks or amends — they exist so tests can be written now. Balance-tuning changes `src/data/*.json` only.

### 5.1 Turn resolution — honest version

v1 mandated the source game's quirk "enemies act immediately after the character they target." **With one hero this collapses into plain player-first alternation** — every enemy targets the only hero. Keep the resolver generic (action queue keyed by combatant) so multi-hero remains possible, but the POC's bait-and-read loop comes from:

1. **Tells:** dangerous enemy attacks are announced one turn early via a visible animation/state (`tellStarted` event).
2. **Defend timing:** Defend halves damage *this* turn and boosts the hero's *next* attack ×1.5 (buff consumed on that attack, does not stack).

The loop to nail: enemy telegraphs → player defends through the hit → counterattacks with the boosted hit. That is the 7th Saga feel at POC scale, stated honestly.

### 5.2 Core formulas

- Damage: `max(1, ATK * 2 − DEF + rand(−2..2))`
- Defend: incoming damage ×0.5 this turn; next attack ×1.5.
- Run: `clamp(0.5 + (heroSPD − avgEnemySPD) * 0.05, 0.25, 0.95)`; failure = lost turn.
- Buffs: additive percentage on the base stat, fixed 3-turn duration, same-buff reapplication refreshes duration (no stacking).
- Lethality target: careless unbuffed play loses to any mob in 3–4 turns; correct Defend/buff play wins with margin. Tune to this invariant, and encode it as a simulation test (§10).

### 5.3 Roster v0

| Unit | HP | MP | ATK | DEF | SPD | Signature behavior |
|---|---|---|---|---|---|---|
| Hero | 40 | 10 | 8 | 5 | 6 | Spells: **Heal** (4 MP, +15 HP), **Power** (3 MP, +50% ATK, 3 turns). Items: 2× Herb (+12 HP), 1× Power Bottle (as Power spell, free action). |
| Spider (mob) | 18 | — | 7 | 3 | 5 | Every 3rd turn: steps forward (tell), next turn bites for 2× damage. |
| Wisp (mob) | 12 | — | 5 | 2 | 7 | 30% of turns casts **Weaken** (−25% hero ATK, 3 turns) instead of attacking. |
| Revenant (mob, optional 3rd) | 22 | — | 6 | 5 | 3 | On death, one-time 50% self-revive at 8 HP (visual: reassembles). |
| Cloaked Chimera (boss) | 90 | — | 9 | 5 | 6 | At ≤ 50% HP: removes cloak (sprite swap = `phaseChanged`), ATK +30%, unlocks **Flame Breath** (1.5× dmg, always telegraphed one full turn ahead). |

Boss phase change is all three of v1's options at once — stat shift + new attack + visual transformation — because the sprite swap is one frame set and the rest is data. Storyboard the cloak-off moment before art generation.

## 6. Asset Pipeline — placeholder-first

**Rule: the game is never blocked on art.** M1–M3 ship entirely on CC0 placeholders (Kenney 16×16 packs or equivalent; record picks in `assets/CREDITS.md`). Final art lands in M4 as a manifest swap.

**AI art normalization (deterministic, scripted — an Art Agent task, not raw generator output):**
1. Generate concepts (Grok Imagine or equivalent) at any resolution.
2. Downscale/snap to grid: 16×16 overworld, 64×64 battle mobs, 96×96 boss.
3. Quantize: pngquant to ≤ 16 colors per sprite group; verify with a palette-count script.
4. Frame alignment in Aseprite; export spritesheets via Aseprite CLI (scripted, reproducible).

**CI asset-lint (blocks merge):** every PNG under `assets/sprites|tilesets` has dimensions divisible by 16; palette count ≤ 16 per sheet; every logical ID in `art-manifest.json` resolves to a file; total `dist/` size within §2 budgets.

**Audio:** AI chiptune drafts → Audio Agent trims to seamless loops. `audio-manifest.json` records `{ file, loopStart, loopEnd }` in seconds; playback uses Web Audio `AudioBufferSourceNode.loopStart/loopEnd` (Phaser exposes this). Deliver OGG + M4A. Three tracks (overworld, battle, boss) + 5 SFX (attack, hit, magic, victory fanfare, menu blip).

**Trailer (Kling):** separate non-blocking workstream, starts after M4 when scenes are capture-stable. Trailer must respect §0.

## 7. Agent Orchestration (real primitives only)

Structure: **one orchestrator session + task-scoped subagents**, each spawned with an explicit file-ownership charter. Implementation subagents run in **git worktrees** (isolated branches); merge happens only via PR with green CI. CI is the arbiter — no agent merges its own PR without the orchestrator's review pass.

**Contracts-first:** M1 freezes the TS interfaces (`BattleState`, `Action`, `BattleEvent`, `Rng`) and the zod schemas. After freeze, contract changes require an orchestrator-approved PR touching `src/core/contracts/**` alone. This is what actually prevents the two-agents-one-file failure mode; ownership lists alone don't.

| Lane | Owns | Deliverables |
|---|---|---|
| Orchestrator (main session) | `docs/**`, `src/core/contracts/**`, merges | GDD lock, issue breakdown, reviews, integration |
| Engine/Systems | `src/scenes/**`, `src/systems/**` | Scene graph, input, save, audio manager |
| Combat | `src/core/battle/**`, `src/data/enemies|spells|items.json` | Resolver, enemy AI, balance sims |
| World/Content | `assets/maps/**`, `src/data/encounters|dialogue.json` | Tiled maps, collision, triggers, NPC text |
| Assets | `assets/**` (except maps), `src/data/*-manifest.json` | Normalized sprites/tiles/audio, CREDITS.md |
| QA/Docs | `tests/**`, `.github/**`, README | Unit+smoke suites, asset-lint, bug log |

Cadence: small PRs (< ~400 lines), land on `main` at least daily, conventional commits (`feat:`, `fix:`, `art:`, `audio:`, `data:`). `CLAUDE.md` stays current so newly spawned agents inherit conventions; updating it after a convention change is part of that change's PR.

## 8. QoL Allowlist / Denylist

v1 §7 allowlist adopted: first-use Defend hint, telegraphed encounters (visible patrol sprites, no blind random carpet), hold-to-fast-forward text/animations, autosave, damage popups + HP tweening. Additions: **battle speed toggle** (1×/2×, affects animation time only, never combat math) and pause.

**Denylist (explicit):** auto-battle, difficulty sliders, minimap, quest log, XP-share/rubber-banding, encounter-rate items. Gamepad + key remapping: fast-follow after POC, documented, not built.

## 9. Milestones v2

| # | Name | Exit criteria (all testable) |
|---|---|---|
| M0 | Walking skeleton (days 1–2) | Repo scaffolded from Phaser Vite-TS template; CI green (lint, typecheck, placeholder test); blank scene deployed to public Pages URL. |
| M1 | Contracts + design lock | GDD locked incl. §5 numbers (amendments recorded); contracts + zod schemas frozen; resolver skeleton passes first unit tests; art/audio bibles drafted. |
| M2 | Vertical slice | On placeholders: move on one map → trigger encounter → full battle vs Spider (all 4 commands) → win/lose → return/game-over. Smoke test covers this path. |
| M3 | Combat complete | All mobs + boss logic (tells, Weaken, revive, phase change) vs placeholder art; balance sim invariants pass; battle unit suite ≥ 90% coverage of `src/core/battle`. |
| M4 | Content + art/audio swap | Final normalized art + looped audio in via manifests; full 3–5 room stage; asset-lint and budgets green. |
| M5 | Polish + release | QoL allowlist done; §2 Definition of Done fully met; README + GIF; trailer workstream handed capture footage. |

Each milestone = GitHub Milestone; issues labeled by owning lane.

## 10. Test Strategy

- **Unit (vitest):** damage bounds; Defend halving + ×1.5 consumption; buff refresh-not-stack; Run clamp; Spider 3-turn cycle; boss phase triggers exactly once at ≤ 50%; Revenant revives at most once; seeded-RNG golden replays.
- **Balance simulation:** scripted policies ("always attack" vs "defend-on-tell") run 1,000 seeded battles each; assert the §5.2 lethality invariant (careless loses, correct play wins). Catches balance regressions from data-only PRs.
- **E2E (Playwright):** boot → title → new game → walk → `?scene=battle&enemy=spider` → win → autosave present → reload restores state.
- **CI order:** lint → typecheck → unit+sim → build → asset-lint + size budget → Playwright. All block merge.

## 11. Risk Register

| Risk | L | Mitigation |
|---|---|---|
| AI pixel art unusable/inconsistent | High | Placeholder-first (§6); normalization pass; budget hand-fix time in M4; CC0 fallback is shippable worst-case. |
| Audio loop seams audible | Med | Loop points in manifest + Web Audio loop; crossfade fallback; loop check in Audio Agent's DoD. |
| Agent merge conflicts / contract drift | Med | Contracts-first freeze, ownership lanes, worktrees, small daily PRs, CI arbiter. |
| Scope creep via QoL/features | Med | §8 denylist; GDD lock; orchestrator rejects out-of-scope issues. |
| Safari audio/rendering quirks | Med | M4A fallback; WebKit Playwright weekly; Safari check in M5 DoD. |
| Accidental IP resemblance in generated assets | Low | §0 review checklist on every art PR. |
| Phaser/Tiled version drift | Low | Exact pins; Renovate off for engine deps during POC. |

## 12. Resources (curated, replaces v1's broken footnotes)

- Phaser official Vite+TS template: `phaserjs/template-vite-ts`
- Phaser turn-based RPG tutorial series (phaser.io news, 2018, parts 1–2) — pattern reference, APIs dated
- Tiled Map Editor — mapeditor.org
- SNESdev wiki (Tiles, Sprites pages) — hardware ground truth for §3 constraints
- Kenney.nl CC0 asset packs (Tiny Town / Tiny Dungeon, 16×16) — placeholders
- Aseprite CLI docs — scripted spritesheet export
- pngquant — palette quantization

## 13. Remaining Open Questions (genuinely open)

Everything v1 §11 listed is now decided in §2–§6 except:

1. Final title + hero/enemy names (M1, after §0 clearance).
2. 3rd mob (Revenant) in or out — decide at M3 start based on schedule.
3. Exact overworld map layout (3 vs 5 rooms) — World lane proposes in M1 with a paper map.
