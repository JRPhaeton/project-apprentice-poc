# Trial of the Apprentice — Game Design Document

**STATUS: LOCKED (M1).** Changes after this point require an orchestrator-approved amendment recorded in §8 below (per PLAN §7/§13). Source of truth for scope, stack, tests, budgets: `docs/PLAN.md` (v3). Where this GDD and PLAN conflict, PLAN wins and the conflict is an amendment-log item.

## 1. Overview

Single-stage browser JRPG POC. One hero, three mob types, one boss, four connected rooms, 10–15 minutes: title → explore → 5 placed encounters → boss → victory screen. Feel target (PLAN §1): Defend-as-tactical-choice, buff-centric combat, large partially-animated enemies with readable tells, tonally heavy music, lethal-both-ways encounters. Tone: **hopeful yet sad**.

- Engine/stack, rendering (256×224, `pixelArt`, `Scale.FIT`), budgets, CI gates: PLAN §2/§3/§10. Not restated here.
- Encounters are **telegraphed** — visible patrol sprites on the map, no random battles (PLAN §8).

## 2. Locked Decisions

| Decision | Value | Notes |
|---|---|---|
| Final title | **Trial of the Apprentice** | §0-cleared: no collision with "The 7th Saga", "Elnard", or original character/location/item names. Repo keeps codename **Project Apprentice**. |
| Hero name | **Aden** | §0-cleared (forbidden hero names: Kamil, Esuna, Olvan, Lux, Valsu, Wilme, Lejes — no match). Data ID `hero`. |
| Enemy display names | **Vale Spider** (`spider`), **Marsh Wisp** (`wisp`), **Revenant** (`revenant`), **Cloaked Chimera** (`chimera`, boss) | §0-cleared; "Cloaked Chimera" is PLAN §5.3's own name. Data IDs match the `enemies.json` `ai` union (PLAN §4). |
| Revenant | **IN** | Locked at M1 per PLAN §13 Q2; roster now frozen. Cut lever (PLAN §11 milestone-overrun row): if M3/M4 slip, Revenant may be cut via orchestrator-approved GDD amendment — remove `enc-revenant-1`, drop the revive unit test + golden (PLAN §10). |
| Stage size | **4 connected rooms** | Mid of PLAN §13 Q3's 3–5 range. Layout in §3 below. |
| Encounter count | **5 placed encounters + boss** | Within §2 DoD's 4–6 + boss. |
| Combat numbers | PLAN §5.2/§5.3 copied verbatim in §5 below as **locked v0** | Reachability-tuned seed; lethality tuning is an explicit M1→M3 task; §10 sim expected red until it lands. |
| QoL | PLAN §8 verbatim, in §6 below | Denylist enforced in review. |

## 2b. Story Canon — "The Stolen Emberheart" (locked M6)

Master Corvan kept the **Emberheart**, the vale's last warm light. At dusk the Cloaked Chimera slew him, **swallowed the Emberheart**, and nested in the ruin. The vale grows cold and dark; wisps breed in the gloom. Aden, the last apprentice, goes to take it back before the master's soul gutters out.

- **Intro:** taunt cinematic after NEW GAME (Chimera addresses the player directly; Enter advances, X skips; CONTINUE bypasses). Plays `music.sting`.
- **Escalation:** claw-scratched Chimera taunts on the forest and marsh signs; the boss door is its final goad; GameOver carries a taunt; Victory is the epilogue — Aden relights the Emberheart.
- Tone: dark, hopeful-yet-sad, 90s JRPG. All dialogue lives in `src/data/dialogue.json` under unified `dlg-*` IDs.

## 3. World & Rooms

Room graph (linear with gated door; Tiled maps, World lane):

```
Room1 (Gate) → Room2 (Forest Path) → Room3 (Marsh) → Room4 (Ruin Antechamber) → [boss door] → Victory
```

| Room | ID | Content |
|---|---|---|
| Room1 — Gate/Intro | `room-gate` | Safe. Sign `dlg-sign-gate`, NPC Keeper (`dlg-npc-keeper-1/-2`). No encounters. Autosave on entry. |
| Room2 — Forest Path | `room-forest` | 2 spider patrols: `enc-spider-1`, `enc-spider-2`. Sign `dlg-sign-path`. |
| Room3 — Marsh | `room-marsh` | `enc-wisp-1`, `enc-mixed-1`. Sign `dlg-sign-marsh`. |
| Room4 — Ruin Antechamber | `room-ruin` | `enc-revenant-1` guards the approach; boss door with sign `dlg-sign-door`; `enc-boss` behind it. |

No rests/inns/shops anywhere: the run from Room2 to the boss is the PLAN §5.2 **no-heal gauntlet** on one shared HP/MP pool.

## 4. Encounters

All encounters are visible patrol sprites; IDs are the `encounters.json` keys. Lethality targets per encounter follow PLAN §5.2/§10 (asserted by the balance sim).

