# Audio Bible — Trial of the Apprentice

**STATUS: DRAFT.** Locks at **M3** (PLAN §9): M4 audio generation may not begin against a draft bible; the M3 lock fixes the loop/seam convention below. Budgets and CI checks are PLAN §2/§6 and bind now.

## 1. Music — 3 tracks

| ID | Use | Direction | Loop length | Load |
|---|---|---|---|---|
| `music.overworld` | Title + Overworld | **Hopeful yet sad**: minor-key lead over a warm, steady accompaniment; ~80–95 BPM; chiptune palette (2 pulse + triangle bass + light noise perc). The melody resolves upward — sad verse, hopeful cadence. | ≤ 60 s | Preload (part of the ~1.4 MB initial set, PLAN §2) |
| `music.battle` | Mob battles | **Propulsive/tense**: driving bassline, ~135–145 BPM, short phrases that loop hard; leaves headroom so tell SFX read over it. | ≤ 60 s | Lazy — first Overworld→Battle transition (PLAN §4) |
| `music.boss` | Cloaked Chimera | **Heavier**: slower harmonic rhythm, lower register, ~140–150 BPM, denser percussion; adds intensity without a phase-change track swap (the `phaseChanged` moment is carried by SFX + visuals, one track throughout). | ≤ 60 s | Lazy — with battle assets |

## 2. SFX — 5 one-shots (PLAN §6)

| ID | Use | Notes |
|---|---|---|
| `sfx.attack` | Hero/enemy attack swing | Short, percussive |
| `sfx.hit` | Damage lands | Distinct from attack; pairs with damage popup |
| `sfx.magic` | Spell cast (Heal/Power/Weaken/Flame Breath) | One shared cast sound in v0 |
| `sfx.victory` | Victory fanfare | ≤ 3 s like all SFX; the one unambiguously bright cue in the game |
| `sfx.menu` | Menu/cursor blip | Very short, low volume |

Each SFX ≤ 3 s (asset-lint via ffprobe). Tell moments reuse `sfx.menu`-class cues or silence in v0; a dedicated tell SFX is out of scope unless added by GDD amendment.

## 3. Loop Convention (M3 lock item)

- Every music track is a **self-contained full-file seamless loop**: composed to loop end→start, **both ends trimmed to zero-crossings**, no intro section, no tail reverb spill across the seam. ≤ 60 s per track.
- Playback: `this.sound.play(key, { loop: true })` — Phaser `WebAudioSound` gapless full-buffer looping (PLAN §6). Phaser has **no sub-clip loop points**; if an intro-then-loop track is ever wanted, it goes through the `WebAudioLoopPlayer` escape hatch (PLAN §6) and the manifest's optional `loopStart`/`loopEnd` fields — reserved, unused in the POC.
- Audio Agent DoD includes an audible loop-seam check per track (PLAN §11).

## 4. Encoding & Budget (PLAN §2/§3)

- **Dual codec, both shipped per entry:** OGG Vorbis **q3–q4** (~112–128 kbps stereo) primary + equivalent-bitrate **M4A/AAC** Safari fallback. asset-lint fails if either file is missing. Never drop the fallback to make budget.
- 3 tracks + 5 SFX in both codecs ≈ 6.3 MB, inside the 8 MB `dist` total (both codecs count); initial load counts one codec only (browser fetches one URL from the `[ogg, m4a]` array).
- Lazy-load split as in §1: only `music.overworld` is in Preload.

## 5. Volume Normalization Convention

- Normalize **in-file** first, trim per-asset in the manifest second; **no volume math in code** outside the manifest field.
- Music: loudness-normalize to **−16 LUFS integrated**, true peak ≤ −1.0 dBTL. SFX: peak-normalize to −3 dBFS.
- Manifest `volume` (0.0–1.0) is the per-asset mix trim: defaults **music 0.8, SFX 1.0**; `sfx.menu` 0.6. Tune by ear at M3 lock; values live only in `audio-manifest.json`.

## 6. Manifest Shape (PLAN §4/§6)

`audio-manifest.json`, one entry per asset:

```json
{
  "music.overworld": { "id": "music.overworld", "ogg": "audio/overworld.ogg", "m4a": "audio/overworld.m4a", "volume": 0.8 },
  "sfx.menu":        { "id": "sfx.menu",        "ogg": "audio/menu.ogg",      "m4a": "audio/menu.m4a",      "volume": 0.6 }
}
```

- `loopStart`/`loopEnd`: optional schema fields, reserved (asset-lint asserts `0 ≤ loopStart < loopEnd ≤ duration` when present).
- Referential integrity is bidirectional (PLAN §6): every manifest ID resolves to files; every audio ID referenced from other data files resolves in the manifest.

## 7. Sourcing & Fallback

- AI chiptune drafts → Audio Agent trims/normalizes per §3/§5. Audio is **never on the critical path** (PLAN §11): the named worst-case fallback is CC0 chiptune (OpenGameArt / Kenney CC0), recorded in `assets/CREDITS.md`.
- §0 applies: no source-game music, covers, or soundalike renditions of its tracks.
