# Asset Credits & Licenses

## M2 placeholder art (current)

All placeholder art listed below is **generated programmatically by
`tools/gen_placeholders.py`** (deterministic — no randomness; re-running the
script reproduces every file byte-for-byte pixel-identical). It is authored
in-repo by this project's Assets lane, contains no third-party, ripped,
traced, or ROM-derived material (PLAN §0), and is dedicated to the public
domain under **CC0 1.0 Universal** — satisfying PLAN §6's "placeholders must
be CC0 or equivalently licensed" rule.

| File | Size | Content | License |
|---|---|---|---|
| `public/assets/tilesets/overworld.png` | 128×16 | 8 overworld tiles 16×16 (0 grass, 1 path, 2 tree, 3 water, 4 wall, 5 sign, 6 flower, 7 dark-grass) | CC0 (self-authored) |
| `public/assets/sprites/hero-overworld.png` | 64×16 | 4 hero facings 16×16 (0 down, 1 up, 2 left, 3 right) | CC0 (self-authored) |
| `public/assets/sprites/spider.png` | 448×64 | 7 battle frames 64×64 (idle ×2, step tell ×2, bite ×3) | CC0 (self-authored) |
| `public/assets/sprites/wisp.png` | 448×64 | 7 battle frames 64×64 (idle ×2, cast ×2, attack ×3) | CC0 (self-authored) |
| `public/assets/sprites/revenant.png` | 448×64 | 7 battle frames 64×64 (idle ×2, reassemble ×2, attack ×3) | CC0 (self-authored) |
| `public/assets/sprites/chimera.png` | 1440×96 | 15 boss frames 96×96 (cloaked idle ×2 / attack ×3, uncloaked idle ×2 / attack ×3 / breath tell ×2 / flame breath ×3) | CC0 (self-authored) |

Palette discipline: ≤ 16 unique colors per sheet (verified by the script's
self-check), shared near-black-blue outline, cold enemy palettes with the warm
ember accent reserved for the hero and the Chimera's fire per
`docs/ART_BIBLE.md` §2.

## Audio (M4 — not yet present)

`src/data/audio-manifest.json` paths are final (`assets/audio/*.ogg|.m4a`),
but the audio files themselves land at M4. Fallback if AI generation is
unusable (PLAN §11): CC0 chiptune from OpenGameArt/Kenney, to be recorded
here with exact pack names and URLs when picked.

## Replacement plan

Final art replaces these placeholders at **M4 as a pure manifest/file swap**
(PLAN §6): the logical IDs in `src/data/art-manifest.json` (`enemy.spider`,
`enemy.wisp`, `enemy.revenant`, `enemy.chimera`, `hero.overworld`, …) stay
stable, so no code changes. Any third-party or AI-generated final asset gets
its own row in this file with source and license before merge (PLAN §0
review checklist).
