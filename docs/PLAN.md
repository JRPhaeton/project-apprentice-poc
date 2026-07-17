# Saga-Inspired Browser RPG — POC Master Plan (v3)

Working codename: **Project Apprentice**. Final title chosen in M1; it must not reference "The 7th Saga", "Elnard", or any Enix/Square Enix property (see §0).

This document supersedes v2 and the original brief (both kept verbatim in git history and the repo root). v3 keeps v2's scope, structure, voice, and aesthetic north star, and applies a round of verified review fixes — combat mechanic reachability, audio-pipeline correctness against the real Phaser API, GitHub Pages subpath handling, a fixed rendering config, frozen cross-scene contracts, sharper asset budgets, and a testable per-encounter lethality invariant. It is written to be executed by a Claude orchestrator with subagents, and to be decomposable into GitHub issues without further clarification.

## What changed from v2

Grouped by theme (full v1→v2 history is preserved in git; this section only summarizes v2→v3):

1. **Combat reachability + a testable lethality invariant (§5, §10).** The v0 roster is re-stat so every mob survives ≥ 2 hero hits and its signature turn (Spider bite, Wisp Weaken, Revenant revive) can actually fire; the boss is retuned so correct play can win. The lethality invariant is reframed **per-encounter** (lone mobs winnable-but-costly; 2-mob encounters, the boss, and the no-heal gauntlet fatal to careless play) and quantified as merge-blocking sim thresholds. The roster is flagged as an amended-but-not-yet-lethality-balanced seed to be tuned M1→M3. "Free action" is now defined.
2. **Audio pipeline made real (§3, §6, §11).** Phaser's Sound API has no sub-clip loop points; music now defaults to full-file `{loop:true}` gapless loops, the manifest carries dual-codec `{ id, ogg, m4a, volume }`, and a thin Web Audio wrapper is the escape hatch for any future intro-then-loop track.
3. **Build/deploy correctness (§3, §9, §10, §11).** Vite `base` plus a Boot-scene `setBaseURL` so Phaser's runtime loader paths resolve on the Pages subpath; a zero-404 E2E guard, an E2E run at the production base via `vite preview`, and a post-deploy live-URL release gate.
4. **Rendering configured (§3).** Fixed 256×224 internal resolution, `pixelArt`/`roundPixels`, `Scale.FIT` — resolves the previously-undecided v1 §11 Q1.
5. **Contracts & architecture pinned (§4, §7).** Typed-registry facade with a frozen `BattleRequest`/`BattleResult` handoff, an `ai` discriminated union in `enemies.json` plus explicit `BattleState` runtime fields, art-manifest frame metadata for a code-free art swap, a save-blob zod schema with discard-on-mismatch, merge-first worktree sequencing, and owners assigned to previously-unowned build/config files.
6. **Asset budgets & dimensions (§2, §6).** Byte units pinned; audio caps and a lazy-load rule; boss 96×96 / mob 64×64 reconciled across §2/§6; asset-lint split into a fast pre-build source check and a post-build size gate, plus initial-load, audio, and bidirectional referential-integrity checks.
7. **Test strategy hardened (§10).** Per-encounter balance sim, engine-determinism-scoped golden replays with a `Math.random` anti-leak guard, save version-mismatch tests, a data-validation gate, and a 90%-coverage gate.
8. **Milestones, risks, open questions tightened (§9, §11, §13).** Revenant decided at M1 (not M3); bibles locked before M4; five risk rows added/edited; the §13 opener corrected.

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

(The 60 fps / < 5 s / Safari lines are DoD acceptance items checked by hand on named hardware in M5, **not** wired as headless-CI gates — see §9 M5 and §10.)

**Hard budgets** (all merge-blocking gates live in §10; "MB" here means binary MiB — **8 MB = 8,388,608 bytes**, **3 MB = 3,145,728 bytes**):
- **Total shipped `dist/` ≤ 8 MB**, counting every file that ships — including **both** the OGG and M4A copy of each audio asset (asset-lint measures real `dist` bytes via `du -sb`, so both codecs already count).
- **First-load-to-title ≤ 3 MB**, counting only assets fetched in Boot/Preload; the browser fetches **one codec per audio key** from the URL array (§3), so initial load counts a single codec. Measured from the E2E network trace, not from `dist` size (§10).
- **Audio caps** (so the size gate is met without rework, keeping OGG + M4A per §3/§6 — do **not** drop the Safari fallback): each music loop ≤ 60 s, encoded ~112–128 kbps stereo (OGG Vorbis q3–q4 + equivalent AAC); each SFX ≤ 3 s. This fits 3 tracks + 5 SFX in both codecs at ~6.3 MB, leaving room for sprites/tiles/UI/font.
- **Lazy-load rule:** Preload fetches only Title/Overworld needs (title + overworld theme, overworld tiles, UI, font — ~1.4 MB); battle and boss music plus battle sprites load on the first Overworld→Battle transition behind a loading state, so first-load stays under 3 MB (§4).
- **Sprite grid:** all art on a 16×16 grid — overworld tiles 16×16, battle mobs 64×64 (4×4 tiles), boss 96×96 (6×6 tiles); every frame size is a multiple of 16. Per-sprite palette ≤ 16 colors.

