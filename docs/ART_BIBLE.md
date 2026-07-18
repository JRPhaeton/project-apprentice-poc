# Art Bible — Trial of the Apprentice
**STATUS: LOCKED (M3, 2026-07-17).** Per PLAN §9, M4 generation now runs against this locked bible: sprite dimensions (overworld 16 / mob 64 / boss 96), per-animation frame counts, and the loop/seam convention below are fixed. Changes require an orchestrator-approved GDD amendment.

## 1. Grid & Dimensions (from PLAN §2, canonical)

- All art on a **16×16 grid**; every frame size a multiple of 16. Hardware truth: 8×8 SNES tiles, 4bpp.
- **Overworld tiles: 16×16.** Patrol minis 16×16. **Overworld hero: 16×24** (M8 amendment, below).
- **M8 amendment (overworld depth pass, per the approved M8 plan):**
  - **Hero overworld sprite is 16×24** (FF6 tall proportion: head ~10 of 24 px, ¾ stance, 5-ramp cloak + shared outline + rim light), 2-frame walk per facing, unchanged anim names/pairs. Sheet is **128×48** — 8 frames on the top row, bottom frame row transparent padding so the PNG stays on CI's 16px grid. Physics keeps the 16×14 feet box, so walk feel and E2E routes are untouched.
  - **Patrol markers are creature minis**: `overworld-minis.png` 128×16 — spider/wisp/revenant 2-frame idle bobs (manifest `enemy.minis`, frameRate 2) + frame 6 blob shadow (palette-alpha, drawn under hero and patrols).
  - **Tileset v2 is 256×128** (16×8 grid, 123 of 128 slots used; layout + `collide`/`anim` tile-property tables live in `tools/tileset_v2.py`): base terrains (grass ×3 variants incl. a feathered dark patch, dark-grass, mud, ruin-floor), five marching-squares transition sets (path↔grass, water↔grass, mud↔dark-grass full 16-mask; marsh-water↔mud, ruin-floor↔dark-grass minimal 12-mask), tree family (collide trunks on grass/dark bases, 16-mask scallop-cut canopy set + 3 one-tile hang fringes — both on the `overhead` layer rendered above the hero), wall/gate/ruin-wall/cliff top+face pairs (faces collide on the ground layer; prop-free tops are the overhead caps, plus cap-lip strips), sign ×3 bases, door, decor (rock, stump, bones, reeds, flowers, rubble, pebbles, ember-glow), and shadow-edge variants of every walkable base for cells south of walls/trees.
  - **Engine contract is property-driven**: `collide: true` on solids, `anim: 'water' | 'marshwater' | 'ember'` on shimmer cells — the engine never reads tile indices. `tile-anim.png` frame 0 of each pair is pixel-identical to the anim-tagged tileset tile.
  - Maps are regenerated ONLY via `tools/gen_maps.py` (topology-preserving compositor: collide grid + objects layer asserted equal to v1).
