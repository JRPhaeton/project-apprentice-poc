#!/usr/bin/env python3
"""Deterministic audio generator — Assets lane (M6, synth engine v2).

SPC700-era "SNES feel" synthesis. Every melodic voice is 2-3 detuned
oscillator layers (pulse/saw/tri blends -> subtle chorus), shaped by a
per-instrument lowpass, mixed on buses that carry a send into a feedback
echo/delay line (120-180 ms, high-cut inside the feedback path — the SNES
signature ambience). Under it: a filtered-noise drum kit (pitched-sine
kick + click, bandpassed-noise snare, metallic hats, brushes) and a
dedicated bass voice (pulse+triangle hybrid with an amp envelope).

Composes the POC's 3 music loops + 1 intro sting + 5 SFX entirely in code
(numpy from note tables; all noise from fixed seeds, so re-running
reproduces the WAV masters bit-for-bit), then encodes every asset to BOTH
codecs at the exact paths in src/data/audio-manifest.json:

  music.overworld  audio/overworld.ogg|.m4a  ~45.7 s  84 BPM, A minor,
      hopeful-yet-sad: warm add9 pad under the original lead, soft arp,
      pulse+tri bass, brushed percussion, gentle echo.
  music.battle     audio/battle.ogg|.m4a     ~34.3 s  140 BPM, driving:
      full drum pattern, bass ostinato, urgent detuned lead with echo
      throws on the phrase ends, offbeat sus/9th comp stabs.
  music.boss       audio/boss.ogg|.m4a       ~32.7 s  147 BPM, C minor,
      low-register 5th drone + ostinato, dissonant cluster stabs kept,
      bigger four-on-the-floor kit, darker echo.
  music.sting      audio/sting.ogg|.m4a      ~10.6 s  NON-looping intro
      sting: low drone swell, sparse inharmonic bells (tritone hang),
      ember-crackle noise texture, unresolved ending.
  sfx.attack/hit/magic/victory/menu           <= 1.5 s one-shots.

Loop convention (AUDIO_BIBLE §3): every music loop is a self-contained
full-file seamless loop — exact bar-length sample count, echo/filter tails
wrapped circularly back to the loop start (frequency-domain circular
processing == the np.roll convention, taken to its exact limit), both ends
faded to true zero over ~1.5 ms so first/last samples sit on a zero
crossing. The sting is the one deliberate NON-loop (one-shot intro cue).

Loudness (AUDIO_BIBLE §5): music is loudness-normalized in-file to
-16 LUFS integrated (single ffmpeg loudnorm analysis pass -> linear gain,
true peak capped at -1 dBFS); SFX are peak-normalized to -3 dBFS.
Per-asset mix trims stay in the manifest's `volume` field only.

Encoding (AUDIO_BIBLE §4): OGG Vorbis q3.5 primary + AAC 128k fallback.
Every encoded music loop is decoded back and re-checked (sample-exact
length for OGG, silent ends at the seam).

Run from anywhere:  python3 tools/gen_audio.py
Exit code is non-zero if any self-check fails.
"""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import wave

import numpy as np

SR = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "public")
AUDIO_DIR = os.path.join(PUB, "assets", "audio")
AUDIO_MANIFEST = os.path.join(ROOT, "src", "data", "audio-manifest.json")

FADE = 64  # samples (~1.5 ms) faded at both ends of music masters


# ---------------------------------------------------------------------------
# Synthesis primitives


