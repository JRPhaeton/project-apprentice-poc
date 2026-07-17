# Asset Credits & Licenses

## M4 final art (current)

All shipped art is **generated programmatically by `tools/gen_placeholders.py`**
(the M2 placeholder generator evolved into the final-art generator —
deterministic: no randomness, Bayer-matrix dithering and arithmetic detail
placement only; re-running the script reproduces every file byte-for-byte).
It is authored in-repo by this project's Assets lane, contains no
third-party, ripped, traced, or ROM-derived material (PLAN §0), and is
dedicated to the public domain under **CC0 1.0 Universal**.

| File | Size | Content | License |
|---|---|---|---|
| `public/assets/tilesets/overworld.png` | 256×16 | 16 overworld tiles 16×16 (0 grass, 1 path, 2 tree, 3 water, 4 wall, 5 sign, 6 flower, 7 dark-grass, 8 mud, 9 marsh-water, 10 reed, 11 ruin-floor, 12 ruin-wall, 13 ruin-door, 14 rubble/bones, 15 ember-glow) | CC0 (self-authored) |
| `public/assets/sprites/hero-overworld.png` | 64×16 | 4 hero facings 16×16 (0 down, 1 up, 2 left, 3 right) | CC0 (self-authored) |
| `public/assets/sprites/spider.png` | 448×64 | 7 battle frames 64×64 (idle ×2, step tell ×2, bite ×3) | CC0 (self-authored) |
| `public/assets/sprites/wisp.png` | 448×64 | 7 battle frames 64×64 (idle ×2, cast ×2, attack ×3) | CC0 (self-authored) |
| `public/assets/sprites/revenant.png` | 448×64 | 7 battle frames 64×64 (idle ×2, reassemble ×2, attack ×3) | CC0 (self-authored) |
| `public/assets/sprites/chimera.png` | 1440×96 | 15 boss frames 96×96 (cloaked idle ×2 / attack ×3, uncloaked idle ×2 / attack ×3 / breath tell ×2 / flame breath ×3) | CC0 (self-authored) |

Palette discipline (ART_BIBLE §2, verified by the script's self-checks):
tileset drawn from one ≤ 32-color master pool with ≤ 16 colors per tile;
every sprite sheet ≤ 16 unique colors; shared near-black-blue outline;
warm ember accent reserved for the hero, interaction glints (sign nails,
ruin-door glow), and the Chimera's fire. Tile indices 0–7 keep their M2
identities; 8–15 are the M4 marsh/ruin extension.

## M4 audio (current)

All shipped audio is **composed and synthesized in code by
`tools/gen_audio.py`** (deterministic numpy synthesis from note tables —
square/triangle/noise chiptune voices — encoded via ffmpeg to OGG Vorbis
q3.5 + AAC 128k at the exact `src/data/audio-manifest.json` paths). It is
authored in-repo by this project's Assets lane; no third-party samples,
recordings, or source-game material of any kind (PLAN §0, AUDIO_BIBLE §7),
and is dedicated to the public domain under **CC0 1.0 Universal**.

| Asset | Files | Content | License |
|---|---|---|---|
| `music.overworld` | `audio/overworld.ogg/.m4a` | ~45.7 s loop, 84 BPM A minor, hopeful-yet-sad (i–VI–III–VII verse, V-major lift) | CC0 (self-authored) |
| `music.battle` | `audio/battle.ogg/.m4a` | ~34.3 s loop, 140 BPM, driving bass arpeggio + urgent lead | CC0 (self-authored) |
| `music.boss` | `audio/boss.ogg/.m4a` | ~32.7 s loop, 147 BPM C minor, low ostinato + dissonant stabs | CC0 (self-authored) |
| `sfx.attack/hit/magic/victory/menu` | `audio/sfx-*.ogg/.m4a` | ≤ 1.5 s one-shots (whoosh, crunch, sparkle arpeggio, fanfare, blip) | CC0 (self-authored) |

Loop convention per AUDIO_BIBLE §3: self-contained full-file seamless
loops, exact bar-length sample counts, echo tails wrapped circularly to the
loop start, both ends at zero crossings (verified by the script's seam
self-check). Music loudness-normalized in-file to −16 LUFS (true peak
≤ −1 dBFS); SFX peak-normalized to −3 dBFS; per-asset mix trims live only
in the manifest `volume` field. The CC0 fallback named in PLAN §11
(OpenGameArt/Kenney chiptune) was **not needed**.

## Replacement/provenance policy

The logical IDs in `src/data/art-manifest.json` and
`src/data/audio-manifest.json` are stable; any future asset replacement is
a pure manifest/file swap (PLAN §6). Any third-party or AI-generated asset
added later gets its own row here with source and license before merge
(PLAN §0 review checklist).
