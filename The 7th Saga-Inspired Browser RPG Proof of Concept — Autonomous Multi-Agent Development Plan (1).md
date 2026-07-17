# The 7th Saga-Inspired Browser RPG Proof of Concept

## Autonomous Multi-Agent Development Plan (Master Brief for Claude)

This document is a master planning brief intended to be handed to Claude (running as an orchestrator with agent teams/subagents) so it can expand, refine, and execute a full autonomous build pipeline. It is deliberately structured so Claude can decompose it into GitHub issues, subagent assignments, and a milestone-based sprint plan. Nothing here should be treated as final — Claude's job is to deepen every section, resolve open questions, and produce a locked technical spec before coding begins.

## 1. Reference Analysis: What Makes 7th Saga Work (and Fail)

The 7th Saga (Enix, 1993, developed by Produce; released in Japan as "Elnard") is a Dragon Quest-style JRPG known for brutal, high-stakes turn-based combat, an "apprentice" system offering seven playable protagonists, and a menu-driven battle loop of Attack/Defend/Magic/Escape. The breakdown video used for this plan highlights several mechanical and presentational strengths worth cloning, plus known weaknesses to deliberately avoid in a proof of concept.[^1]

**Strengths to replicate:**
- Defend is not a "skip turn" — it meaningfully buffs the next attack, creating a read-and-react rhythm where turn order (enemies act immediately after the character they target) lets the player bait attacks and adapt.[^1]
- Support magic (buffs to power/defense/agility) is mechanically central, not decorative — buffed stats materially change outcomes, making itemized "bottled magic" (single-use buff/attack consumables) meaningful resource management.[^1]
- Enemy sprites are large, colorful, and partially animated (a spider stepping forward before attacking, a chimera removing its cloak when damaged) — small idle/attack animation touches added texture even to simple encounters.[^1]
- Soundtrack carries tonal weight: overworld themes are deliberately "hopeful yet sad," and battle themes are propulsive and tense, changing by region.[^1]
- Random encounters are lethal in both directions — a single miscalculated turn can kill the player or the monster, raising the stakes of ordinary fights far above typical grind-JRPG combat.[^1]

**Weaknesses to deliberately avoid in the POC (call these out as explicit non-goals):**
- Absurdly high encounter rate that makes movement tedious.[^1]
- End-game itemization contradictions (runes duplicating and outclassing bottles, jewel-limit "treasury management" busywork).[^1]
- Late-game systems being stripped away from the player as a "tax," and grind walls gating progress with no meaningful decisions.[^1]
- A pitch (multiple rival apprentices, branching world state) that the original game never mechanically delivers on.[^1]

Claude should treat this analysis as the aesthetic and mechanical north star, while explicitly scoping the POC away from the grind/itemization problems. The POC is one stage, a handful of mob types, and one boss — so the target is to nail the *feel* of a single 7th Saga combat/exploration loop at high polish, not the whole game's structure.

## 2. Proof-of-Concept Scope Definition

Claude's first task should be to lock this scope into a written Game Design Document (GDD) before any code is written. Recommended POC scope:

| Element | Scope for POC |
|---|---|
| Player characters | 1 selectable hero (reduce from 7 apprentices — reserve multi-hero select as a stretch goal) |
| Stage | 1 overworld/dungeon stage, roughly 3-5 connected rooms/screens |
| Mobs | 2-3 distinct normal enemy types with unique sprites and one animated "tell" each |
| Boss | 1 boss encounter with at least one phase change or unique mechanic |
| Combat system | Turn-based menu battle: Attack, Defend (buffs next hit), Magic/Item, Run |
| Progression | Minimal: leveling on victory, 1-2 spells/skills, a small equipment or item set |
| Exploration | Top-down tile movement, encounter triggers (random or fixed), NPC/sign flavor text |
| UI/UX | Title screen, HUD, battle menu, dialogue box, victory/defeat screens |
| Audio | 1 overworld theme, 1 battle theme, 1 boss theme, 3-5 SFX (attack, hit, magic, victory, menu blip) |
| Platform | Browser (desktop-first, keyboard input; document mobile/touch as a stretch consideration) |