def midi_hz(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def noise(n, seed):
    return np.random.RandomState(seed).uniform(-1.0, 1.0, n)


def voice(f0, n, layers, vib=0.0, vib_rate=5.3):
    """One note of a layered voice: `layers` is a list of
    (wave, duty, detune_cents, level) oscillator units summed together.
    Slight detune between units gives the SPC700-style chorus shimmer;
    vibrato (delayed-onset, shared modulation) sits on top of all units."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    if vib:
        vib_env = np.clip(t / 0.30, 0.0, 1.0)  # vibrato fades in, SNES-style
        mod = 1.0 + vib * vib_env * np.sin(2 * np.pi * vib_rate * t)
    for i, (wav, duty, cents, lvl) in enumerate(layers):
        f = f0 * 2.0 ** (cents / 1200.0)
        ph0 = (0.19 + 0.37 * i) % 1.0  # fixed per-unit phase offsets
        if vib:
            ph = ph0 + np.cumsum(f * mod) / SR
        else:
            ph = ph0 + f * t
        p = ph % 1.0
        if wav == "pulse":
            w = np.where(p < duty, 1.0, -1.0)
        elif wav == "saw":
            w = 2.0 * p - 1.0
        elif wav == "tri":
            w = 2.0 * np.abs(2.0 * p - 1.0) - 1.0
        else:  # sine
            w = np.sin(2 * np.pi * ph)
        out += lvl * w
    return out


def envelope(n, a=0.004, d=0.04, s=0.7, r=0.04, gate=0.9):
    """ADSR over n samples; release completes at gate*n so note tails end
    inside their slot (keeps bar boundaries near-silent for clean loops)."""
    gn = max(8, int(n * gate))
    an, dn, rn = (max(1, int(x * SR)) for x in (a, d, r))
    an, dn, rn = min(an, gn // 3), min(dn, gn // 3), min(rn, gn // 3)
    env = np.zeros(n)
    env[:an] = np.linspace(0.0, 1.0, an, endpoint=False)
    env[an:an + dn] = np.linspace(1.0, s, dn, endpoint=False)
    env[an + dn:gn - rn] = s
    env[gn - rn:gn] = np.linspace(s, 0.0, rn, endpoint=False)
    return env


def onepole_lowpass(x, fc_start, fc_end):
    """One-pole lowpass with a linearly swept cutoff (SFX whoosh/crunch)."""
    n = len(x)
    fc = np.linspace(fc_start, fc_end, n)
    a = 1.0 - np.exp(-2.0 * np.pi * fc / SR)
    y = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def lp1(x, fc):
    """Constant-cutoff one-pole lowpass (short signals: drums, SFX)."""
    return onepole_lowpass(x, fc, fc)


def hp1(x, fc):
    return x - lp1(x, fc)


def loop_filter(x, lp=None, hp=None, order=1):
    """Per-instrument tone shaping applied CIRCULARLY in the frequency
    domain: the exact periodic steady state of a one-pole (order=1) or
    cascaded (order=2) low/high shelf-slope filter. Circular processing is
    what makes filter tails loop-seam-safe on full-track buses."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    if lp is not None:
        X *= (1.0 / (1.0 + 1j * f / lp)) ** order
    if hp is not None:
        X *= ((1j * f / hp) / (1.0 + 1j * f / hp)) ** order
    return np.fft.irfft(X, n)


def echo_channel(x, delay_samples, fb, hc):
    """SNES-style echo: feedback delay with a one-pole high-cut INSIDE the
    feedback path, solved exactly in the frequency domain —
    H = G·z^-d / (1 - fb·G·z^-d). Circular by construction, so the echo
    tail of the last bar folds back under the loop start (the np.roll
    pattern, extended to infinite taps)."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    G = 1.0 / (1.0 + 1j * f / hc)
    D = np.exp(-2j * np.pi * f * delay_samples / SR)
    X *= (G * D) / (1.0 - fb * G * D)
    return np.fft.irfft(X, n)


def place(buf, start, sig):
    """Circular (loop-safe) placement of a mono signal into a bus."""
    n = len(buf)
    start %= n
    end = start + len(sig)
    if end <= n:
        buf[start:end] += sig
    else:
        k = n - start
        buf[start:] += sig[:k]
        buf[:end - n] += sig[k:]


def render_notes(n_total, notes, spb, layers, octave=0, vib=0.0, gate=0.88,
                 a=0.004, d=0.04, s=0.7, r=0.05):
    """Render a note table into a fresh mono bus. Notes are
    (beat, dur_beats, midi | (midi, ...) | None [, velocity])."""
    buf = np.zeros(n_total)
    for note in notes:
        beat, dur, m = note[0], note[1], note[2]
        if m is None:
            continue
        vel = note[3] if len(note) > 3 else 1.0
        start = int(round(beat * spb * SR))
        n = int(round(dur * spb * SR))
        env = envelope(n, a=a, d=d, s=s, r=r, gate=gate)
        midis = m if isinstance(m, (tuple, list)) else (m,)
        sig = np.zeros(n)
        for mm in midis:
            sig += voice(midi_hz(mm + octave * 12), n, layers, vib=vib)
        place(buf, start, sig * env * vel)
    return buf


class Chip:
    """Stereo master with per-instrument submix buses and an echo send.

    Instruments render into mono buses (render_notes / drum placement),
    then `submix` applies the per-instrument lowpass/highpass shaping,
    panning, dry gain, and an independent echo-send amount. `master` runs
    the echo bus through the feedback delay and folds it under the dry mix.
    All processing is circular, so every tail wraps to the loop start."""

    def __init__(self, n):
        self.n = n
        self.dryL = np.zeros(n)
        self.dryR = np.zeros(n)
        self.sendL = np.zeros(n)
        self.sendR = np.zeros(n)

    def submix(self, mono, gain=1.0, pan=0.0, send=0.0, lp=None, hp=None,
               order=1):
        y = loop_filter(mono, lp=lp, hp=hp, order=order) if (lp or hp) else mono
        gl = min(1.0, 1.0 - pan)
        gr = min(1.0, 1.0 + pan)
        self.dryL += y * (gain * gl)
        self.dryR += y * (gain * gr)
        if send > 0.0:
            self.sendL += y * (send * gl)
            self.sendR += y * (send * gr)

    def master(self, echo_delay_s=0.16, fb=0.45, hc=2500, wet=0.35,
               spread=1.031):
        dl = int(round(echo_delay_s * SR))
        dr = int(round(echo_delay_s * spread * SR))
        eL = echo_channel(self.sendL, dl, fb, hc)
        eR = echo_channel(self.sendR, dr, fb, hc)
        # small cross-bleed keeps the widened echo coherent in mono
        L = self.dryL + wet * (0.85 * eL + 0.15 * eR)
        R = self.dryR + wet * (0.85 * eR + 0.15 * eL)
        x = np.stack([L, R])
        peak = np.max(np.abs(x))
        if peak > 0:
            x = x * (0.9 / peak)
        # fade both ends to a true zero crossing
        ramp = np.linspace(0.0, 1.0, FADE)
        x[:, :FADE] *= ramp
        x[:, -FADE:] *= ramp[::-1]
        return x


# --- filtered-noise drum kit ----------------------------------------------


def drum_kick(dur=0.18, f0=150.0, f1=44.0, click=0.5, seed=101):
    """Pitched sine thump with an attached noise click transient."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = (f0 - f1) * np.exp(-30.0 * t) + f1
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-16.0 * t)
    cn = int(0.004 * SR)
    ck = lp1(noise(cn, seed), 4500) * np.exp(-np.arange(cn) / (0.0012 * SR))
    body[:cn] += click * ck
    return body


def drum_snare(seed, dur=0.16, tone=185.0, bright=5200.0):
    """Bandpassed noise burst over a short two-partial tone body."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    band = hp1(lp1(noise(n, seed), bright), 850)
    body = (0.55 * np.sin(2 * np.pi * tone * t) * np.exp(-30.0 * t)
            + 0.28 * np.sin(2 * np.pi * tone * 1.62 * t) * np.exp(-42.0 * t))
    return band * np.exp(-24.0 * t) * 1.1 + body


def drum_hat(seed, dur=0.045, metal=1.0):
    """Short highpassed noise + a stack of detuned squares (metallic ring)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    hp_noise = np.diff(noise(n + 1, seed))
    m = np.zeros(n)
    for k, f in enumerate((3113.0, 4660.0, 5835.0, 7143.0, 8117.0, 9343.0)):
        m += np.where(((f * t + k * 0.13) % 1.0) < 0.5, 1.0, -1.0)
    m = hp1(m / 6.0, 6500)
    sig = 0.55 * hp_noise + metal * 0.5 * m
    return sig * np.exp(-t / (dur * 0.30))