## 3. Technical Stack (pinned)

| Layer | Choice | Notes |
|---|---|---|
| Engine | Phaser 3, latest 3.x, **pinned exact version** | Official `phaserjs/template-vite-ts` starter. Phaser 4 not required; revisit only for a blocking feature. |
| Language | TypeScript, `strict: true` | `strict` enables `noImplicitAny` but does **not** ban explicit `any`. Explicit `any` is banned in `src/core/**` via a scoped `@typescript-eslint/no-explicit-any: 'error'` ESLint override (lint gate, §10). |
| Maps | Tiled (pin 1.10+), JSON export, **embedded tilesets** | Embedding avoids loader path bugs; loaded via `load.tilemapTiledJSON`. |
| Data validation | zod, **pinned exact version** | Every JSON content file **and the persisted save blob** has a schema; validated in tests and at boot in dev builds. Import from the package root (`import { z } from 'zod'`). |
| Unit tests | vitest | Headless, runs the combat core with seeded RNG. |
| E2E | Playwright | Chromium smoke path in CI, run against a built `vite preview` at the Pages base; Firefox/WebKit weekly. |
| Build/host | Vite + GitHub Pages via Actions | `vite.config.ts` sets `base: '/<repo>/'`. Because Vite's `base` only rewrites URLs Vite itself processes (not Phaser's runtime string loader paths), the Boot scene calls `this.load.setBaseURL(import.meta.env.BASE_URL)` and uses leading-slash-free relative keys (`this.load.image('hero','sprites/hero.png')`), so paths resolve on both localhost and `https://<user>.github.io/<repo>/`. Playwright asserts zero 404s (§10). |
| Rendering | Fixed internal resolution **256×224 px** | SNES NTSC visible area; Phaser config `pixelArt: true` (nearest-neighbor, no antialias), `roundPixels: true`, `Scale.FIT` + `autoCenter: CENTER_BOTH`, integer zoom, letterbox `#000`. Overworld camera shows **16×14** of the 16×16 tiles. Resolves v1 §11 Q1. |
| Art cleanup | Aseprite (CLI scriptable) + pngquant/ImageMagick | Deterministic normalization pass, §6. |
| Audio | OGG Vorbis primary + M4A fallback (Safari) | Phaser accepts a URL array per key. Looped music defaults to full-file `{loop:true}` gapless playback; Phaser's Sound API has **no** sub-clip loop points, so any future intro-then-loop track uses a thin Web Audio wrapper on the shared context (§6). |

All dev and runtime dependencies are pinned to **exact** versions (no caret) and `package-lock.json` is committed, so installs are reproducible across worktrees and CI (§11).

SNES authenticity constraints from v1 §3 (8×8 hardware tiles, 4bpp/16-color sprite palettes, 16×16 working grid) are encoded as the asset-lint rules in §6, not prose.

## 4. Architecture

**Scene graph:** `Boot → Preload → Title → Overworld ⇄ Battle → Victory/Defeat`, with a `UIOverlay` scene running in parallel for dialogue/HUD.

**Cross-scene state lives in a typed registry.** `src/core/contracts/` holds **pure TYPE definitions only** (no Phaser import) — `RegistryShape`, `BattleRequest`, `BattleResult`, `HeroState`. The runtime facade `src/systems/registry.ts` (Engine/Systems lane) is a thin generic wrapper over Phaser's `Data.DataManager`, typed by `RegistryShape` (`get<K extends keyof RegistryShape>(k:K): RegistryShape[K]`), taking the DataManager by injection so `src/core/**` stays Phaser-free and headless-testable. The Overworld→Battle handoff and the Battle→outcome return are a **frozen contract**: both the overworld encounter trigger and the debug-flag-gated debug entry build the payload through one shared `makeBattleRequest(...)` factory, so the tested path equals the production path. `BattleResult` is minimal — `{ outcome: 'victory'|'defeat'|'fled'; heroSnapshot: HeroState; itemsDropped?: ItemId[] }` — with no XP/rewards until §5 adds leveling; the debug `level` param is an optional, factory-defaulted field, not a contract obligation.

**The combat core is pure TypeScript, no Phaser imports:**

```ts
// src/core/battle/resolver.ts
resolveAction(state: BattleState, action: Action, rng: Rng):
  { state: BattleState; events: BattleEvent[] }
```