This scope is intentionally small so it can be finished to a *high polish bar* rather than broad but shallow. Claude should push back if any of these are ambiguous and resolve them into the GDD with concrete numeric values (tile size, resolution, frame counts, HP/damage numbers).

## 3. Recommended Technical Stack

For a browser-native SNES-style RPG proof of concept, the stack should prioritize a mature 2D engine with first-class tilemap and sprite support, since it must ship fast and look authentic.

| Layer | Recommendation | Why |
|---|---|---|
| Game engine | Phaser 3 (JavaScript/TypeScript) | Purpose-built for 2D browser games, native Tiled JSON tilemap support, sprite/animation system, scene manager suits a turn-based RPG's Overworld→Battle scene split[^2][^3] |
| Map/level authoring | Tiled Map Editor, exported as JSON, loaded via `Phaser.Loader` tilemap JSON API | Industry-standard free tool; Phaser has native loaders (`load.tilemapTiledJSON`) and helper APIs (`addTilesetImage`, `createLayer`) so agents can iterate on level data without touching engine code[^4][^5][^6] |
| Sprite/pixel art tooling | Aseprite (or equivalent pixel editor) for cleanup of AI-generated art, packed into spritesheets | AI image tools rarely produce clean, animation-ready, palette-consistent pixel sheets; a deterministic cleanup pass is required |
| Audio tooling | Chiptune/8-bit AI music generators for drafts, refined/looped by an audio agent | Multiple AI chiptune generators (e.g., text-to-chiptune tools trained on NES/SNES-style waveforms) can produce royalty-free draft tracks in seconds, then be trimmed/looped for seamless in-game use[^7][^8] |
| Version control | GitHub (monorepo), trunk-based with feature branches per agent/task | Matches the requirement for professional revision history, PR-based review, and parallel agent work |
| Build/deploy | Vite (bundler) + GitHub Pages or Netlify for POC hosting | Fast dev server, trivial static hosting for a browser build with no backend needed |
| CI | GitHub Actions: lint, type-check, automated Playwright smoke test (load title → start battle → win) | Keeps multiple agents from regressing shared systems without a human catching it every time |

**SNES authenticity constraints to encode into the spec (these are hardware facts, not aesthetic opinions):** SNES backgrounds are built from 8x8 pixel tiles (optionally grouped into 16x16 tiles = four 8x8 tiles), and hardware sprites use 4bpp (16-color) tiles with palette groups selected per-sprite, with the largest common sprite sizes being 32x32 or 64x64 assembled from tile grids. For an authentic look, standardize the project's base sprite/tile grid at 16x16 pixels (a common "SNES JRPG" scale used by Dragon Quest/7th Saga-era games) with a limited palette per asset (12-16 colors), and enforce this constraint as a hard rule in the agent instructions so AI-generated art gets normalized to it rather than left at arbitrary AI-native resolutions.[^9][^10]

## 4. Multi-Agent Orchestration Architecture (for Claude)

Claude Code supports two complementary parallelization primitives that this plan should combine: **subagents** (task-scoped workers that report back to one orchestrator, ideal for quick, bounded, non-communicating work) and **agent teams** (independent Claude sessions with their own context that message each other directly and share a task list, ideal for interdependent creative/technical work that benefits from cross-review). The recommended structure below assigns clear file/domain ownership per agent to avoid the most common team failure mode: two agents editing the same files.[^11][^12]

**Recommended team composition (agent teams, 5-6 tasks each to start):**

| Role | Ownership | Key deliverables |
|---|---|---|
| Lead/Orchestrator (Claude, main session) | GDD, task breakdown, PR review/merge, quality gate enforcement | Locked GDD, milestone plan, final integration |
| Engine/Systems Agent | Core game loop, scene management, save state, input handling | Overworld scene, Battle scene, state machine |
| Combat Agent | Turn-based battle logic, damage formulas, AI for mobs/boss | Battle resolver, enemy behavior scripts, buff/defend logic |
| Level/World Agent | Tiled maps, encounter zones, collision, NPC placement | Exported tilemap JSON, collision layers, trigger data |
| Art/Asset Agent | Sprite sheets, tileset art, UI chrome, palette conformance | Cleaned, animation-ready spritesheets and tilesets matching the 16x16/4bpp-style spec |
| Audio Agent | Music composition/curation, SFX, looping, mixing | Looped OGG/MP3 tracks, SFX bank, volume-balanced audio manifest |
| QA/Docs Agent | Automated tests, playtesting notes, documentation, CLAUDE.md upkeep | Playwright smoke tests, bug log, updated docs |