def drum_brush(seed, dur=0.13):
    """Soft band-limited noise swish — brushed percussion (overworld)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    band = hp1(lp1(noise(n, seed), 6200), 1400)
    return band * np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.3


def chord_tones(root, quality):
    third = root + (3 if quality == "m" else 4)
    return root, third, root + 7


# --- shared voice patches (oscillator layer stacks) ------------------------

LEAD_LAYERS = [("pulse", 0.25, -5.0, 0.42), ("pulse", 0.25, +5.0, 0.42),
               ("saw", 0.0, 0.0, 0.26)]
PAD_LAYERS = [("saw", 0.0, -6.0, 0.34), ("saw", 0.0, +6.0, 0.34),
              ("pulse", 0.5, 0.0, 0.26)]
BASS_LAYERS = [("pulse", 0.5, 0.0, 0.45), ("tri", 0.0, 0.2, 0.62)]
ARP_LAYERS = [("pulse", 0.125, -4.0, 0.5), ("pulse", 0.125, +4.0, 0.5)]
STAB_LAYERS = [("pulse", 0.5, -7.0, 0.5), ("pulse", 0.5, +7.0, 0.5)]


# ---------------------------------------------------------------------------
# music.overworld — 84 BPM, 16 bars of 4/4 in A minor (~45.71 s).
# "Hopeful yet sad": Am F C G verse, F G Am / E-major lift back to the loop.
# v2: warm add9 pad under the original lead, arp pushed back, pulse+tri
# bass, brushed percussion, 179 ms echo.


def build_overworld():
    bpm, bars = 84, 16
    spb = 60.0 / bpm
    n = int(round(bars * 4 * spb * SR))
    chip = Chip(n)
    chords = [
        (45, "m"), (41, "M"), (48, "M"), (43, "M"),
        (45, "m"), (41, "M"), (48, "M"), (40, "M"),
        (41, "M"), (43, "M"), (45, "m"), (45, "m"),
        (41, "M"), (43, "M"), (40, "M"), (40, "M"),
    ]
    bass, harm, pad = [], [], []
    for bar, (root, q) in enumerate(chords):
        b0 = bar * 4
        r, t3, t5 = chord_tones(root, q)
        bass += [(b0, 1, r), (b0 + 1, 1, t5), (b0 + 2, 1, r + 12), (b0 + 3, 1, t5)]
        arp = [r + 24, t3 + 24, t5 + 24, t3 + 24]
        harm += [(b0 + k * 0.5, 0.5, arp[k % 4]) for k in range(8)]
        # warm add9 voicing: root, third, fifth, ninth (no doubled 3rd on top)
        pad.append((b0, 4, (r + 12, t3 + 12, r + 19, r + 26),
                    0.95 if bar < 8 else 1.06))
    chip.submix(render_notes(n, bass, spb, BASS_LAYERS, gate=0.92, s=0.85,
                             d=0.06),
                gain=0.26, pan=0.0, send=0.02, lp=760)
    chip.submix(render_notes(n, pad, spb, PAD_LAYERS, a=0.30, d=0.5, s=0.85,
                             r=0.6, gate=0.97),
                gain=0.058, pan=0.0, send=0.05, lp=1500)
    chip.submix(render_notes(n, harm, spb, ARP_LAYERS, gate=0.75, s=0.6),
                gain=0.030, pan=0.35, send=0.04, lp=4200)
    lead = [
        # A section: sad verse, phrases sighing downward
        (0, 1.5, 76), (1.5, 0.5, 74), (2, 1, 72), (3, 1, 71),
        (4, 1.5, 72), (5.5, 0.5, 71), (6, 2, 69),
        (8, 1.5, 67), (9.5, 0.5, 69), (10, 1, 71), (11, 1, 72),
        (12, 2, 74), (14, 2, 71),
        (16, 1.5, 76), (17.5, 0.5, 74), (18, 1, 72), (19, 1, 71),
        (20, 1.5, 69), (21.5, 0.5, 71), (22, 2, 72),
        (24, 1, 76), (25, 1, 77), (26, 2, 76),
        (28, 1.5, 74), (29.5, 0.5, 72), (30, 2, 71),
        # B section: rising, hopeful cadence
        (32, 1, 69), (33, 1, 72), (34, 2, 77),
        (36, 1, 79), (37, 1, 77), (38, 2, 76),
        (40, 1.5, 76), (41.5, 0.5, 72), (42, 1, 71), (43, 1, 72),
        (44, 3, 69),
        (48, 1, 72), (49, 1, 74), (50, 2, 76),
        (52, 1, 77), (53, 1, 76), (54, 2, 74),
        # E-major lift: G# leading tone resolves to A at the loop point
        (56, 2, 76), (58, 1, 71), (59, 1, 68), (60, 3, 69),
    ]
    # section dynamics: quieter verse, the B section lifts
    lead = [(b, d, m, 0.92 if b < 32 else 1.06) for (b, d, m) in lead]
    chip.submix(render_notes(n, lead, spb, LEAD_LAYERS, vib=0.005, gate=0.92,
                             s=0.75, d=0.06),
                gain=0.13, pan=-0.12, send=0.07, lp=4600)
    # brushed percussion: swish 8ths, soft kick on the downbeat, brush-snare
    # answer on beat 2. The kit sits out the first bars after the loop point
    # (a breath after the cadence), then builds back in.
    kick_bus, brush_bus = np.zeros(n), np.zeros(n)
    for bar in range(bars):
        b0 = bar * 4
        if bar >= 2:
            place(kick_bus, int(round(b0 * spb * SR)),
                  drum_kick(dur=0.16, f0=120, f1=46, click=0.15, seed=90 + bar))
        place(brush_bus, int(round((b0 + 2) * spb * SR)),
              0.55 * drum_brush(700 + bar * 3, dur=0.16))
        if bar < 2:  # breath bar: downbeat swish only
            place(brush_bus, int(round(b0 * spb * SR)),
                  0.9 * drum_brush(900 + bar * 8))
            continue
        for k in range(8):
            if bar < 4 and k % 2 == 1:
                continue  # quarters only while building back in
            g = 0.9 if k % 4 == 0 else 0.5
            place(brush_bus, int(round((b0 + k * 0.5) * spb * SR)),
                  g * drum_brush(900 + bar * 8 + k))
    chip.submix(kick_bus, gain=0.24, pan=0.0, send=0.01)
    chip.submix(brush_bus, gain=0.13, pan=0.12, send=0.02)
    return chip.master(echo_delay_s=0.25 * spb, fb=0.42, hc=2900, wet=0.34)


# ---------------------------------------------------------------------------
# music.battle — 140 BPM, 20 bars (~34.29 s): driving bass ostinato,
# urgent lead, A/B sections + 4-bar chromatic turnaround into the loop.
# v2: full kit, detuned lead with echo throws, offbeat 9th comp stabs.


def build_battle():
    bpm, bars = 140, 20
    spb = 60.0 / bpm
    n = int(round(bars * 4 * spb * SR))
    chip = Chip(n)
    chords = [
        (45, "m"), (45, "m"), (43, "M"), (43, "M"),
        (41, "M"), (41, "M"), (40, "M"), (40, "M"),
        (38, "m"), (38, "m"), (45, "m"), (45, "m"),
        (46, "M"), (46, "M"), (40, "M"), (40, "M"),
        (45, "m"), (43, "M"), (41, "M"), (40, "M"),
    ]
    bass, stabs = [], []
    for bar, (root, q) in enumerate(chords):
        b0 = bar * 4
        r, t3, t5 = chord_tones(root, q)
        patt = [r, r, r + 12, r, t5, r, r + 12, r]
        bass += [(b0 + k * 0.5, 0.5, patt[k]) for k in range(8)]
        # comp stabs: sus2/9th color on the offbeats, sparser in the B half
        voicing = (r + 19, t3 + 24, r + 26)
        beats = (1.5, 3.5) if bar < 12 else (3.5,)
        stabs += [(b0 + bt, 0.25, voicing) for bt in beats]
    chip.submix(render_notes(n, bass, spb, BASS_LAYERS, gate=0.78, s=0.9,
                             a=0.002, d=0.03),
                gain=0.25, pan=0.0, send=0.02, lp=900)
    chip.submix(render_notes(n, stabs, spb, STAB_LAYERS, gate=0.9, s=1.0,
                             a=0.001, d=0.01),
                gain=0.048, pan=0.30, send=0.05, lp=3800)
    lead = [
        # A: circling riff, tightening over G, F, then E with a chromatic climb
        (0, 0.5, 81), (0.5, 0.5, 79), (1, 0.5, 81), (1.5, 0.5, 76),
        (2, 0.5, 81), (2.5, 0.5, 79), (3, 0.5, 76), (3.5, 0.5, 79),
        (4, 0.5, 81), (4.5, 0.5, 84), (5, 0.5, 81), (5.5, 0.5, 79),
        (6, 1, 76), (7, 1, 79),
        (8, 0.5, 79), (8.5, 0.5, 74), (9, 0.5, 79), (9.5, 0.5, 74),
        (10, 0.5, 79), (10.5, 0.5, 81), (11, 0.5, 79), (11.5, 0.5, 74),
        (12, 0.5, 83), (12.5, 0.5, 79), (13, 0.5, 74), (13.5, 0.5, 79),
        (14, 1, 71), (15, 1, 74),
        (16, 0.5, 77), (16.5, 0.5, 72), (17, 0.5, 77), (17.5, 0.5, 72),
        (18, 0.5, 77), (18.5, 0.5, 79), (19, 0.5, 77), (19.5, 0.5, 72),
        (20, 0.5, 81), (20.5, 0.5, 77), (21, 0.5, 72), (21.5, 0.5, 77),
        (22, 1, 69), (23, 1, 72),
        (24, 0.5, 76), (24.5, 0.5, 71), (25, 0.5, 76), (25.5, 0.5, 68),
        (26, 0.5, 76), (26.5, 0.5, 71), (27, 0.5, 68), (27.5, 0.5, 71),
        (28, 0.5, 64), (28.5, 0.5, 68), (29, 0.5, 71), (29.5, 0.5, 76),
        (30, 0.5, 79), (30.5, 0.5, 80), (31, 1, 81),
        # B: broader melody over Dm / Am / Bb / E
        (32, 1, 74), (33, 0.5, 77), (33.5, 0.5, 74), (34, 1, 81), (35, 1, 77),
        (36, 1.5, 74), (37.5, 0.5, 72), (38, 2, 69),
        (40, 1, 72), (41, 0.5, 76), (41.5, 0.5, 72), (42, 1, 84), (43, 1, 81),
        (44, 1.5, 76), (45.5, 0.5, 74), (46, 2, 72),
        (48, 1, 77), (49, 0.5, 82), (49.5, 0.5, 77), (50, 1, 86), (51, 1, 82),
        (52, 2, 79), (54, 2, 77),
        (56, 0.5, 76), (56.5, 0.5, 80), (57, 0.5, 83), (57.5, 0.5, 80),
        (58, 0.5, 76), (58.5, 0.5, 80), (59, 0.5, 83), (59.5, 0.5, 80),
        (60, 1, 83), (61, 1, 80), (62, 2, 76),
        # turnaround: falling riffs, then a chromatic sprint back to A5
        (64, 1.5, 81), (65.5, 0.5, 79), (66, 1, 76), (67, 1, 74),
        (68, 1.5, 79), (69.5, 0.5, 74), (70, 1, 71), (71, 1, 74),
        (72, 1.5, 77), (73.5, 0.5, 76), (74, 1, 72), (75, 1, 69),
        (76, 0.5, 64), (76.5, 0.5, 68), (77, 0.5, 71), (77.5, 0.5, 76),
        (78, 0.5, 68), (78.5, 0.5, 71), (79, 0.5, 76), (79.5, 0.5, 80),
    ]
    # crescendo through the turnaround into the loop restart
    lead = [(b, d, m, 1.0 if b < 64 else 1.0 + (b - 64) * 0.009)
            for (b, d, m) in lead]
    chip.submix(render_notes(n, lead, spb, LEAD_LAYERS, vib=0.003, gate=0.85,
                             s=0.8, a=0.002),
                gain=0.12, pan=-0.12, send=0.05, lp=5200)
    # echo throws: phrase-end notes fed to the echo bus only (no extra dry),
    # louder into the delay than the lead itself so the repeats ring out
    throws = [nt for nt in lead if nt[1] >= 1.0]
    chip.submix(render_notes(n, throws, spb, LEAD_LAYERS, vib=0.003,
                             gate=0.85, s=0.8, a=0.002),
                gain=0.0, pan=0.15, send=0.16, lp=5200)
    # full kit: kick 1 & 2-and-a-half, backbeat snare, accented 8th hats,
    # kick pickup each 4th bar, snare-roll fill through the final bar
    kick_bus, snare_bus, hat_bus = np.zeros(n), np.zeros(n), np.zeros(n)
    for bar in range(bars):
        b0 = bar * 4
        kicks = [0.0, 2.5] + ([3.75] if bar % 4 == 3 else [])
        for bt in kicks:
            place(kick_bus, int(round((b0 + bt) * spb * SR)),
                  drum_kick(dur=0.17, f0=150, f1=46, click=0.55, seed=40 + bar))
        for bt in (1.0, 3.0):
            place(snare_bus, int(round((b0 + bt) * spb * SR)),
                  drum_snare(1300 + bar * 7 + int(bt)))
        if bar == bars - 1:  # turnaround fill
            for k in range(4):
                place(snare_bus, int(round((b0 + 2 + k * 0.5) * spb * SR)),
                      (0.5 + 0.14 * k) * drum_snare(1900 + k, dur=0.10))
        for k in range(8):
            g = 1.0 if k % 2 == 0 else 0.55
            dur = 0.075 if k == 7 else 0.045  # open-ish hat on the last 8th
            place(hat_bus, int(round((b0 + k * 0.5) * spb * SR)),
                  g * drum_hat(1700 + bar * 11 + k, dur=dur))
    chip.submix(kick_bus, gain=0.38, pan=0.0, send=0.01)
    chip.submix(snare_bus, gain=0.22, pan=0.04, send=0.04)
    chip.submix(hat_bus, gain=0.07, pan=0.22, send=0.01)
    return chip.master(echo_delay_s=0.375 * spb, fb=0.40, hc=2800, wet=0.30)


# ---------------------------------------------------------------------------
# music.boss — 147 BPM, 20 bars (~32.65 s): C minor, low ostinato,
# dissonant cluster stabs, four-on-the-floor percussion.
# v2: low 5th drone underneath, detuned stabs kept, bigger kit, darker echo.


def build_boss():
    bpm, bars = 147, 20
    spb = 60.0 / bpm
    n = int(round(bars * 4 * spb * SR))
    chip = Chip(n)
    chords = [
        (36, "m"), (36, "m"), (36, "m"), (36, "m"),
        (44, "M"), (44, "M"), (43, "M"), (43, "M"),
        (36, "m"), (36, "m"), (41, "m"), (41, "m"),
        (44, "M"), (44, "M"), (43, "M"), (43, "M"),
        (36, "m"), (37, "M"), (36, "m"), (43, "M"),
    ]
    bass, drone = [], []
    for bar, (root, _q) in enumerate(chords):
        b0 = bar * 4
        r = root
        patt = [r, r, r + 12, r, r + 3, r, r + 12, r]
        bass += [(b0 + k * 0.5, 0.5, patt[k]) for k in range(8)]
        drone.append((b0, 4, (r, r + 7)))  # low open-5th weight
    chip.submix(render_notes(n, bass, spb, BASS_LAYERS, gate=0.82, s=0.9,
                             a=0.002, d=0.03),
                gain=0.30, pan=0.0, send=0.015, lp=760)
    chip.submix(render_notes(n, drone, spb, PAD_LAYERS, a=0.25, d=0.4,
                             s=0.9, r=0.5, gate=0.97),
                gain=0.065, pan=0.0, send=0.07, lp=520)
    # dissonant stabs: minor-2nd-over-tritone cluster on the offbeats
    stabs = []
    for bar, (root, _q) in enumerate(chords):
        if bar % 2 == 0:
            b0 = bar * 4
            for beat in (1.5, 3.5):
                stabs.append((b0 + beat, 0.25, (root + 24, root + 30, root + 31)))
    chip.submix(render_notes(n, stabs, spb, STAB_LAYERS, gate=0.9, s=1.0,
                             a=0.001, d=0.01),
                gain=0.065, pan=0.15, send=0.12, lp=3600)
    lead = [
        # A: slow menace in the low-mid register
        (0, 3, 60), (3, 1, 63), (4, 3, 62), (7, 1, 58),
        (8, 3, 60), (11, 0.5, 63), (11.5, 0.5, 62), (12, 4, 55),
        (16, 2, 63), (18, 1, 68), (19, 1, 63), (20, 2, 60), (22, 2, 63),
        (24, 2, 62), (26, 1, 59), (27, 1, 55), (28, 2, 62), (30, 2, 65),
        # B: the same dread an octave up, pressing forward
        (32, 1.5, 72), (33.5, 0.5, 75), (34, 1, 74), (35, 1, 70),
        (36, 2, 72), (38, 1, 75), (39, 1, 74),
        (40, 1.5, 77), (41.5, 0.5, 75), (42, 1, 74), (43, 1, 72),
        (44, 2, 75), (46, 2, 72),
        (48, 1, 80), (49, 1, 78), (50, 1, 75), (51, 1, 72),
        (52, 2, 74), (54, 2, 71),
        (56, 1, 74), (57, 1, 71), (58, 1, 67), (59, 1, 62),
        (60, 2, 67), (62, 2, 71),
        # coda: chromatic shudder (Cm -> Db -> Cm -> G) back into the loop
        (64, 1, 72), (65, 1, 75), (66, 1, 72), (67, 1, 75),
        (68, 1, 73), (69, 1, 76), (70, 1, 73), (71, 1, 76),
        (72, 1, 72), (73, 1, 75), (74, 1, 72), (75, 1, 75),
        (76, 1, 74), (77, 1, 71), (78, 1, 67), (79, 1, 62),
    ]
    lead = [(b, d, m, 0.95 if b < 32 else (1.05 if b < 64 else 1.1))
            for (b, d, m) in lead]
    chip.submix(render_notes(n, lead, spb, LEAD_LAYERS, vib=0.004, gate=0.88,
                             s=0.8, d=0.05),
                gain=0.115, pan=-0.10, send=0.10, lp=4200)
    # bigger kit: deep 4-on-the-floor kick, fat layered snare, 16th hats.
    # Arrangement build: half-time snare + no hats for the first 8 bars,
    # full backbeat + 16ths after, double-kick 8ths through the final bar.
    kick_bus, snare_bus, hat_bus = np.zeros(n), np.zeros(n), np.zeros(n)
    for bar in range(bars):
        b0 = bar * 4
        kicks = ([k * 0.5 for k in range(8)] if bar == bars - 1
                 else list(range(4)))
        for beat in kicks:
            place(kick_bus, int(round((b0 + beat) * spb * SR)),
                  drum_kick(dur=0.21, f0=140, f1=40, click=0.5,
                            seed=60 + int(beat * 2)))
        for beat in ((3,) if bar < 8 else (1, 3)):
            s = drum_snare(2100 + bar * 5 + beat, dur=0.18, tone=170,
                           bright=4200)
            place(snare_bus, int(round((b0 + beat) * spb * SR)), s)
        if bar >= 4:
            for k in range(16):
                g = 1.0 if k % 4 == 0 else 0.55
                place(hat_bus, int(round((b0 + k * 0.25) * spb * SR)),
                      g * drum_hat(2900 + bar * 17 + k, dur=0.03))
    chip.submix(kick_bus, gain=0.38, pan=0.0, send=0.01)
    chip.submix(snare_bus, gain=0.24, pan=0.05, send=0.08)
    chip.submix(hat_bus, gain=0.05, pan=0.25, send=0.01)
    # rising noise swell through the final bar, cresting at the loop point
    swn = int(round(4 * spb * SR))
    sw = noise(swn, 4242) * np.linspace(0.0, 1.0, swn) ** 2
    swell_bus = np.zeros(n)
    place(swell_bus, n - swn, onepole_lowpass(sw, 400, 4000))
    chip.submix(swell_bus, gain=0.12, pan=0.0, send=0.03)
    return chip.master(echo_delay_s=0.33 * spb, fb=0.50, hc=1700, wet=0.34)


# ---------------------------------------------------------------------------
# music.sting — ~10.6 s NON-looping dark intro sting for the taunt scene:
# low C 5th drone swell, sparse inharmonic bells hanging on the tritone,
# ember-crackle noise, unresolved end. One-shot: no loop constraints, but
# all content decays inside the file (circular processing wrap ~-70 dB).


def bell(f0, dur, bright=1.0):
    """Inharmonic bell: detuned partials with independent decays."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    partials = [(1.0, 1.0, 2.2), (2.0, 0.55, 3.2), (2.76, 0.4 * bright, 4.4),
                (5.40, 0.22 * bright, 6.5), (8.93, 0.10 * bright, 9.0)]
    for i, (ratio, lvl, dec) in enumerate(partials):
        f = f0 * ratio * (1.0 + 0.0007 * i)
        out += lvl * np.sin(2 * np.pi * f * t + i * 0.7) * np.exp(-dec * t)
    return out * np.exp(-1.1 * t)