| ID | Room | Composition | Lethality target (careless "always-attack" policy) |
|---|---|---|---|
| `enc-spider-1` | room-forest | 1× Vale Spider | Winnable (≥ 90% win) but costly (median end-HP ≥ 20 constraint binds the whole class of lone mobs) |
| `enc-spider-2` | room-forest | 1× Vale Spider | Same as above |
| `enc-wisp-1` | room-marsh | 1× Marsh Wisp | Same as above |
| `enc-mixed-1` | room-marsh | 1× Vale Spider + 1× Marsh Wisp | Fatal to careless play (2-mob standard per PLAN §5.2) |
| `enc-revenant-1` | room-ruin | 1× Revenant | Winnable careless; cost variable by design (~45% typical, up to ~90% on revive proc) |
| `enc-boss` | room-ruin | 1× Cloaked Chimera | Careless win ≤ 5%; correct play (defend-on-tell + Power + Heal < 33%) ≥ 95% win, median end-HP ≥ 8 |
| — gauntlet | rooms 2–4 cumulative | all of the above, no heals between | Careless survival-to-boss ≤ 10% |

## 5. Combat (locked v0 numbers)

**These are PLAN §5.2/§5.3 verbatim — the locked amended v0 seed. They are reachability-tuned (every mob survives ≥ 2 hero hits so its signature can fire) but NOT yet lethality-balanced; bringing per-encounter lethality into line with the invariant is an explicit M1→M3 Combat-lane tuning task editing `src/data/*.json` only. The §10 sim is expected red until that lands.** Turn model: player-first alternation with tells + Defend timing (PLAN §5.1).

### 5.1 Core formulas (PLAN §5.2 verbatim)

- Damage: `max(1, ATK * 2 − DEF + rand(−2..2))`
- Defend: incoming damage ×0.5 this turn; next attack ×1.5.
- Run: `clamp(0.5 + (heroSPD − avgEnemySPD) * 0.05, 0.25, 0.95)`; failure = lost turn.
- Buffs: additive percentage on the base stat, fixed 3-turn duration, same-buff reapplication refreshes duration (no stacking).
- **Free action:** an item flagged `freeAction` (Power Bottle) applies its effect **without consuming the hero's turn** — the hero still selects one normal Attack/Defend/Magic/Item that turn. At most one free action per turn.
- **Lethality target (per ENCOUNTER, not per mob):** careless unbuffed play loses a standard **2-mob** encounter, the **boss**, and the no-heal **4–6-encounter gauntlet** in the low single digits of rounds. A **lone mob is winnable careless but always costs meaningful HP**, and **no mob may be one-shot or left un-acted** — every mob must take at least 2 hero hits before dying so its signature turn (Spider bite, Wisp Weaken) can fire. Revenant's cost is variable by design (~45% typical, up to ~90% when its one-time revive triggers). Correct Defend/tell-reading + Power/Heal wins any 1–3 mob encounter and the boss with margin.
- **Quantified invariant (encode as the §10 sim, asserted per encounter):** over 1,000 seeded battles per policy, the "always-attack, never defend/heal/buff" policy wins ≤ 5% vs the boss and survives-to-boss ≤ 10% across the gauntlet, while the "defend-on-tell + Power before boss + Heal below 33% HP" policy wins ≥ 95% with median end-HP ≥ 8; single mobs are winnable careless (≥ 90% win, median end-HP ≥ 20). **Tune to this invariant.**

### 5.2 Roster v0 (PLAN §5.3 verbatim)

| Unit | HP | MP | ATK | DEF | SPD | Signature behavior |
|---|---|---|---|---|---|---|
| Hero | 40 | 10 | 8 | 5 | 6 | Spells: **Heal** (4 MP, +15 HP), **Power** (3 MP, +50% ATK, 3 turns). Items: 2× Herb (+12 HP), 1× Power Bottle (`freeAction`, applies Power without using the turn). |
| Spider (mob) | 28 | — | 7 | 5 | 5 | Turn 1: steps forward (tell, no attack). Turn 2: bites for 2× (~14–22). Subsequent turns: normal attacks, re-telling every 3rd turn. |
| Wisp (mob) | 22 | — | 5 | 4 | 7 | 30% of turns casts **Weaken** (−25% hero ATK, 3 turns) instead of attacking. |
| Revenant (mob, optional 3rd) | 30 | — | 6 | 6 | 3 | On death, one-time 50% self-revive at 12 HP (~40% HP; visual: reassembles). |
| Cloaked Chimera (boss) | 66 | — | 7 | 5 | 6 | At ≤ 50% HP (33): removes cloak (frame-group switch = `phaseChanged`), ATK +30% (→ ~9), unlocks **Flame Breath** (1.5× dmg, always telegraphed one full turn ahead). |