- **M10 amendment ("The Vale Alive", per the approved M10 plan):**
  - **Treasure chest is 16×16**, 2 frames (0 closed / 1 open) on a 32×16 sheet — manifest `chest`, anim `open` [1] @1 once; frame 0 is the closed default. Banded wooden chest; the ember-glint lock and open-mouth glow are sanctioned warm interaction glints (§2). Chest objects are non-colliding walk-over cells (sign-style interact), so walk routes are untouched.
  - **Gate Keeper npc is 16×24** (hero proportions), 2-frame idle sway on a 32×48 sheet — top row only, bottom frame row transparent for the CI 16px grid — manifest `npc.keeper`, anim `idle` [0,1] @2 loop. Older robed figure in desaturated warm greys + bone beard; his lantern carries the warm ember dot (§2 names the Keeper's lantern a warm-accent element).
  - **Emberheart is 32×32**, 2-frame flicker on a 64×32 sheet — manifest `fx.emberheart`, anim `burn` [0,1] @4 loop, for the Victory relight beat. Frame 0 is pixel-identical to the PWA icon key art (generator self-check).
  - Maps still regenerate ONLY via `tools/gen_maps.py`; its assertion policy is amended exactly this far: collide grid still byte-equal to v1; all pre-M10 objects present verbatim IN ORDER as the layer prefix; the `tools/room_extras.py` extras (7 chests + the room1 Keeper npc) appended at the tail with fresh sequential ids; every extra-covered cell asserted walkable (non-collide ground) and non-overlapping with every pre-M10 object rect.
- **Battle mobs: 64×64** (4×4 tiles) — Vale Spider, Marsh Wisp, Revenant.
- **Boss: 96×96** (6×6 tiles) — Cloaked Chimera. No sprite/tileset frame may exceed 96×96 (asset-lint).
- Internal resolution 256×224, camera shows 16×14 tiles. Compose battle layouts against that frame.
- Spritesheets exported via Aseprite CLI (scripted); manifest-driven (`art-manifest.json` carries `frameWidth/Height` + anim defs), so the M4 placeholder→final swap is a pure data diff. Keep the logical IDs from day one: `hero`, `enemy.spider`, `enemy.wisp`, `enemy.revenant`, `enemy.chimera`, plus tileset/UI IDs.

## 2. Palette Rules

- **≤ 16 colors per sprite/sheet** (asset-lint blocks merge; pngquant quantize + palette-count verify per PLAN §6).
- **Master palette direction (draft):** desaturated dusk — cool blue-gray environment ramps (stone, marsh water, twilight sky), muted forest greens, with a single **warm ember accent** (amber/orange) reserved for hope-coded elements: the hero's trim, save/interaction glints, the Keeper's lantern, victory UI. Enemies skew cold (violet/teal/bone). This is the "hopeful yet sad" tone in color: cold world, warm hero.
- Shared dark outline color (near-black blue, not pure black) across all battle sprites for cohesion against dark backdrops.
- Build one master pool (~32 colors) at M3 lock; each sprite draws its ≤ 16 from that pool. Until lock, placeholders (Kenney CC0 etc.) are exempt from palette direction but not from the ≤ 16 count.

## 3. Animation Frame Counts (per unit, draft — final counts lock at M3)

Convention matches the PLAN §4 manifest example (`idle` [0,1] @4fps loop, `step` [2,3] @8fps once, `bite` [4,5,6] @12fps once):

| Anim role | Frames | Rate | Repeat |
|---|---|---|---|
| idle | **2** | 4 | loop (−1) |
| tell / step | **2** | 8 | once |
| attack | **3** | 12 | once |

Per unit (battle sprites):

- **Vale Spider (64×64):** `idle` 2, `step` 2 (the tell), `bite` 3. 7 frames.
- **Marsh Wisp (64×64):** `idle` 2, `tell` 2 (cast flare — precedes/marks Weaken), `attack` 3. 7 frames.
- **Revenant (64×64):** `idle` 2, `tell` 2, `attack` 3. Revive "reassembles" visual: v0 = `tell` frames reversed + code-side flash/tween, no dedicated frames; dedicated `revive` frames are an M3 lock decision.
- **Cloaked Chimera (96×96), ONE preloaded sheet, two anim groups** (PLAN §4 — `phaseChanged` switches groups, no mid-battle load):
  - `cloaked.idle` 2, `cloaked.attack` 3
  - `uncloaked.idle` 2, `uncloaked.tell` 2 (Flame Breath is always telegraphed one full turn ahead), `uncloaked.attack` 3, `uncloaked.breath` 3
  - Cloak-off transition: v0 = group switch + screen flash; optional 2-frame `transition` group is an M3 decision. **Storyboard the cloak-off moment before art generation** (PLAN §5.3).
- **Hero battle sprite (64×64):** `idle` 2, `defend` 2 (readable guard pose — Defend is the core verb, make it unmistakable), `attack` 3.
- Overworld: hero (16×24, M8) 2-frame walk per facing; patrol minis (16×16) 2-frame idle bob; Keeper npc (16×24, M10) 2-frame idle sway; chest (16×16, M10) closed/open pair; Emberheart fx (32×32, M10) 2-frame flicker.

## 4. UI Chrome (draft)

- SNES-style dialogue/menu panels: near-black navy fill, 1px light border + 1px inner shadow, generous padding; parchment-tint variant for signs.
- Bitmap font on the 8×8 grid, high-contrast off-white; warm ember accent for selection cursor and victory text only.
- Damage popups: small bitmap numerals, white (hero-dealt) / red (hero-taken); HP bars tween (PLAN §8).
- Tell indicator: consistent visual language — enemy plays its tell anim **plus** a fixed screen-space cue (e.g. "!" glyph in ember accent) so tells stay readable on every enemy.

## 5. Per-Enemy Visual Descriptions (draft)

- **Vale Spider:** bulky forest spider, moss-and-bone palette, low stance filling the lower 64×64. **Tell = a full body-length step toward the hero** (`step` frames shift the silhouette visibly forward ~8px inside the frame); bite rears up then lunges. Must read at a glance: forward = danger next turn.
- **Marsh Wisp:** a hovering pale flame-orb with a faint trailing wisp, teal-white core — deliberately lantern-like (echoes `dlg-sign-marsh`: lights that are not stars). Idle bobs; cast tell = core flares and dims the trail; attack = a thrown spark.
- **Revenant:** gaunt assembled-bones-and-grave-cloth figure, violet/bone palette, slow heavy poses (SPD 3). On revive it visibly **reassembles** — pieces pull back together (reversed tell frames + flash in v0).
- **Cloaked Chimera:** 96×96. **Cloaked group:** a tall shrouded mass, silhouette ambiguous, only claws and one eye-glint visible — reads as a robed pilgrim, not yet a monster. **Uncloaked group:** cloak gone, fused multi-beast revealed (leonine mass, secondary head, scaled haunches — keep it a generic mythological chimera, no resemblance to any named source-game design), palette shifts hotter (embers in mane) since it now owns fire. Flame Breath tell = deep inhale, chest/throat glow building over the full telegraph turn.

## 6. §0 Resemblance Checklist (required on every art PR)

Per PLAN §0/§11 — reviewer checks each box before merge:

- [ ] No ripped, traced, or ROM-derived material, including "just for placeholder".
- [ ] No visual resemblance to the source game's **named designs** (characters, monsters, locations) — compare against reference before merge.
- [ ] No source-game names in filenames, logical IDs, or metadata ("7th Saga", "Elnard", Kamil, Esuna, Olvan, Lux, Valsu, Wilme, Lejes, original location/item names).
- [ ] Placeholder assets are CC0 (or equivalent) with license recorded in `assets/CREDITS.md`.
- [ ] Dimensions on-grid (16 multiple, ≤ 96×96), palette ≤ 16 per sheet, logical IDs match `art-manifest.json`.