def ember_crackle(n, seed, density=26.0):
    """Sparse filtered ticks with a slow flicker — embers in the dark."""
    rs = np.random.RandomState(seed)
    out = np.zeros(n)
    count = int(density * n / SR)
    for _ in range(count):
        pos = int(rs.uniform(0, n - 1))
        dur = int(rs.uniform(0.002, 0.009) * SR)
        amp = rs.uniform(0.2, 1.0) ** 2
        tick = rs.uniform(-1, 1, dur) * np.exp(-np.arange(dur) / (0.002 * SR))
        end = min(n, pos + dur)
        out[pos:end] += amp * tick[:end - pos]
    t = np.arange(n) / SR
    flicker = 0.62 + 0.38 * np.sin(2 * np.pi * 0.31 * t + 1.1)
    return lp1(hp1(out, 900), 3400) * flicker


def build_sting():
    dur_total = 10.6
    n = int(dur_total * SR)
    chip = Chip(n)
    t = np.arange(n) / SR

    # low drone: C2+G2 detuned saws + C1 sine sub, swelling to a hold,
    # released at ~7.6 s so the echo tail hangs and dies unresolved
    swell = np.clip(t / 6.0, 0, 1) ** 1.6
    release = np.clip((t - 7.6) / 1.6, 0, 1)
    denv = swell * (1.0 - release) ** 2
    drone = np.zeros(n)
    for f0, lvl in ((65.41, 1.0), (98.0, 0.55)):
        drone += lvl * voice(f0, n, PAD_LAYERS)
    drone += 0.4 * np.sin(2 * np.pi * 32.70 * t)  # sub kept below the saws
    drone *= denv
    chip.submix(drone, gain=0.16, pan=0.0, send=0.04, lp=640)
    # a minor-9th shadow (Db3) creeping in under the hold
    shadow = voice(138.59, n, [("saw", 0.0, -5.0, 0.5), ("saw", 0.0, 5.0, 0.5)])
    shadow *= np.clip((t - 4.2) / 2.6, 0, 1) ** 2 * (1.0 - release) ** 2
    chip.submix(shadow, gain=0.045, pan=-0.2, send=0.03, lp=900)

    # sparse bells: C5, F#5 (tritone), Ab4, ending hung on Db5 — no resolve
    bell_bus = np.zeros(n)
    for when, f0, g in ((1.9, 523.25, 0.8), (3.8, 739.99, 0.9),
                        (5.5, 415.30, 0.75), (7.2, 554.37, 1.0)):
        b = bell(f0, min(2.8, dur_total - when - 0.15), bright=0.9)
        place(bell_bus, int(when * SR), g * b)
    chip.submix(bell_bus, gain=0.11, pan=0.10, send=0.10, lp=5200)

    # ember crackle floor, panned wide via two independent seeds
    ck_l = ember_crackle(n, 7001)
    ck_r = ember_crackle(n, 7002)
    amb = 1.0 - 0.85 * release
    chip.dryL += 0.07 * ck_l * amb
    chip.dryR += 0.07 * ck_r * amb
    chip.sendL += 0.015 * ck_l * amb
    chip.sendR += 0.015 * ck_r * amb

    x = chip.master(echo_delay_s=0.175, fb=0.55, hc=1400, wet=0.45)
    # one-shot: long fade-out over the final 0.5 s (on top of edge fades)
    fo = int(0.5 * SR)
    x[:, -fo:] *= np.linspace(1.0, 0.0, fo) ** 1.5
    return x