Display-name mapping (presentation only; data IDs and stats unchanged): Hero → **Aden**, Spider → **Vale Spider**, Wisp → **Marsh Wisp**, Revenant → **Revenant**, Cloaked Chimera → **Cloaked Chimera**. Per PLAN §5.3: with these numbers hero hits land ~[9,13] on Spider/boss, ~[10,14] on Wisp, ~[8,12] on Revenant — each signature is reachable. AI params are the PLAN §4 `ai` union: `spider {kind:'telegraph',tellEvery:3,tellDamageMult:2}`, `wisp {kind:'caster',spell:'weaken',chance:0.30}`, `revenant {kind:'reviver',reviveChance:0.5,reviveHp:12}`, `chimera {kind:'boss',phaseAtPct:50,phaseAtkPct:30,phaseUnlock:'flameBreath'}`.

## 6. QoL (PLAN §8 verbatim)

> v1 §7 allowlist adopted: first-use Defend hint, telegraphed encounters (visible patrol sprites, no blind random carpet), hold-to-fast-forward text/animations, autosave, damage popups + HP tweening. Additions: **battle speed toggle** (1×/2×, affects animation time only, never combat math) and pause.
>
> **Denylist (explicit):** auto-battle, difficulty sliders, minimap, quest log, XP-share/rubber-banding, encounter-rate items. Gamepad + key remapping: fast-follow after POC, documented, not built.

## 7. Dialogue / Flavor Text (locked, `dialogue.json` content)

Tone: hopeful yet sad. Short — every line fits one 256px-wide dialogue box page.

| ID | Placement | Text |
|---|---|---|
| `dlg-sign-gate` | Room1 sign | "The road to the ruin is closed. It has been closed a long time. Someone should have taken this sign down by now." |
| `dlg-npc-keeper-1` | Room1 NPC (Keeper), first talk | "Another apprentice? The others went up that road too, once. Go on, then — one of you has to be the one who comes back." |
| `dlg-npc-keeper-2` | Room1 NPC (Keeper), repeat talks | "I keep the gate oiled. Silly, I suppose. But a gate should open easily for good news." |
| `dlg-sign-path` | Room2 sign | "Mind the webs. The forest keeps what it catches — travel light, and be worth less to it." |
| `dlg-sign-marsh` | Room3 sign | "The marsh lights are not stars. Follow them anyway. They end where the road ends." |
| `dlg-sign-door` | Room4 boss door | "Here waits the last trial. Whoever you were before this door, leave it — you will not need it after." |

(First-use Defend hint is QoL UI per §6, not dialogue content.)

## 8. Amendment Log

| # | Date | Section | Change | Approved by |
|---|---|---|---|---|
| 1 | 2026-07-17 | §5 | Progression curve locked (M2, Combat lane): XP to reach L2–L5 = 10/25/45/70 cumulative; per level +5 maxHP, +2 maxMP, +1 ATK/DEF/SPD; HP/MP refill on level-up. Lives in `src/core/battle/progression.ts`. | Orchestrator |
| 2 | 2026-07-17 | §7 | Dialogue ID convention split (M2, World lane): engine-referenced Room2 IDs stay `sign-gate`/`npc-gatekeeper`; the four new entries use GDD `dlg-*` IDs. Unify at M4 room split. | Orchestrator |
| 3 | 2026-07-17 | §5 | M3 lethality tuning (sanctioned M1→M3 task, PLAN §5.2): hero HP 40→42, Heal 15→18, wisp ATK 5→6, revenant ATK 6→5. All four §10 sim gates pass on seeds 1..1000; 2-mob careless winRate 0.54→0.31; leveling gauntlet survival 1.000. | Orchestrator |
| 4 | 2026-07-17 | §5 | Revenant-cost prose corrected: tuned reality is ~25–30% HP typical, ~50–55% when the revive triggers (the old ~45%/~90% claim conflicted with the median ≥ 20 sim gate at 50% revive). | Orchestrator |
| 5 | 2026-07-17 | §2b/§7 | M6 story lock: "The Stolen Emberheart" canon, intro taunt cinematic, full dialogue rewrite, dialogue IDs unified to `dlg-*` (clears amendment 2's debt; map sign props updated). | Orchestrator |
| 7 | 2026-07-17 | Art bible | M8 overworld depth pass (FF3-US style): tileset v2 (256×128 — marching-squares transitions, trunk/canopy split w/ walk-under `overhead` layer, wall top+face pairs, decor, shadow tiles), hero overworld sprite 16→16×24 FF6 proportions, patrol markers → mini creature sprites + shadows, room mood tints. Maps regenerated by `tools/gen_maps.py` with collide-grid + objects byte-equality asserted (all 29 E2E unchanged). | Orchestrator |
| 6 | 2026-07-17 | Art/Audio bibles | M6 presentation upgrade within locked dims: hero overworld sheet 4→8 frames (2-frame walk per direction; frame SIZE unchanged), sprite palettes to full 16-color budget, new non-sprite assets (bitmap font, 256×144 backdrops, ui-panel, tile-anim overlays), audio remastered to SPC700-style synthesis + `music.sting`. | Orchestrator |