Each teammate should be spawned with an explicit prompt naming its owned file paths (e.g., "you own `src/scenes/battle/**` only"), and the lead should use `isolation: worktree` for subagents doing implementation so parallel branches never collide before PR review. Use hooks (`TaskCompleted`, `TeammateIdle`) to enforce a quality gate — e.g., block a task from being marked complete until its automated test passes.[^12][^11]

**Recommended workflow per feature:**
1. Lead creates a GitHub issue and a shared task-list entry with acceptance criteria.
2. Assigned agent works in an isolated worktree/branch, commits incrementally with conventional commit messages.
3. Agent opens a PR; a second agent (or Claude itself via `request_copilot_review`-equivalent) reviews it.
4. CI runs lint/build/smoke test; lead merges once green.
5. Lead updates the shared `CLAUDE.md`/context docs so future agents inherit the latest conventions automatically, since subagents and teammates load `CLAUDE.md` at spawn time.[^11][^12]

## 5. Repository and Documentation Structure (GitHub-First Workflow)

To make the project genuinely "other agents can work on parts of it," the repo needs machine-readable context baked in, not just a README for humans.

```
/repo-root
  CLAUDE.md                 <- project conventions, coding standards, art/audio specs, loaded by every agent
  /docs
    GDD.md                  <- locked game design doc (source of truth for scope)
    ART_BIBLE.md             <- palette rules, resolution rules, animation frame counts, reference sheets
    AUDIO_BIBLE.md           <- tempo/key conventions per track, looping requirements, mixing levels
    ARCHITECTURE.md          <- scene graph, state machine, data flow
    AGENT_GUIDE.md            <- which agent owns which folder, how to claim/complete tasks
  /src
    /scenes (boot, title, overworld, battle, victory)
    /entities (player, enemies, boss)
    /systems (combat, movement, save, audio-manager)
    /data (enemy stats JSON, dialogue JSON, level configs)
  /assets
    /sprites  /tilesets  /audio  /ui
  /tests (Playwright + unit tests)
  .github/workflows (CI: lint, build, test)
```

Every PR should reference its GitHub issue, and commits should follow Conventional Commits (`feat:`, `fix:`, `art:`, `audio:`) so the history itself documents the build for future agents or human contributors reviewing revision history — directly satisfying the "develop like a professional, use GitHub for revision history" requirement.

## 6. Combat and Core Mechanics Specification (Draft for Claude to Deepen)

Claude should formalize exact numbers, but the POC should encode these 7th Saga-inspired rules as testable specs:

- **Defend mechanic:** Selecting Defend reduces incoming damage this turn by a fixed percentage AND increases the character's next Attack damage by a bonus multiplier, directly mirroring the source game's "defend buffs your next hit" design that reviewers called out as the system's best idea.[^1]
- **Turn resolution order:** Party member acts, then any enemy targeting that member resolves immediately after — preserving the "bait and read" tactical layer described in the source material, rather than a flat speed-stat queue.[^1]
- **Buff-driven combat, not attack spam:** At least one spell/item should meaningfully buff a stat (attack/defense/agility) rather than just dealing damage, since this was identified as the mechanic that made encounters interesting rather than decorative.[^1]
- **Visible enemy "tells":** Each mob and the boss should have at least one readable animation cue before or during their signature attack (idle bob, wind-up frame, or a visual state change on taking damage), replicating the "spider steps forward before attacking" texture noted in the breakdown.[^1]
- **Lethality without grind:** Damage numbers should be tuned so an unprepared player can lose a fight in 2-4 turns (tension), but the POC's single stage should never require grinding — this is the explicit fix for the source game's "grind tax" flaw.[^1]

## 7. Modern Quality-of-Life Features (Research-Backed, Non-Intrusive)

The brief asks specifically what modern QoL should be added without harming the retro feel. Based on the source critique and general genre conventions, the following are recommended as "invisible" improvements — things a genre fan would barely notice as modern, because they quietly fix things 1990s RPGs got wrong without changing the combat feel:

- **Clear, in-context Defend tooltip/first-use hint** — the breakdown explicitly flags that even guides, NPCs, and the manual failed to make players understand Defend's real function for 30 years; a single one-time on-screen hint the first time Defend is available removes this friction with zero gameplay cost.[^1]
- **Readable, low-noise encounter design** — since the source game's "juke the monster" radar mechanic mostly failed due to poor maneuverability in tight spaces, the POC should keep encounter zones intentional and telegraphed (visible patrol sprites or clearly-bounded grass/trigger tiles) rather than a blind random-encounter carpet.[^1]
- **Instant, skippable text and battle animations** — hold-to-fast-forward on dialogue and attack animations, standard in modern retro-inspired titles, preserves pacing without touching combat math.
- **Auto-save at scene transitions** — removes punishing death resets without adding any UI the player has to manage.
- **Damage/heal number pop-ups and HP bar tweening** — pure legibility improvements; SNES games often lacked these due to hardware constraints, not design intent.
- **Remappable keys / gamepad support via a browser Gamepad API hook** — trivial to add in Phaser and expected by modern browser-game players, with zero impact on the turn-based feel.

These should be documented as an explicit "QoL allowlist" in the GDD so agents don't over-add modern conveniences (e.g., auto-battle, difficulty sliders) that would dilute the intentionally tense, high-stakes combat identity the brief wants preserved.

## 8. Visual and Audio Production Pipeline

**Art pipeline (Grok/X for asset ideation + manual pixel-cleanup pass):** Grok's image generation tooling (Grok Imagine) now supports fast iteration (2-3 seconds per image) and multi-image/style-reference editing for consistent character and asset generation, which is well suited to rapidly iterating concept sprites, enemy designs, and tileset motifs before a cleanup pass. Because AI image generators are not natively grid-locked or palette-locked, every generated asset must go through a deterministic normalization step: downscale/snap to the 16x16 (or 32x32 for bosses) grid, quantize to a 12-16 color palette per sprite group, and hand-align animation frames — this should be an explicit Art Agent task, not left to the generator's raw output.[^13][^14]

**Audio pipeline (AI chiptune generation + manual loop/mix pass):** AI-driven 8-bit/chiptune generators can produce full draft tracks (intro, main theme, natural ending) from a text prompt describing mood, tempo, and game scenario (e.g., "tense boss-fight theme with fast arpeggio lead"), and these are generated royalty-free from scratch rather than sampled, which resolves licensing risk entirely. The Audio Agent's job is then to trim these into seamless loops, normalize volume across tracks, and export to a web-friendly format (OGG/MP3) with defined loop points documented in `AUDIO_BIBLE.md`.[^7][^8]

**Trailer/marketing asset generation (Kling):** Since the user's affiliate marketing team has access to Kling for video/audio, this should be scoped as a separate, parallel workstream (not blocking the game build) to produce a short POC trailer: a Kling-generated cinematic intro/trailer cut combining in-engine capture with stylized transitions, useful for pitching or showcasing the finished POC once core scenes are stable enough to record.

## 9. Milestone Plan (for Claude to Expand into Sprints/Issues)

| Milestone | Key exit criteria |
|---|---|
| M0 — Design Lock | GDD, Art Bible, Audio Bible finalized and merged; repo scaffolded with CI |
| M1 — Vertical Slice Engine | Player can move on one test map, trigger a placeholder battle, and return to overworld |
| M2 — Combat Core | Attack/Defend/Magic/Run fully functional against 1 mob with real stats and animations |
| M3 — Content Fill | All 2-3 normal mobs + boss implemented with unique sprites, tells, and audio |
| M4 — Polish Pass | Full stage assembled, music/SFX integrated, QoL features added, UI chrome finalized |
| M5 — POC Release | Automated smoke tests pass, build deployed to a public URL, README/demo GIF finalized |

Each milestone should map to a GitHub Milestone with issues labeled by owning agent, so progress is visible in revision history exactly as the brief requests.

## 10. Must-Have Resources Checklist