# ---------------------------------------------------------------------------
# SFX — mono one-shots, peak-normalized to -3 dBFS at write time.


def echo_oneshot(x, delay_s, fb, hc, taps=5):
    """Time-domain echo tail for one-shots (non-circular, inside the buffer)."""
    n = len(x)
    d = int(delay_s * SR)
    y = x.copy()
    tap = x
    for k in range(1, taps + 1):
        tap = lp1(tap, hc) * fb
        if k * d >= n:
            break
        y[k * d:] += tap[:n - k * d]
    return y


def sfx_attack():
    """Attack whoosh: swept-noise body + falling pitch sweep + air layer."""
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    env = np.sin(np.pi * np.clip(t / 0.32, 0, 1)) ** 1.4
    whoosh = onepole_lowpass(noise(n, 11), 6500, 260) * env
    f = 620.0 * np.exp(-9.0 * t) + 130.0
    sweep = np.sin(2 * np.pi * np.cumsum(f) / SR) * env ** 1.5
    air = np.diff(noise(n + 1, 12)) * env ** 2
    return whoosh + 0.45 * sweep + 0.28 * air


def sfx_hit():
    """Impact: filtered crunch + pitched thump + sub weight + click."""
    n = int(0.26 * SR)
    t = np.arange(n) / SR
    crunch = onepole_lowpass(noise(n, 23), 2800, 260) * np.exp(-26 * t)
    f = 110.0 * np.exp(-16.0 * t) + 48.0
    thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-18 * t)
    sub = np.sin(2 * np.pi * 56.0 * t) * np.exp(-13 * t)
    cn = int(0.003 * SR)
    click = np.zeros(n)
    click[:cn] = lp1(noise(cn, 24), 5200) * np.exp(-np.arange(cn) / (0.001 * SR))
    return 0.75 * crunch + 0.65 * thump + 0.5 * sub + 0.35 * click


