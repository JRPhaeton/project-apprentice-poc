#!/usr/bin/env python3
"""Deterministic audio generator — Assets lane (M4, AUDIO_BIBLE locked).

Composes the POC's 3 chiptune music loops and 5 SFX entirely in code
(numpy synthesis from note tables — no randomness beyond fixed-seed noise
sources, so re-running reproduces the WAV masters bit-for-bit), then
encodes every asset to BOTH codecs at the exact paths in
src/data/audio-manifest.json:

  music.overworld  audio/overworld.ogg|.m4a  ~45.7 s  84 BPM, A minor,
      hopeful-yet-sad: i-VI-III-VII verse with a V-major lift, square lead
      + triangle bass + soft noise ticks, A/B sections.
  music.battle     audio/battle.ogg|.m4a     ~34.3 s  140 BPM, driving
      bass arpeggio, urgent riffing lead, A/B + turnaround.
  music.boss       audio/boss.ogg|.m4a       ~32.7 s  147 BPM, C minor,
      low-register ostinato, dissonant cluster stabs, denser percussion.
  sfx.attack/hit/magic/victory/menu           <= 1.5 s one-shots.

Loop convention (AUDIO_BIBLE §3): every music track is a self-contained
full-file seamless loop — exact bar-length sample count, echo tails wrapped
circularly back to the loop start (np.roll), both ends faded to true zero
over ~1.5 ms so first/last samples sit on a zero crossing.

Loudness (AUDIO_BIBLE §5): music is loudness-normalized in-file to
-16 LUFS integrated (single ffmpeg loudnorm analysis pass -> linear gain,
true peak capped at -1 dBFS); SFX are peak-normalized to -3 dBFS.
Per-asset mix trims stay in the manifest's `volume` field only.

Encoding (AUDIO_BIBLE §4): OGG Vorbis q3.5 primary + AAC 128k fallback.

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


def osc_pulse(freq, n, duty=0.25, vib=0.0):
    t = np.arange(n) / SR
    if vib:
        f = freq * (1.0 + vib * np.sin(2 * np.pi * 5.5 * t))
        ph = np.cumsum(f) / SR
    else:
        ph = freq * t
    return np.where((ph % 1.0) < duty, 1.0, -1.0)


def osc_tri(freq, n):
    ph = (freq * np.arange(n) / SR) % 1.0
    return 2.0 * np.abs(2.0 * ph - 1.0) - 1.0


def osc_sine(freq, n):
    return np.sin(2 * np.pi * freq * np.arange(n) / SR)


def noise(n, seed):
    return np.random.RandomState(seed).uniform(-1.0, 1.0, n)


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


class Mix:
    """Stereo mix bus with circular (loop-safe) note placement."""

    def __init__(self, n):
        self.n = n
        self.L = np.zeros(n)
        self.R = np.zeros(n)

    def add(self, start, sig, gain=1.0, pan=0.0):
        gl = gain * min(1.0, 1.0 - pan)
        gr = gain * min(1.0, 1.0 + pan)
        start %= self.n
        end = start + len(sig)
        if end <= self.n:
            self.L[start:end] += sig * gl
            self.R[start:end] += sig * gr
        else:  # wrap the tail to the loop start
            k = self.n - start
            self.L[start:] += sig[:k] * gl
            self.R[start:] += sig[:k] * gr
            self.L[:end - self.n] += sig[k:] * gl
            self.R[:end - self.n] += sig[k:] * gr

    def echo(self, delay_l, delay_r, gain):
        self.L += gain * np.roll(self.L, delay_l)  # np.roll = circular: seam-safe
        self.R += gain * np.roll(self.R, delay_r)

    def master(self):
        x = np.stack([self.L, self.R])
        peak = np.max(np.abs(x))
        if peak > 0:
            x = x * (0.9 / peak)
        # fade both ends to a true zero crossing
        ramp = np.linspace(0.0, 1.0, FADE)
        x[:, :FADE] *= ramp
        x[:, -FADE:] *= ramp[::-1]
        return x


def play(mix, notes, spb, wave_fn="pulse", duty=0.25, gain=0.12, pan=0.0,
         vib=0.0, gate=0.88, a=0.004, d=0.04, s=0.7, r=0.05, octave=0):
    for beat, dur, m in notes:
        if m is None:
            continue
        start = int(round(beat * spb * SR))
        n = int(round(dur * spb * SR))
        f = midi_hz(m + octave * 12)
        if wave_fn == "pulse":
            sig = osc_pulse(f, n, duty=duty, vib=vib)
        elif wave_fn == "tri":
            sig = osc_tri(f, n)
        else:
            sig = osc_sine(f, n)
        mix.add(start, sig * envelope(n, a=a, d=d, s=s, r=r, gate=gate), gain=gain, pan=pan)


# --- tiny drum kit --------------------------------------------------------


def drum_kick(spb):
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = 110.0 * np.exp(-18.0 * t) + 42.0
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return sig * np.exp(-22.0 * t)


def drum_snare(seed):
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    sig = 0.7 * noise(n, seed) + 0.4 * np.sin(2 * np.pi * 185.0 * t)
    return sig * np.exp(-28.0 * t)


def drum_hat(seed, dur=0.05):
    n = int(dur * SR)
    hp = np.diff(noise(n + 1, seed))  # crude highpass: first difference
    return hp * np.exp(-60.0 * np.arange(n) / SR)


def chord_tones(root, quality):
    third = root + (3 if quality == "m" else 4)
    return root, third, root + 7


# ---------------------------------------------------------------------------
# music.overworld — 84 BPM, 16 bars of 4/4 in A minor (~45.71 s).
# "Hopeful yet sad": Am F C G verse, F G Am / E-major lift back to the loop.


def build_overworld():
    bpm, bars = 84, 16
    spb = 60.0 / bpm
    n = int(round(bars * 4 * spb * SR))
    mix = Mix(n)
    chords = [
        (45, "m"), (41, "M"), (48, "M"), (43, "M"),
        (45, "m"), (41, "M"), (48, "M"), (40, "M"),
        (41, "M"), (43, "M"), (45, "m"), (45, "m"),
        (41, "M"), (43, "M"), (40, "M"), (40, "M"),
    ]
    bass, harm = [], []
    for bar, (root, q) in enumerate(chords):
        b0 = bar * 4
        r, t3, t5 = chord_tones(root, q)
        bass += [(b0, 1, r), (b0 + 1, 1, t5), (b0 + 2, 1, r + 12), (b0 + 3, 1, t5)]
        arp = [r + 24, t3 + 24, t5 + 24, t3 + 24]
        harm += [(b0 + k * 0.5, 0.5, arp[k % 4]) for k in range(8)]
    play(mix, bass, spb, wave_fn="tri", gain=0.30, gate=0.92, s=0.85, pan=0.0)
    play(mix, harm, spb, duty=0.5, gain=0.055, gate=0.75, s=0.6, pan=0.35)
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
    play(mix, lead, spb, duty=0.25, gain=0.15, vib=0.004, gate=0.92, s=0.75, pan=-0.15)
    # soft noise ticks: one per beat, a touch louder on the downbeat
    for beat in range(bars * 4):
        g = 0.05 if beat % 4 == 0 else 0.028
        mix.add(int(round(beat * spb * SR)), drum_hat(900 + beat), gain=g, pan=0.1)
    mix.echo(int(0.75 * spb * SR), int(0.5 * spb * SR), 0.16)
    return mix.master()


# ---------------------------------------------------------------------------
# music.battle — 140 BPM, 20 bars (~34.29 s): driving bass arpeggio,
# urgent lead, A/B sections + 4-bar chromatic turnaround into the loop.


def build_battle():
    bpm, bars = 140, 20
    spb = 60.0 / bpm
    n = int(round(bars * 4 * spb * SR))
    mix = Mix(n)
    chords = [
        (45, "m"), (45, "m"), (43, "M"), (43, "M"),
        (41, "M"), (41, "M"), (40, "M"), (40, "M"),
        (38, "m"), (38, "m"), (45, "m"), (45, "m"),
        (46, "M"), (46, "M"), (40, "M"), (40, "M"),
        (45, "m"), (43, "M"), (41, "M"), (40, "M"),
    ]
    bass = []
    for bar, (root, q) in enumerate(chords):
        b0 = bar * 4
        r, _t3, t5 = chord_tones(root, q)
        patt = [r, r, r + 12, r, t5, r, r + 12, r]
        bass += [(b0 + k * 0.5, 0.5, patt[k]) for k in range(8)]
    play(mix, bass, spb, wave_fn="tri", gain=0.30, gate=0.8, s=0.9, a=0.002)
    play(mix, bass, spb, duty=0.5, gain=0.05, gate=0.7, s=0.8, a=0.002, pan=0.25)
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
    play(mix, lead, spb, duty=0.25, gain=0.13, vib=0.003, gate=0.85, s=0.8,
         a=0.002, pan=-0.15)
    for bar in range(bars):
        b0 = bar * 4
        for beat in (0, 2):
            mix.add(int(round((b0 + beat) * spb * SR)), drum_kick(spb), gain=0.5)
        for beat in (1, 3):
            mix.add(int(round((b0 + beat) * spb * SR)), drum_snare(1300 + bar * 7 + beat), gain=0.22)
        for k in range(8):
            g = 0.045 if k % 2 == 0 else 0.028
            mix.add(int(round((b0 + k * 0.5) * spb * SR)), drum_hat(1700 + bar * 11 + k), gain=g, pan=0.2)
    mix.echo(int(0.25 * spb * SR), int(0.375 * spb * SR), 0.12)
    return mix.master()


# ---------------------------------------------------------------------------
# music.boss — 147 BPM, 20 bars (~32.65 s): C minor, low ostinato,
# dissonant cluster stabs, four-on-the-floor percussion.


def build_boss():
    bpm, bars = 147, 20
    spb = 60.0 / bpm
    n = int(round(bars * 4 * spb * SR))
    mix = Mix(n)
    chords = [
        (36, "m"), (36, "m"), (36, "m"), (36, "m"),
        (44, "M"), (44, "M"), (43, "M"), (43, "M"),
        (36, "m"), (36, "m"), (41, "m"), (41, "m"),
        (44, "M"), (44, "M"), (43, "M"), (43, "M"),
        (36, "m"), (37, "M"), (36, "m"), (43, "M"),
    ]
    bass = []
    for bar, (root, q) in enumerate(chords):
        b0 = bar * 4
        r = root
        patt = [r, r, r + 12, r, r + 3, r, r + 12, r]
        bass += [(b0 + k * 0.5, 0.5, patt[k]) for k in range(8)]
    play(mix, bass, spb, wave_fn="tri", gain=0.34, gate=0.82, s=0.9, a=0.002)
    play(mix, bass, spb, duty=0.5, gain=0.045, gate=0.7, s=0.8, a=0.002, pan=-0.2)
    # dissonant stabs: minor-2nd-over-tritone cluster on the offbeats
    stabs = []
    for bar, (root, _q) in enumerate(chords):
        if bar % 2 == 0:
            b0 = bar * 4
            for beat in (1.5, 3.5):
                for iv in (24, 30, 31):
                    stabs.append((b0 + beat, 0.25, root + iv))
    play(mix, stabs, spb, duty=0.5, gain=0.07, gate=0.9, s=1.0, a=0.001, d=0.01, pan=0.15)
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
        (48, 1, 80), (49, 1, 78)  , (50, 1, 75), (51, 1, 72),
        (52, 2, 74), (54, 2, 71),
        (56, 1, 74), (57, 1, 71), (58, 1, 67), (59, 1, 62),
        (60, 2, 67), (62, 2, 71),
        # coda: chromatic shudder (Cm -> Db -> Cm -> G) back into the loop
        (64, 1, 72), (65, 1, 75), (66, 1, 72), (67, 1, 75),
        (68, 1, 73), (69, 1, 76), (70, 1, 73), (71, 1, 76),
        (72, 1, 72), (73, 1, 75), (74, 1, 72), (75, 1, 75),
        (76, 1, 74), (77, 1, 71), (78, 1, 67), (79, 1, 62),
    ]
    play(mix, lead, spb, duty=0.3, gain=0.12, vib=0.004, gate=0.88, s=0.8, pan=-0.1)
    for bar in range(bars):
        b0 = bar * 4
        for beat in range(4):
            mix.add(int(round((b0 + beat) * spb * SR)), drum_kick(spb), gain=0.55)
        for beat in (1, 3):
            mix.add(int(round((b0 + beat) * spb * SR)), drum_snare(2100 + bar * 5 + beat), gain=0.26)
        for k in range(16):
            g = 0.032 if k % 4 == 0 else 0.02
            mix.add(int(round((b0 + k * 0.25) * spb * SR)), drum_hat(2900 + bar * 17 + k, 0.03), gain=g, pan=0.25)
    # rising noise swell through the final bar, cresting at the loop point
    swn = int(round(4 * spb * SR))
    sw = noise(swn, 4242) * np.linspace(0.0, 1.0, swn) ** 2
    mix.add(n - swn, onepole_lowpass(sw, 400, 4000), gain=0.10)
    mix.echo(int(0.25 * spb * SR), int(0.33 * spb * SR), 0.11)
    return mix.master()


# ---------------------------------------------------------------------------
# SFX — mono one-shots, peak-normalized to -3 dBFS at write time.


def sfx_attack():
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    sw = onepole_lowpass(noise(n, 11), 5200, 380)  # falling whoosh
    env = np.sin(np.pi * np.clip(t / 0.30, 0, 1)) ** 1.5
    return sw * env


def sfx_hit():
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    crunch = onepole_lowpass(noise(n, 23), 2600, 300) * np.exp(-26 * t)
    f = 105.0 * np.exp(-16.0 * t) + 48.0
    thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-18 * t)
    return 0.8 * crunch + 0.7 * thump


def sfx_magic():
    dur = 0.85
    n = int(dur * SR)
    out = np.zeros(n)
    steps = [84, 88, 91, 96, 100, 103, 108]  # C6 arpeggio sprinting upward
    step_n = int(0.055 * SR)
    for i, m in enumerate(steps):
        s = osc_pulse(midi_hz(m), step_n, duty=0.5)
        s *= envelope(step_n, a=0.002, d=0.01, s=0.8, r=0.01, gate=0.95)
        out[i * step_n:(i + 1) * step_n] += s
    # shimmer: high tone with vibrato decaying over the tail
    tail0 = len(steps) * step_n
    tn = n - tail0
    sh = osc_pulse(midi_hz(108), tn, duty=0.5, vib=0.012)
    out[tail0:] += sh * np.exp(-6.0 * np.arange(tn) / SR) * 0.8
    out += 0.25 * np.roll(out, int(0.09 * SR))  # sparkle echo
    return out * np.linspace(1.0, 0.0, n) ** 0.25


def sfx_victory():
    dur = 1.45
    n = int(dur * SR)
    out = np.zeros(n)
    line = [(0.0, 0.12, 67), (0.12, 0.12, 72), (0.24, 0.12, 76), (0.36, 0.30, 79)]
    for start, d, m in line:
        sn = int(d * SR)
        s0 = int(start * SR)
        s = osc_pulse(midi_hz(m), sn, duty=0.25)
        out[s0:s0 + sn] += s * envelope(sn, a=0.003, d=0.02, s=0.85, r=0.02, gate=0.95)
    c0 = int(0.68 * SR)
    cn = n - c0
    for m in (72, 76, 79, 84):  # closing C-major chord, slight detune sparkle
        s = osc_pulse(midi_hz(m) * 1.001, cn, duty=0.5, vib=0.004)
        out[c0:] += 0.4 * s * envelope(cn, a=0.004, d=0.1, s=0.7, r=0.25, gate=0.98)
    return out


def sfx_menu():
    n = int(0.09 * SR)
    half = n // 2
    out = np.concatenate([
        osc_pulse(1560.0, half, duty=0.5),
        osc_pulse(2080.0, n - half, duty=0.5),
    ])
    return out * envelope(n, a=0.001, d=0.01, s=0.8, r=0.02, gate=0.9)


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
    run(["ffmpeg", "-hide_banner", "-y", "-i", wav_path,
         "-c:a", "libvorbis", "-q:a", "3.5", ogg_path])
    run(["ffmpeg", "-hide_banner", "-y", "-i", wav_path,
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


def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    music = {
        "overworld": build_overworld,
        "battle": build_battle,
        "boss": build_boss,
    }
    sfx = {
        "sfx-attack": sfx_attack,
        "sfx-hit": sfx_hit,
        "sfx-magic": sfx_magic,
        "sfx-victory": sfx_victory,
        "sfx-menu": sfx_menu,
    }
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for name, builder in music.items():
            x = builder()
            x, lufs, gain = normalize_music(x)
            seam_ok_x = x  # normalized master used for seam check (linear gain)
            print(f"  {name}: composed {x.shape[1] / SR:.2f} s, source loudness "
                  f"{lufs:.1f} LUFS -> -16 LUFS (gain x{gain:.3f})")
            seam_report(name, seam_ok_x)
            wav = os.path.join(td, name + ".wav")
            write_wav(wav, x)
            encode(wav, os.path.join(AUDIO_DIR, name + ".ogg"),
                   os.path.join(AUDIO_DIR, name + ".m4a"))
            rows.append((name, True))
        for name, builder in sfx.items():
            x = builder()
            peak = np.max(np.abs(x))
            x = x * (10.0 ** (-3.0 / 20.0) / peak)  # peak-normalize to -3 dBFS
            x = x[None, :]  # mono
            wav = os.path.join(td, name + ".wav")
            write_wav(wav, x)
            encode(wav, os.path.join(AUDIO_DIR, name + ".ogg"),
                   os.path.join(AUDIO_DIR, name + ".m4a"))
            rows.append((name, False))

    # --- verification against the manifest + budgets ---
    with open(AUDIO_MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
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