- `Rng` is seeded (mulberry32). Every battle logs its seed; any battle is replayable in a unit test.
- `BattleEvent` is a discriminated union (`damage`, `heal`, `buffApplied`, `tellStarted`, `phaseChanged`, `fled`, `defeated`, …). The Phaser `BattleScene` consumes the event list and animates it; it never computes outcomes.
- `BattleState` carries per-combatant runtime fields — `turnCount`, `tellPending`, `hasRevived`, `phase`, `mods: StatMod[]` — the exact fields the §10 tests require. These are part of the M1 contract freeze (§7) so no lane re-invents them mid-build.
- Enemy AI is a pure function `chooseAction(state, enemyId, rng): Action`. **Per-turn action selection** (Spider tell scheduling via `turnCount % tellEvery`, the Wisp RNG branch) reads runtime data from `state` and dispatches on an `ai` discriminated union declared per enemy in `enemies.json` (params only) to typed handlers in `src/core/battle/ai/`: `spider {kind:'telegraph',tellEvery:3,tellDamageMult:2}`, `wisp {kind:'caster',spell:'weaken',chance:0.30}`, `revenant {kind:'reviver',reviveChance:0.5,reviveHp:12}`, `chimera {kind:'boss',phaseAtPct:50,phaseAtkPct:30,phaseUnlock:'flameBreath'}`. **Threshold/death triggers resolve in `resolveAction` on the damage path, not in `chooseAction`:** Revenant revive fires when lethal damage lands and `!hasRevived`; the boss phase change fires when HP first crosses ≤ `phaseAtPct`% — each emitting `defeated`/`phaseChanged`. This keeps the signatures data-driven and QA table-testable (seed `rng`, set `turnCount`).

**Data-driven content.** All balance and content in `src/data/*.json` with zod schemas: `enemies.json`, `spells.json`, `items.json`, `encounters.json`, `dialogue.json`, `audio-manifest.json`, `art-manifest.json`. The **art manifest keys each sprite-SHEET by a sheet-level logical ID** carrying frame metadata, e.g.

```json
"enemy.spider": {
  "file": "sprites/spider.png",
  "frameWidth": 64, "frameHeight": 64,
  "anims": {
    "idle": { "frames": [0,1],   "frameRate": 4,  "repeat": -1 },
    "step": { "frames": [2,3],   "frameRate": 8,  "repeat": 0 },
    "bite": { "frames": [4,5,6], "frameRate": 12, "repeat": 0 }
  }
}
```

The loader reads `frameWidth/Height` and anim defs from the manifest, so the placeholder→final art swap in M4 is a **pure data diff**, not a code change. The boss ships as **one preloaded sheet** containing both cloak states as separate anim groups (`cloaked.*` / `uncloaked.*`); `phaseChanged` only switches which frames play, so there is no mid-battle load. `audio-manifest.json` records `{ id, ogg, m4a, volume }` (§6), matching Phaser's per-key `[ogg, m4a]` URL array.

**Preload loads only Boot + Title/Overworld assets** (title UI, overworld theme, overworld tiles, UI, font). Battle sprites and the battle/boss music load on the first Overworld→Battle transition behind a loading state (optionally warmed during overworld idle to avoid first-battle latency), keeping initial load under the §2 3 MB budget. The current `Boot → Preload → Title` graph therefore does **not** load everything before Title.

**Save:** JSON to `localStorage`, autosave on scene transition and victory. The save blob has its **own zod schema** and is versioned from day one (`{ v: 1, ... }`). `loadSave()` parses the blob, zod-validates it against the current schema, and on **any** failure — unrecognized/older/future version, JSON parse error, corrupt/truncated data — discards the save and starts a fresh game, **never throwing** into Title/Preload. Migration (upgrading an older blob to preserve progress) is out of default POC scope; the discard-on-mismatch path prevents the crash for a 10–15-minute game. All save I/O is wrapped in feature-detect + try/catch with an in-memory fallback and a "saving disabled" HUD notice (§11).

**Debug hooks (build-flag-gated via `import.meta.env.VITE_ENABLE_DEBUG`, set by the `--mode e2e` build and left unset — hence tree-shaken out — in the public Pages deploy build; NOT gated on `import.meta.env.DEV`, which is false under `vite preview`):** query params `?seed=`, `?scene=battle&enemy=spider` (with optional `&level=`, factory-defaulted) for direct scene entry via the same `makeBattleRequest(...)` factory the overworld uses, plus `?turbo=1` to zero animation durations. These make Playwright fast and let QA agents reproduce exact battles. Gating on this dedicated flag (rather than `DEV`) is what lets the §10 E2E exercise the hooks against the production `vite preview` artifact — a real `vite build` where `DEV` is false — while the deployed Pages build, built without the flag, still strips arbitrary scene-jumping.