def sfx_magic():
    """Sparkle arpeggio (layered detuned pulses) with a real echo tail."""
    dur = 1.42
    n = int(dur * SR)
    out = np.zeros(n)
    steps = [84, 88, 91, 96, 100, 103, 108]  # C6 arpeggio sprinting upward
    step_n = int(0.055 * SR)
    for i, m in enumerate(steps):
        s = voice(midi_hz(m), step_n, ARP_LAYERS)
        s *= envelope(step_n, a=0.002, d=0.01, s=0.8, r=0.01, gate=0.95)
        out[i * step_n:(i + 1) * step_n] += s
    # shimmer: high detuned tone with vibrato decaying over the tail
    tail0 = len(steps) * step_n
    tn = int(0.45 * SR)
    sh = voice(midi_hz(108), tn, LEAD_LAYERS, vib=0.012)
    out[tail0:tail0 + tn] += sh * np.exp(-6.0 * np.arange(tn) / SR) * 0.8
    out = echo_oneshot(out, 0.13, 0.5, 3200, taps=6)
    fo = int(0.25 * SR)
    out[-fo:] *= np.linspace(1.0, 0.0, fo)
    return out


def sfx_victory():
    """Mini-fanfare: layered line, kit hits, closing add9 chord."""
    dur = 1.45
    n = int(dur * SR)
    out = np.zeros(n)
    line = [(0.0, 0.12, 67), (0.12, 0.12, 72), (0.24, 0.12, 76), (0.36, 0.30, 79)]
    for start, d, m in line:
        sn = int(d * SR)
        s = voice(midi_hz(m), sn, LEAD_LAYERS)
        s *= envelope(sn, a=0.003, d=0.02, s=0.85, r=0.02, gate=0.95)
        out[int(start * SR):int(start * SR) + sn] += s
    # drums: kicks under the pickup, snare+hat splash on the chord landing
    for when, g in ((0.0, 0.9), (0.36, 0.7)):
        k = drum_kick(dur=0.15, f0=140, f1=50, click=0.4, seed=301)
        out[int(when * SR):int(when * SR) + len(k)] += 0.8 * g * k
    for when in (0.12, 0.24, 0.48):
        h = drum_hat(310 + int(when * 100), dur=0.04)
        out[int(when * SR):int(when * SR) + len(h)] += 0.16 * h
    sn_hit = drum_snare(320, dur=0.14)
    out[int(0.68 * SR):int(0.68 * SR) + len(sn_hit)] += 0.5 * sn_hit
    # closing C add9 chord, detuned layers, long release
    c0 = int(0.68 * SR)
    cn = n - c0
    for m in (72, 76, 79, 84, 86):
        s = voice(midi_hz(m), cn, PAD_LAYERS, vib=0.004)
        out[c0:] += 0.30 * s * envelope(cn, a=0.004, d=0.1, s=0.7, r=0.25,
                                        gate=0.98)
    out = echo_oneshot(out, 0.11, 0.35, 3000, taps=4)
    fo = int(0.18 * SR)
    out[-fo:] *= np.linspace(1.0, 0.0, fo)
    return out