- Phaser 3 + Vite starter template, Tiled Map Editor (both free/open-source).[^2][^4]
- A pixel-art cleanup tool (Aseprite or equivalent) for normalizing AI-generated sprites to a fixed grid and palette.
- An AI chiptune/8-bit music generation tool for royalty-free draft scoring, refined by the Audio Agent.[^8][^7]
- Grok Imagine (or equivalent) for rapid concept/sprite ideation with style-reference consistency.[^14][^13]
- Kling for POC trailer/marketing video production via the affiliate marketing team's existing access.
- GitHub repository with Actions CI, branch protection, and PR templates enforcing the CLAUDE.md/GDD conventions.
- Playwright (or similar) for automated browser smoke testing of the POC build.

## 11. Open Questions for Claude to Resolve Before Coding

Claude should treat these as required decisions to lock in the GDD, not optional nice-to-haves:

- Exact resolution and canvas scaling strategy (e.g., native 256x224-style internal resolution scaled up with pixel-perfect nearest-neighbor filtering to preserve the SNES look on modern displays).
- Exact damage formulas, HP pools, and turn-speed rules for the one hero, each mob, and the boss.
- Whether the "boss phase change" is a stat shift, a new attack, or a visual transformation (all should be storyboarded before art is generated).
- Final file formats and loop-point convention for audio, and target total asset budget (KB) to keep the browser build lightweight.
- Whether input remapping/gamepad support ships in the POC or is documented as a fast-follow, given the "one stage" scope constraint.

---

## References

1. [How to create a turn-based RPG in Phaser 3](https://phaser.io/news/2018/09/how-to-create-a-turn-based-rpg-in-phaser-3) - In this tutorial series you will make a turn-based RPG similar to the early Final Fantasy games, all...

2. [Monster Tamer - RPG Tutorial with Phaser 3 - Ep. 1](https://www.youtube.com/watch?v=ibeaQ3vW-MM) - Learn how to create dynamic and engaging turn-based battles between players and wild monsters. Imple...

3. [Phaser - How to create a turn-based RPG in Phaser 3 Part 2](https://phaser.io/news/2018/09/how-to-create-a-turn-based-rpg-in-phaser-3-part2) - Learn how to make a turn-based RPG game. In this part you create the battle scene and fight sequence...

4. [Phaser RPG Tutorial: Build a Top-Down RPG with Combat ...](https://generalistprogrammer.com/tutorials/phaser-rpg-tutorial) - Complete Phaser 3 RPG tutorial with tile-based world, grid movement, NPC dialogue, quest system, tur...

5. [Nintendo Entertainment System](https://www.cosmigo.com/promotion/docs/onlinehelp/gfxHardware-NES.htm)

6. [Turn Based Battle using Phaser - Medium](https://medium.com/@davidang/turn-based-battle-using-phaser-c0e1e1629399) - Our heroes faces a group of trolls. Everyone takes turn to attack, following a priority queue system...

7. [Tile size map size questions, SNES](https://forums.nesdev.org/viewtopic.php?t=14782)

8. [Sprites - SNESdev Wiki](https://snes.nesdev.org/wiki/Sprites) - Sprites allow 16-color graphics tiles to be rendered at freely placed locations on the screen, indep...

9. [How To Make A Turn-Based RPG Game In Phaser - Part 3](https://gamedevacademy.org/phaser-rpg-tutorial-3/) - In the last tutorial we added a WorldState where the player can navigate and linked it with the Batt...

10. [SNES Overview](https://nesdoug.com/2020/04/02/snes-overview/) - The Super Nintendo first came out in 1991 (1990 in Japan as the Super Famicom). It was one of the be...

11. [Retro Development](https://megacatstudios.com/blogs/retro-development/tagged/snes-graphics-guide) - Mega Cat Studios is a creative first games agency based out of Pittsburgh, PA with a global team. Co...

12. [Tiles - SNESdev Wiki](https://snes.nesdev.org/wiki/Tiles) - Graphics tile data is stored in VRAM, to be used by backgrounds and sprites. Each tile is an 8x8 pix...

13. [Lesson P35 - Hardware Sprites on the SNES / Super Famicom](https://www.youtube.com/watch?v=8W6Yg6UAReA) - The SNES has some pretty powerful hardware sprites - but unfortunately they're not the most simple!
...

14. [Please help consolidate all info for pixel artists for SNES](https://forums.nesdev.org/viewtopic.php?t=15953)