## 5. Combat Specification v0 (concrete, testable)

These numbers are the starting point M1 locks or amends — they exist so tests can be written now. Balance-tuning changes `src/data/*.json` only. **The §5.3 values are an amended v0 seed: they are chosen so every mob's signature is *reachable* (each mob survives ≥ 2 hero hits so its tell/Weaken/revive turn can fire), but they are not yet *lethality-balanced* — bringing per-encounter lethality (§5.2) into line is an explicit M1→M3 tuning task, and the §10 lethality sim is expected red until that tuning lands.**

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
- **Free action:** an item flagged `freeAction` (Power Bottle) applies its effect **without consuming the hero's turn** — the hero still selects one normal Attack/Defend/Magic/Item that turn. At most one free action per turn.
- **Lethality target (per ENCOUNTER, not per mob):** careless unbuffed play loses a standard **2-mob** encounter, the **boss**, and the no-heal **4–6-encounter gauntlet** in the low single digits of rounds. A **lone mob is winnable careless but always costs meaningful HP**, and **no mob may be one-shot or left un-acted** — every mob must take at least 2 hero hits before dying so its signature turn (Spider bite, Wisp Weaken) can fire. Revenant's cost is variable by design (~45% typical, up to ~90% when its one-time revive triggers). Correct Defend/tell-reading + Power/Heal wins any 1–3 mob encounter and the boss with margin.
- **Quantified invariant (encode as the §10 sim, asserted per encounter):** over 1,000 seeded battles per policy, the "always-attack, never defend/heal/buff" policy wins ≤ 5% vs the boss and survives-to-boss ≤ 10% across the gauntlet, while the "defend-on-tell + Power before boss + Heal below 33% HP" policy wins ≥ 95% with median end-HP ≥ 8; single mobs are winnable careless (≥ 90% win, median end-HP ≥ 20). **Tune to this invariant.** The one-time search for numbers that satisfy it is a Combat-lane task editing `src/data/*.json`, not a CI activity — CI only asserts the thresholds.

### 5.3 Roster v0 (amended seed — reachability-tuned, lethality still to be tuned)

| Unit | HP | MP | ATK | DEF | SPD | Signature behavior |
|---|---|---|---|---|---|---|
| Hero | 40 | 10 | 8 | 5 | 6 | Spells: **Heal** (4 MP, +15 HP), **Power** (3 MP, +50% ATK, 3 turns). Items: 2× Herb (+12 HP), 1× Power Bottle (`freeAction`, applies Power without using the turn). |
| Spider (mob) | 28 | — | 7 | 5 | 5 | Turn 1: steps forward (tell, no attack). Turn 2: bites for 2× (~14–22). Subsequent turns: normal attacks, re-telling every 3rd turn. |
| Wisp (mob) | 22 | — | 5 | 4 | 7 | 30% of turns casts **Weaken** (−25% hero ATK, 3 turns) instead of attacking. |
| Revenant (mob, optional 3rd) | 30 | — | 6 | 6 | 3 | On death, one-time 50% self-revive at 12 HP (~40% HP; visual: reassembles). |
| Cloaked Chimera (boss) | 66 | — | 7 | 5 | 6 | At ≤ 50% HP (33): removes cloak (frame-group switch = `phaseChanged`), ATK +30% (→ ~9), unlocks **Flame Breath** (1.5× dmg, always telegraphed one full turn ahead). |

With these numbers and the §5.2 formula, hero hits land for ~[9,13] on the Spider/boss (DEF 5), ~[10,14] on the Wisp (DEF 4), ~[8,12] on the Revenant (DEF 6) — so the Spider survives ~3 hits (tell+bite fire before death), the Wisp survives its first hit (Weaken can proc), the Revenant re-kills over ~2 post-revive hits, and the boss survives ~6 hits (long enough for the ≤50% phase and Flame Breath). These make each signature *reachable*; whether careless multi-mob/boss encounters are *fatal* is the M1→M3 tuning target above.

Boss phase change is all three of v1's options at once — stat shift + new attack + visual transformation — because the cloak-off is a frame-group switch within one preloaded sheet (§4) and the rest is data. Storyboard the cloak-off moment before art generation.

## 6. Asset Pipeline — placeholder-first

**Rule: the game is never blocked on art.** M1–M3 ship entirely on CC0 placeholders (Kenney 16×16 packs or equivalent; record picks in `assets/CREDITS.md`). Final art lands in M4 as a manifest swap.