def sfx_menu():
    """Cleaner cursor blip: two rounded sine+tri tones, tiny and click-free."""
    n = int(0.075 * SR)
    half = n // 2
    a = voice(1560.0, half, [("sine", 0.0, 0.0, 0.7), ("tri", 0.0, 0.0, 0.3)])
    b = voice(2080.0, n - half, [("sine", 0.0, 0.0, 0.7), ("tri", 0.0, 0.0, 0.3)])
    out = np.concatenate([a, b])
    return out * envelope(n, a=0.002, d=0.012, s=0.75, r=0.02, gate=0.92)


# ---------------------------------------------------------------------------
# WAV + encode + loudness plumbing


def write_wav(path, x):
    """x: float array shape (2, n) or (n,) in [-1, 1]."""
    if x.ndim == 1:
        x = x[None, :]
    pcm = np.clip(x, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    frames = pcm.T.reshape(-1).tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)


def read_wav(path):
    """Decoded PCM back as float array shape (ch, n)."""
    with wave.open(path, "rb") as w:
        ch, n = w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32767.0
    return x.reshape(-1, ch).T


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print("COMMAND FAILED:", " ".join(cmd), file=sys.stderr)
        print(p.stderr[-2000:], file=sys.stderr)
        sys.exit(1)
    return p


def measure_lufs(wav_path):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", wav_path, "-af",
         "loudnorm=I=-16:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not m:
        print("loudnorm analysis failed", file=sys.stderr)
        sys.exit(1)
    return float(json.loads(m.group(0))["input_i"])


