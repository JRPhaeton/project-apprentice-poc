# Art Bible — Trial of the Apprentice
**STATUS: LOCKED (M3, 2026-07-17; palette section rewritten M11, 2026-07-18 per GDD amendment row 11).** Per PLAN §9, generation runs against this locked bible: sprite dimensions (overworld 16 / mob 64 / boss 96), per-animation frame counts, and the loop/seam convention below are fixed. Changes require an orchestrator-approved GDD amendment.

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
- **M11 amendment ("Modern 2D", per the approved M11 plan + GDD row 11):** all dims and frame sizes unchanged; three anims gain frames and the backdrops split into parallax pairs:
  - **Marsh Wisp battle idle 2→4 frames** (breathing loop): sheet 576×64, 9 frames — `idle` [0,1,2,3] @8, `cast` [4,5] @8, `attack` [6,7,8] @12.
  - **Chimera `uncloaked.idle` 2→4 frames** (wing-beat loop): sheet 1632×96, 17 frames — cloaked group unchanged [0..4]; `uncloaked.idle` [5,6,7,8] @8, `uncloaked.attack` [9,10,11], `uncloaked.tell` [12,13], `uncloaked.breath` [14,15,16].
  - **Emberheart `burn` 2→4 frames**: sheet 128×32 — `burn` [0,1,2,3] @8. Frame 0 keeps the PWA icon's opaque silhouette (self-check); the icons themselves stay M10 art.
  - **Backdrops become parallax pairs** per biome: manifest `backdrop.<biome>.far` (256×144 full scene) + `backdrop.<biome>.near` (256×64 band, transparent top, x-seamless, engine drifts it ±4px); the legacy `backdrop.<biome>` key ALIASES the -far file until the Engine lane consumes the pairs (landing-race guard, self-checked). New overlay strips `fx.shafts` (256×144) and `fx.fog` (256×64), screen-blend-ready.
- **Battle mobs: 64×64** (4×4 tiles) — Vale Spider, Marsh Wisp, Revenant.
- **Boss: 96×96** (6×6 tiles) — Cloaked Chimera. No sprite/tileset frame may exceed 96×96 (asset-lint).
- Internal resolution 256×224, camera shows 16×14 tiles. Compose battle layouts against that frame.
- Spritesheets exported via Aseprite CLI (scripted); manifest-driven (`art-manifest.json` carries `frameWidth/Height` + anim defs), so the M4 placeholder→final swap is a pure data diff. Keep the logical IDs from day one: `hero`, `enemy.spider`, `enemy.wisp`, `enemy.revenant`, `enemy.chimera`, plus tileset/UI IDs.

## 2. Palette Rules (M11 "Modern 2D" — GDD amendment row 11)

The SNES-authentic ≤ 16-color/4bpp cap (M3–M10) is **retired**. M11 moves the game to the modern-2D register (Chained Echoes reference): high-color pixel art on the unchanged 16×16 grid. The caps live in the GENERATOR self-checks (`tools/gen_placeholders.py`) — CI's source-asset-lint still enforces only the 16px grid.

- **Budgets (enforced by generator self-checks):**
  - Sprite sheets: **≤ 48 unique colors per sheet**.
  - Tileset: **≤ 64-color master pool** on the sheet, soft cap **≤ 24 colors per 16×16 tile**.
  - Backdrops + full-screen fx overlay strips (`fx-shafts` / `fx-fog`): **≤ 96 colors per file**; overlays additionally alpha-quantized and translucent (alpha peak ≤ 200, screen-blend-ready).
- **Modern-pixel signatures (applied everywhere, M11):**
  - **6–8 step ramps with hue-shifted ends** — shadows shift cool (blue/violet/teal), lights shift warm; never a plain darken/lighten of the same hue.
  - **Soft interior anti-aliasing** at ramp boundaries (midpoint blends at staircase corners, bounded per ramp family); outlines stay crisp.
  - **Rim light + bounce light** on sprites (warm top/left key, cool bottom/right bounce); **specular glints** on metal/wet surfaces.
  - **Texture detail** on tiles: individual two-tone grass blades, bark striations, stone cracks + moss, water depth gradients.
  - **Painterly backdrops**: multi-stop quantized sky gradients, silhouette layers with rim-lit edges, per-biome parallax pairs (`<biome>-far.png` 256×144 full scene + `<biome>-near.png` 256×64 near band, transparent top, x-seamless).
- **Master palette direction (unchanged in spirit):** desaturated dusk — cool blue-gray environment ramps, muted forest greens, with the single **warm ember accent** reserved for hope-coded elements: the hero's trim, save/interaction glints, the Keeper's lantern, victory UI, the Chimera's/lair's fire. Enemies skew cold (violet/teal/bone). Cold world, warm hero.
- Shared dark outline color (near-black blue `#141628`, not pure black) across all battle sprites for cohesion against dark backdrops.
- **PWA icons are exempt** and keep the M10 16-color key art byte-for-byte; the M11 emberheart sprite re-lights the same art at the modern budget, so its frame 0 keeps the icon's opaque **silhouette** (self-checked) rather than its exact pixels.

## 3. Animation Frame Counts (per unit, draft — final counts lock at M3)

Convention matches the PLAN §4 manifest example (`idle` [0,1] @4fps loop, `step` [2,3] @8fps once, `bite` [4,5,6] @12fps once):

| Anim role | Frames | Rate | Repeat |
|---|---|---|---|
| idle | **2** | 4 | loop (−1) |
| tell / step | **2** | 8 | once |
| attack | **3** | 12 | once |

Per unit (battle sprites):

- **Vale Spider (64×64):** `idle` 2, `step` 2 (the tell), `bite` 3. 7 frames.
- **Marsh Wisp (64×64):** `idle` **4** (M11 breathing loop), `tell` 2 (cast flare — precedes/marks Weaken), `attack` 3. 9 frames.
- **Revenant (64×64):** `idle` 2, `tell` 2, `attack` 3. Revive "reassembles" visual: v0 = `tell` frames reversed + code-side flash/tween, no dedicated frames; dedicated `revive` frames are an M3 lock decision.
- **Cloaked Chimera (96×96), ONE preloaded sheet, two anim groups** (PLAN §4 — `phaseChanged` switches groups, no mid-battle load):
  - `cloaked.idle` 2, `cloaked.attack` 3
  - `uncloaked.idle` **4** (M11 wing-beat loop), `uncloaked.tell` 2 (Flame Breath is always telegraphed one full turn ahead), `uncloaked.attack` 3, `uncloaked.breath` 3
  - Cloak-off transition: v0 = group switch + screen flash; optional 2-frame `transition` group is an M3 decision. **Storyboard the cloak-off moment before art generation** (PLAN §5.3).
- **Hero battle sprite (64×64):** `idle` 2, `defend` 2 (readable guard pose — Defend is the core verb, make it unmistakable), `attack` 3.
- Overworld: hero (16×24, M8) 2-frame walk per facing; patrol minis (16×16) 2-frame idle bob; Keeper npc (16×24, M10) 2-frame idle sway; chest (16×16, M10) closed/open pair; Emberheart fx (32×32) **4-frame burn (M11)**.

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
- [ ] Dimensions on-grid (16 multiple; frames ≤ 96×96 — backdrop/tileset/fx-overlay strips exempt), palettes within the M11 budgets (§2: 48 sprite / 64+24 tileset / 96 backdrop), logical IDs match `art-manifest.json`.