**Battle-scale placeholders.** Kenney Tiny Town/Tiny Dungeon only supply 16×16 overworld art, so for the 64×64 mobs and 96×96 boss use a 16×16 CC0 creature nearest-neighbor-upscaled to those exact dimensions, or a flat CC0 silhouette at 64×64/96×96, recorded in `assets/CREDITS.md` and mapped in `art-manifest.json` under the **same logical IDs the final art will use**, so the M4 swap stays code-free (§6's placeholder rule permits non-16×16 placeholders via "or equivalent").

**AI art normalization (deterministic, scripted — an Art Agent task, not raw generator output):**
1. Generate concepts (Grok Imagine or equivalent) at any resolution.
2. Downscale/snap to grid: 16×16 overworld, 64×64 battle mobs, 96×96 boss.
3. Quantize: pngquant to ≤ 16 colors per sprite group; verify with a palette-count script.
4. Frame alignment in Aseprite; export spritesheets via Aseprite CLI (scripted, reproducible).

**CI asset-lint (blocks merge) — split into two jobs:**
- **`source-asset-lint`** (no build; runs in the pre-build parallel group — these are pure file checks, no reason to spend a build first): every PNG frame under `assets/sprites|tilesets` has dimensions divisible by 16 and no sprite/tileset PNG frame exceeds 96×96; palette count ≤ 16 per sheet. **Bidirectional referential integrity:** every logical ID in `art-manifest.json`/`audio-manifest.json` resolves to a file, AND every art/audio ID referenced by the ID-bearing fields of `enemies|spells|items|encounters|dialogue.json` (as declared in their zod schemas — not every string, since dialogue is prose) resolves in the matching manifest; manifest IDs referenced by nothing emit a non-blocking warning. **Audio:** for each `audio-manifest.json` entry, both the OGG and M4A files exist (a missing Safari fallback is otherwise a green ship); each music loop ≤ 60 s and each SFX ≤ 3 s via `ffprobe` (the one check needing a new CI dep; trivial for 3 tracks + 5 SFX); if the optional `loopStart`/`loopEnd` fields are present, assert `0 ≤ loopStart < loopEnd ≤ duration`.
- **`size-budget`** (post-build): `du -sb dist` ≤ 8 MB (total, both codecs counted). The ≤ 3 MB initial-load budget is measured inside the E2E run (§10), since a total-`dist` measurement cannot see it.

**Audio.** AI chiptune drafts → Audio Agent trims each music track to a **self-contained seamless loop** (both ends snapped to a zero-crossing so the file loops cleanly) and plays it via `this.sound.play(key, { loop: true })` — Phaser's `WebAudioSound` does gapless full-buffer looping natively via a dual `AudioBufferSourceNode` scheme. `audio-manifest.json` records `{ id, ogg, m4a, volume }` for the POC's three tracks; `loopStart`/`loopEnd` are **optional** schema fields reserved for a future intro-then-loop-region track. Phaser's Sound API exposes no sub-clip loop points, so if such a track is ever needed, bypass the Sound Manager and drive a raw node on Phaser's shared context via a thin `WebAudioLoopPlayer`:

```ts
const ctx = this.sound.context;
const src = ctx.createBufferSource();
src.buffer = this.cache.audio.get(key);
src.loop = true; src.loopStart = m.loopStart; src.loopEnd = m.loopEnd;
src.connect(gain).connect(ctx.destination);
src.start(0); // manage stop/volume manually
```

SFX and one-shots continue to use Phaser's normal `this.sound.add/play`. Deliver OGG + M4A. Three tracks (overworld, battle, boss) + 5 SFX (attack, hit, magic, victory fanfare, menu blip).

**Trailer (Kling):** separate non-blocking workstream, starts after M4 when scenes are capture-stable. Trailer must respect §0.

## 7. Agent Orchestration (real primitives only)

Structure: **one orchestrator session + task-scoped subagents**, each spawned with an explicit file-ownership charter. Implementation subagents run in **git worktrees** (isolated branches); merge happens only via PR with green CI. CI is the arbiter — no agent merges its own PR without the orchestrator's review pass.

Note the base-branch behavior of the real primitive: `isolation: worktree` by default branches each subagent's worktree from the repository's **default branch** (`origin/HEAD` = `main`), not the orchestrator's working `HEAD`. Consequence: the M0 scaffold, the frozen contracts (`src/core/contracts/**` + zod schemas), and root build/config must be **merged to `main`** before any dependent-lane (Combat/World/Engine) subagent is spawned — a worktree spawned while the contracts PR is still open/in-CI branches from `main` without the contracts and re-invents `BattleState`/`Action`/`BattleEvent` divergently, the exact drift contracts-first is meant to prevent. Sequencing: the contracts PR merges to `main` at the M1 gate, and only then does the orchestrator fan out M2+ implementation subagents. (The alternative — `worktree.baseRef: "head"`, branching worktrees from the orchestrator's current HEAD — would carry the orchestrator's entire uncommitted working state into every worktree, weakening isolation; merge-first keeps `main` as the single clean source of contracts, consistent with the CI-arbiter model.)

**Contracts-first:** M1 freezes the TS interfaces — `BattleState` (including its per-combatant runtime fields `turnCount`, `tellPending`, `hasRevived`, `phase`, `mods: StatMod[]`), `Action`, `BattleEvent`, `Rng`, the cross-scene types `RegistryShape`/`BattleRequest`/`BattleResult`/`HeroState`, and the `enemies.json` `ai` discriminated union — plus **the zod schemas for all `src/data/*.json` content files (§4)**, including the save-blob schema. The runtime registry facade (`src/systems/registry.ts`) that wraps Phaser's `DataManager` is an **Engine/Systems** deliverable, not a contract file, keeping `src/core/**` Phaser-free. After freeze, contract changes require an orchestrator-approved PR touching `src/core/contracts/**` alone. This is what actually prevents the two-agents-one-file failure mode; ownership lists alone don't.

| Lane | Owns | Deliverables |
|---|---|---|
| Orchestrator (main session) | `docs/**`, `src/core/contracts/**`, `package.json` + lockfile, `tsconfig.json`, `vite.config.ts`, merges | GDD lock, issue breakdown, reviews, integration |
| Engine/Systems | `src/scenes/**`, `src/systems/**`, `src/main.ts`, `index.html` | Scene graph, Phaser bootstrap, input, save, registry facade, audio manager |
| Combat | `src/core/battle/**`, `src/data/enemies\|spells\|items.json` | Resolver, enemy AI, balance sims |
| World/Content | `assets/maps/**`, `src/data/encounters\|dialogue.json` | Tiled maps, collision, triggers, NPC text |
| Assets | `assets/**` (except maps), `src/data/*-manifest.json` | Normalized sprites/tiles/audio, CREDITS.md |
| QA/Docs | `tests/**`, `.github/**`, README | Unit+smoke suites, asset-lint, bug log |

Root build/config files (`package.json` + lockfile, `tsconfig.json`, `vite.config.ts`) are a shared-edit surface with a single integrator owner (Orchestrator; QA/Docs is an acceptable alternative for `tsconfig.json`/`vite.config.ts` since the Pages `base` path pairs with the deploy workflow), resolved at the normal single merge point under the small-PR / orchestrator-merge discipline — **not** the frozen-contract gate, which is reserved for `src/core/contracts/**` (freezing high-churn build files would contradict their churn). The Phaser bootstrap (`src/main.ts`, `index.html`) belongs to Engine/Systems as part of the scene graph and must **not** require an orchestrator PR to wire a scene. The `src/data/*.json` split (3 Combat / 2 World / 2 Assets = all 7, no overlap) is already conflict-free and needs no gate.

Cadence: small PRs (< ~400 lines), land on `main` at least daily, conventional commits (`feat:`, `fix:`, `art:`, `audio:`, `data:`). `CLAUDE.md` stays current so newly spawned agents inherit conventions; updating it after a convention change is part of that change's PR.

## 8. QoL Allowlist / Denylist

v1 §7 allowlist adopted: first-use Defend hint, telegraphed encounters (visible patrol sprites, no blind random carpet), hold-to-fast-forward text/animations, autosave, damage popups + HP tweening. Additions: **battle speed toggle** (1×/2×, affects animation time only, never combat math) and pause.

**Denylist (explicit):** auto-battle, difficulty sliders, minimap, quest log, XP-share/rubber-banding, encounter-rate items. Gamepad + key remapping: fast-follow after POC, documented, not built.

## 9. Milestones v3

| # | Name | Exit criteria (all testable) |
|---|---|---|
| M0 | Walking skeleton (days 1–2) | Repo scaffolded from Phaser Vite-TS template; CI green (lint, typecheck, placeholder test); blank scene deployed to public Pages URL (E2E asserts zero 404s at the `/<repo>/` base). |
| M1 | Contracts + design lock | GDD locked incl. §5 numbers and the §5.3 roster — **Revenant decided IN or OUT here, not at M3** (amendments recorded); contracts + zod schemas frozen **and merged to `main`** (not merely drafted/frozen on a branch) before any M2 lane subagent is spawned; resolver skeleton passes first unit tests; art/audio bibles drafted. |
| M2 | Vertical slice | On placeholders: move on one map → trigger encounter → full battle vs Spider (all 4 commands) → win/lose → return/game-over. Smoke test covers this path. |
| M3 | Combat complete | All confirmed mobs + boss logic (tells, Weaken, phase change; **Revenant revive only if the roster locked it IN at M1**) vs placeholder art; balance sim invariants pass (requires the M1/M3 stat-tuning pass to have brought `src/data/*.json` into line with the §5.2 invariant); battle unit suite ≥ 90% coverage of `src/core/battle`. **Art & audio bibles LOCKED** — M4 generation may not begin against a draft bible; the lock fixes (i) canonical per-logical-group sprite dimensions (§2/§6 reconciled to overworld 16 / mob 64 / boss 96, recorded), (ii) per-animation frame counts (now determinable, all combat behaviors complete), (iii) audio loop/seam convention. Palette ≤ 16 already binds via §2/asset-lint. |
| M4 | Content + art/audio swap | Final normalized art + looped audio in via manifests; full 3–5 room stage; asset-lint and budgets green. |
| M5 | Polish + release | QoL allowlist done; §2 Definition of Done fully met, with the < 5 s-load and 60 fps checks **naming specific hardware and recording a result**; post-deploy **live-URL release gate** green (HTTP 200 + correct Content-Type on `index.html` and the hashed JS bundle); README + GIF; trailer workstream handed capture footage. |

Each milestone = GitHub Milestone; issues labeled by owning lane.

## 10. Test Strategy

- **Unit (vitest):** damage bounds; Defend halving + ×1.5 consumption; buff refresh-not-stack; Run clamp; **Spider tell precedes bite — the 2× bite only ever follows a tell**; boss phase triggers exactly once at ≤ 50%; **Revenant revives at most once (test present only if Revenant is in the M1-locked roster)**; **data-validation:** every `src/data/*.json` parses against its zod schema AND a committed malformed fixture per schema is rejected (realizes §3's "validated in tests"); **save-load:** `tests/unit/save-load.test.ts` with committed fixtures under `tests/fixtures/saves/` — a current-version blob round-trips and passes the save schema; a future-version blob returns `null` (fresh game), never throws; a truncated/corrupt/non-JSON blob returns `null`, never throws.
- **Golden replays (ENGINE DETERMINISM, not balance):** each golden is the full serialized `BattleEvent[]` of a complete scripted battle for a fixed seed, recorded against a frozen `tests/fixtures/balance-v0.json` (a valid, zod-passing dataset never edited for tuning, loaded via the core's normal data-injection path, kept separate from live `src/data`) and asserted byte-for-byte against the committed file. Coverage: Spider full cycle incl. the bite turn, Wisp Weaken, the boss ≤ 50% phase change, and a Revenant-revive golden only if Revenant ships. Regeneration only through an explicit `test:golden --update` mode; CI runs non-updating, so any diff **fails** the build and CI never regenerates. Anti-leak guard: inside the golden test, replace global `Math.random` with a throwing stub, enforcing the "pure core, seeded `Rng` only" invariant of §4. (Goldens on frozen data and the balance sim on live data are complementary, not duplicates.)
- **Balance simulation (LIVE `src/data`, per-encounter):** run seeds 1..1000 (a committed constant array) against the live dataset. Assert per target: (1) the "always-attack, never defend/heal/buff" policy vs the Cloaked Chimera boss → hero win-rate ≤ 5%; (2) the same careless policy across the full 4–6-encounter gauntlet on one shared HP/MP pool (no rests) → survival-to-boss ≤ 10%; (3) the "defend-on-tell + Power before boss + Heal below 33% HP" policy vs boss → win-rate ≥ 95% AND median hero end-HP ≥ 8; (4) per single mob (Spider/Wisp/Revenant) careless win-rate ≥ 90% AND median end-HP ≥ 20 — single mobs are winnable, the gauntlet + boss are not without correct play. This is a merge-blocking regression assertion; expect it red until the M1/M3 tuning lands (§5.2). Catches balance regressions from data-only PRs.
- **E2E (Playwright, at the PRODUCTION base):** `vite build --mode e2e` → `vite preview` (which honors the Pages `base`) → Playwright `baseURL` = `<preview-origin>/<base>/`, with `<base>` derived from `vite.config` rather than hardcoded (the repo/title isn't locked until M1). **The preview build under test is the `--mode e2e` build, which enables the debug hooks via `import.meta.env.VITE_ENABLE_DEBUG` (§4) so the load-bearing `?scene=battle&enemy=spider` jump and `?turbo=1` timing-zeroing actually resolve in this production-mode artifact (where `import.meta.env.DEV` is false); the public Pages deploy build omits that flag and tree-shakes the hooks out, so the tested artifact still exercises the hooks while the deployed artifact still excludes arbitrary scene-jumping.** Path: boot → title → new game → walk → `?scene=battle&enemy=spider` → win (assert on the `battle:win` registry event **and** the autosave `localStorage` key) → reload restores state. Added steps: seed `localStorage` with a corrupt / wrong-version blob before boot → title loads with no unhandled exception or console error; a storage-blocked run → game still playable, no crash. A guard asserts **zero HTTP 404s** in the network log so a stray absolute path fails CI instead of shipping. **Initial-load measurement folded into this same run:** before navigation, attach a Chromium CDP session and sum `encodedDataLength` from `Network.loadingFinished` events (or sum `(await response.sizes()).responseBodySize` from `page.on('response')` in pure Playwright — **not** the non-existent `response.encodedDataLength()`), stop at a `title:ready` signal, and assert the sum ≤ 3 MB. Reuse the `?turbo=1` flag for animation determinism. If audio is ever exercised, launch Chromium with `--autoplay-policy=no-user-gesture-required`.
- **Release gate (M5, not per-PR):** after deploy, curl the live Pages URL and assert HTTP 200 + correct Content-Type on `index.html` and the hashed JS bundle (QA/Docs lane, `.github/**`).
- **CI order (fail-fast):** [parallel] lint · typecheck · `source-asset-lint` → unit + coverage gate (≥ 90% lines for `src/core/battle/**`) → balance sim → `vite build` → `size-budget` (`du -sb dist` ≤ 8 MB) → Playwright E2E (smoke path + initial-load ≤ 3 MB). All block merge.

## 11. Risk Register

| Risk | L | Mitigation |
|---|---|---|
| AI pixel art unusable/inconsistent | High | Placeholder-first (§6); normalization pass; budget hand-fix time in M4; CC0 fallback is shippable worst-case. |
| Audio loop seams audible | Med | Author tracks as clean full-file loops; `{loop:true}` gapless playback; loop-seam check in Audio Agent DoD. |
| Agent merge conflicts / contract drift | Med | Contracts-first freeze **merged to `main` before fan-out** (§7), ownership lanes, worktrees, small daily PRs, CI arbiter. |
| Scope creep via QoL/features | Med | §8 denylist; GDD lock; orchestrator rejects out-of-scope issues. |
| Safari audio/rendering quirks | Med | M4A fallback; WebKit Playwright weekly; Safari check in M5 DoD. |
| localStorage unavailable/over-quota (Safari Private Browsing historically 0 quota; storage disabled; `QuotaExceededError`) | Med | Feature-detect + try/catch around all save I/O; in-memory fallback with a "saving disabled" HUD notice; keep save blob small; §10 E2E adds a "storage-blocked → game still playable, no crash" case. |
| AI audio-generation tool unavailable/unusable | Med | Name a CC0 audio fallback now (e.g. OpenGameArt/Kenney CC0 chiptune) recorded in `assets/CREDITS.md` — shippable worst-case exactly like the CC0 art fallback; audio never on the critical path. |
| Milestone wall-clock overrun (only M0 is time-boxed) | Med | Orchestrator tracks per-milestone progress in `docs/STATUS.md`; if M3/M4 slip, pull the §13 cut levers (Revenant out; 5-room stage → 3). No fixed day quotas imposed. |
| Accidental IP resemblance in generated assets | Low | §0 review checklist on every art PR. |
| Pages subpath misconfig causes asset 404s not caught by dev-server tests | Low | `base` set to `/<repo>/` (§3); run Playwright against a built `vite preview` (not the dev server) and fail CI on any 404 in the network log. |
| Toolchain version drift | Low | Exact pins (no caret) for all runtime and dev deps — Phaser, Tiled, zod, Vite, Vitest, Playwright — plus a committed `package-lock.json` for reproducible installs; Renovate off during POC. |

## 12. Resources (curated, replaces v1's broken footnotes)

- Phaser official Vite+TS template: `phaserjs/template-vite-ts`
- Phaser turn-based RPG tutorial series (phaser.io news, 2018, parts 1–2) — pattern reference, APIs dated
- Tiled Map Editor — mapeditor.org
- SNESdev wiki (Tiles, Sprites pages) — hardware ground truth for §3 constraints
- Kenney.nl CC0 asset packs (Tiny Town / Tiny Dungeon, 16×16) — placeholders
- Aseprite CLI docs — scripted spritesheet export
- pngquant — palette quantization
- ffprobe (FFmpeg) — audio duration/loop verification in asset-lint

## 13. Remaining Open Questions (genuinely open)

All five v1 §11 open questions are now decided (resolution/scaling §3; formulas/stats §5; boss phase §5.3; audio formats/loop/budget §3/§6/§2; input remapping §8). The only questions v3 leaves genuinely open are:

1. Final title + hero/enemy names (M1, after §0 clearance).
2. 3rd mob (Revenant): decided IN or OUT **at M1** with the rest of the §5.3 roster lock — **not** deferred to M3 — because M3's exit criteria and the §10 unit suite reference the revive mechanic and cannot be written against an undecided roster. After M1 the roster is frozen; a cut requires an orchestrator-approved GDD amendment.
3. Exact overworld map layout (3 vs 5 rooms) — World lane proposes in M1 with a paper map.