def normalize_music(x):
    """Linear-gain loudness normalization to -16 LUFS, TP capped at -1 dBFS.
    (Static gain keeps the loop seam bit-consistent; loudnorm is used in its
    single analysis pass only.)"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    write_wav(tmp, x)
    lufs = measure_lufs(tmp)
    os.unlink(tmp)
    gain = 10.0 ** ((-16.0 - lufs) / 20.0)
    peak = np.max(np.abs(x))
    cap = 10.0 ** (-1.0 / 20.0)  # -1 dBFS
    if peak * gain > cap:
        gain = cap / peak
    return x * gain, lufs, gain


def encode(wav_path, ogg_path, m4a_path):
    # -bitexact: fixed Ogg stream serial + no versioned metadata, so the
    # encoded files (not just the WAV masters) are byte-stable across runs
    bitexact = ["-fflags", "+bitexact", "-flags", "+bitexact"]
    run(["ffmpeg", "-hide_banner", "-y", "-i", wav_path, *bitexact,
         "-c:a", "libvorbis", "-q:a", "3.5", ogg_path])
    run(["ffmpeg", "-hide_banner", "-y", "-i", wav_path, *bitexact,
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", m4a_path])


def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    return float(p.stdout.strip())


def probe_bitrate(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
             "-of", "csv=p=0", path])
    try:
        return int(p.stdout.strip()) // 1000
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Self-checks


def check(cond, msg):
    if not cond:
        print(f"SELF-CHECK FAILED: {msg}", file=sys.stderr)
        sys.exit(1)


def seam_report(name, x):
    """Loop-seam verification: ends at ~zero, amplitude continuous."""
    for ch in range(x.shape[0]):
        first, last = abs(x[ch, 0]), abs(x[ch, -1])
        check(first < 1e-3 and last < 1e-3,
              f"{name}: loop ends not at zero (|first|={first:.5f}, |last|={last:.5f})")
        jump = abs(x[ch, -1] - x[ch, 0])
        check(jump < 2e-3, f"{name}: seam discontinuity {jump:.5f}")
    w = int(0.02 * SR)
    rms_end = float(np.sqrt(np.mean(x[:, -w:] ** 2)))
    rms_start = float(np.sqrt(np.mean(x[:, :w] ** 2)))
    print(f"    loop seam: ends at zero crossing; 20 ms RMS end={rms_end:.4f} "
          f"start={rms_start:.4f} (no click, no gap)")


def spectral_report(x):
    """Band-energy balance of the mastered mix (arrangement sanity print)."""
    mono = x.mean(axis=0)
    spec = np.abs(np.fft.rfft(mono)) ** 2
    f = np.fft.rfftfreq(len(mono), 1.0 / SR)
    bands = [("sub", 20, 120), ("bass", 120, 500), ("mid", 500, 2000),
             ("himid", 2000, 6000), ("air", 6000, 16000)]
    total = spec[(f >= 20) & (f < 16000)].sum()
    parts = []
    for label, lo, hi in bands:
        e = spec[(f >= lo) & (f < hi)].sum()
        parts.append(f"{label} {10 * math.log10(max(e, 1e-30) / total):5.1f}")
    print("    spectral balance (dB rel total): " + "  ".join(parts))


def decode_verify(name, ogg_path, n_master, is_loop):
    """Decode the encoded OGG back to PCM and re-verify length + seam ends
    survived the codec (Vorbis is sample-exact; ends must stay silent)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    run(["ffmpeg", "-hide_banner", "-y", "-i", ogg_path, tmp])
    dec = read_wav(tmp)
    os.unlink(tmp)
    check(abs(dec.shape[1] - n_master) <= 16,
          f"{name}: decoded OGG length {dec.shape[1]} != master {n_master}")
    if is_loop:
        edge = float(max(np.max(np.abs(dec[:, :8])), np.max(np.abs(dec[:, -8:]))))
        # lossy codecs smear ~-30 dBFS of noise into the faded edge samples;
        # that is masked at the seam. A missing fade would read ~0.3+.
        check(edge < 0.06, f"{name}: decoded loop ends not silent ({edge:.4f})")
        print(f"    decode-back: OGG {dec.shape[1]} samples "
              f"(master {n_master}), seam edges |x|<{edge:.4f} — loop intact")
    else:
        print(f"    decode-back: OGG {dec.shape[1]} samples "
              f"(master {n_master}) — one-shot intact")


def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    music = {
        "overworld": (build_overworld, True),
        "battle": (build_battle, True),
        "boss": (build_boss, True),
        "sting": (build_sting, False),
    }
    sfx = {
        "sfx-attack": sfx_attack,
        "sfx-hit": sfx_hit,
        "sfx-magic": sfx_magic,
        "sfx-victory": sfx_victory,
        "sfx-menu": sfx_menu,
    }
    with tempfile.TemporaryDirectory() as td:
        for name, (builder, is_loop) in music.items():
            x = builder()
            x, lufs, gain = normalize_music(x)
            print(f"  {name}: composed {x.shape[1] / SR:.2f} s, source loudness "
                  f"{lufs:.1f} LUFS -> -16 LUFS (gain x{gain:.3f})")
            if is_loop:
                seam_report(name, x)
            else:
                dur = x.shape[1] / SR
                check(8.0 <= dur <= 12.0,
                      f"{name}: one-shot sting {dur:.2f}s outside 8-12s design")
                tail = float(np.max(np.abs(x[:, -8:])))
                check(tail < 1e-3, f"{name}: sting does not end silent ({tail:.5f})")
                print(f"    one-shot: {dur:.2f} s, fades to silence (no loop)")
            spectral_report(x)
            wav = os.path.join(td, name + ".wav")
            write_wav(wav, x)
            ogg = os.path.join(AUDIO_DIR, name + ".ogg")
            encode(wav, ogg, os.path.join(AUDIO_DIR, name + ".m4a"))
            decode_verify(name, ogg, x.shape[1], is_loop)
        for name, builder in sfx.items():
            x = builder()
            peak = np.max(np.abs(x))
            x = x * (10.0 ** (-3.0 / 20.0) / peak)  # peak-normalize to -3 dBFS
            x = x[None, :]  # mono
            wav = os.path.join(td, name + ".wav")
            write_wav(wav, x)
            encode(wav, os.path.join(AUDIO_DIR, name + ".ogg"),
                   os.path.join(AUDIO_DIR, name + ".m4a"))

    # --- verification against the manifest + budgets ---
    with open(AUDIO_MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    check("music.sting" in manifest, "manifest missing the music.sting entry")
    print("\n  asset               codec  dur(s)  kbps   bytes")
    total = 0
    for key, entry in manifest.items():
        is_music = key.startswith("music.")
        for codec in ("ogg", "m4a"):
            p = os.path.join(PUB, entry[codec])
            check(os.path.isfile(p), f"manifest {key}: {entry[codec]} missing under public/")
            dur = probe_duration(p)
            cap = 60.0 if is_music else 3.0
            check(dur <= cap, f"{key} ({codec}): {dur:.2f}s exceeds {cap}s cap")
            if not is_music:
                check(dur <= 1.6, f"{key} ({codec}): {dur:.2f}s exceeds the 1.5s SFX design cap")
            size = os.path.getsize(p)
            total += size
            print(f"  {key:<19} {codec:<5} {dur:7.2f} {probe_bitrate(p):5d} {size:7d}")
    print(f"\n  total audio (both codecs): {total} bytes ({total / 1048576:.2f} MiB)"
          f"  [target <= ~6.3 MiB per PLAN §2]")
    check(total <= int(6.3 * 1048576), "audio exceeds the ~6.3 MiB dual-codec target")

    assets_total = 0
    for dirpath, _dirs, files in os.walk(os.path.join(PUB, "assets")):
        for fn in files:
            assets_total += os.path.getsize(os.path.join(dirpath, fn))
    print(f"  total public/assets/: {assets_total} bytes ({assets_total / 1048576:.2f} MiB)"
          f"  [dist budget 8 MiB incl. code]")
    check(assets_total <= 7 * 1048576, "public/assets leaves too little headroom in the 8 MiB dist budget")
    print("All audio self-checks passed.")


if __name__ == "__main__":
    main()
