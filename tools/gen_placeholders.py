#!/usr/bin/env python3
"""Deterministic FINAL-art generator — Assets lane (M6 presentation pass).

Evolved from the M2 placeholder generator under the same deterministic
contract: no randomness anywhere — dithering is Bayer-matrix arithmetic and
all detail placement is pure arithmetic, so re-running reproduces every file
byte-for-byte. Generates the shipping art set per docs/ART_BIBLE.md (LOCKED
dims; M6 amendment: hero overworld gains a 2-frame walk per facing).

Outputs (all self-authored, CC0 — see assets/CREDITS.md):
  public/assets/tilesets/overworld.png     256x128  tileset v2 (M8): 16x8
      grid of 16px tiles — bases, marching-squares transition sets, tree
      trunk/canopy family, wall top+face pairs, decor, shadow tiles; the
      layout + collide/anim property tables live in tools/tileset_v2.py
  public/assets/sprites/hero-overworld.png  128x48   8 frames 16x24 (M8:
      FF6 proportions; top row only, pad row transparent for the CI grid)
      0,1 down / 2,3 up / 4,5 left / 6,7 right (2-frame walk each)
  public/assets/sprites/overworld-minis.png 128x16   8 frames 16x16 (M8)
      0,1 spider bob / 2,3 wisp flicker / 4,5 revenant sway / 6 blob
      shadow / 7 spare
  public/assets/sprites/spider.png          448x64   7 frames 64x64
  public/assets/sprites/wisp.png            448x64   7 frames 64x64
  public/assets/sprites/revenant.png        448x64   7 frames 64x64
  public/assets/sprites/chimera.png        1440x96  15 frames 96x96
  public/assets/sprites/tile-anim.png        96x16   6 frames 16x16
      0,1 water / 2,3 marsh-water / 4,5 ember-glow shimmer pairs; frames
      0/2/4 are pixel-identical to the tileset-v2 tiles that carry the
      anim property (overlay blending; ids from tools/tileset_v2.py)
  public/assets/sprites/ui-panel.png         48x48  SNES 9-slice window
  public/assets/sprites/ui-touch.png        160x32   5 frames 32x32 (M7)
      0 D-pad base, 1 pressed-arm overlay (UP; engine rotates), 2 'A'
      button, 3 'B' button, 4 pause — ui-panel chrome family
  public/assets/sprites/backdrops/{forest,marsh,ruin,lair}.png  256x144
  public/assets/fonts/font.png              128x48  8x8 bitmap font
  public/assets/fonts/font.fnt              BMFont XML (Phaser-compatible)
  public/assets/icons/icon-192.png          192x192 PWA icon (M7)
  public/assets/icons/icon-512.png          512x512 PWA icon
  public/assets/icons/icon-maskable-512.png 512x512 maskable (safe-zone art)
  public/apple-touch-icon.png               180x180 — at public/ ROOT: 180 is
      not 16-divisible and CI's source-asset-lint grid-checks every PNG
      under public/assets/, so the apple icon must live outside assets/

Palette discipline (ART_BIBLE §2): the tileset draws from one <=32-color
master pool with <=16 colors per 16x16 tile; every sprite sheet, backdrop
and UI texture <=16 colors; shared near-black-blue outline across battle
sprites; the warm ember accent is reserved for the hero, interaction
glints, and the Chimera's/lair's fire.

Run from anywhere:  python3 tools/gen_placeholders.py
Exit code is non-zero if any self-check fails.
"""

import json
import math
import os
import sys
from collections import deque

from PIL import Image, ImageDraw

sys.dont_write_bytecode = True  # keep tools/ free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_backdrops  # noqa: E402  (sibling module, deterministic)
import pixelfont  # noqa: E402
import tileset_v2  # noqa: E402  (M8 tileset + tile-property tables)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "public")
TILESETS = os.path.join(PUB, "assets", "tilesets")
SPRITES = os.path.join(PUB, "assets", "sprites")
BACKDROPS_DIR = os.path.join(SPRITES, "backdrops")
FONTS = os.path.join(PUB, "assets", "fonts")
ICONS_DIR = os.path.join(PUB, "assets", "icons")
ICON_192 = os.path.join(ICONS_DIR, "icon-192.png")
ICON_512 = os.path.join(ICONS_DIR, "icon-512.png")
ICON_MASKABLE = os.path.join(ICONS_DIR, "icon-maskable-512.png")
# 180x180 is NOT 16-divisible; CI's source-asset-lint grid-checks every PNG
# under public/assets/, so the apple icon must live at public/ root instead.
APPLE_ICON = os.path.join(PUB, "apple-touch-icon.png")
ART_MANIFEST = os.path.join(ROOT, "src", "data", "art-manifest.json")

OUTLINE = (20, 22, 40, 255)  # near-black blue: shared outline + tile "void"

BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


# ---------------------------------------------------------------------------
# Helpers


def new_img(w, h, bg=(0, 0, 0, 0)):
    return Image.new("RGBA", (w, h), bg)


def dither(px, x0, y0, x1, y1, color, level, ox=0, oy=0, only=None):
    """Ordered-dither overlay: paint `color` on `level`/16 of the pixels in
    the inclusive rect, by Bayer threshold. `only` restricts painting to
    pixels currently equal to that color (region-safe shading). Coordinates
    outside the image are skipped (never wrapped)."""
    for y in range(max(0, y0), y1 + 1):
        for x in range(max(0, x0), x1 + 1):
            if BAYER4[(y + oy) & 3][(x + ox) & 3] < level:
                try:
                    if only is None or px[x, y] == only:
                        px[x, y] = color
                except IndexError:
                    break  # past the right/bottom edge of this image


def glow_ring(px, w, h, cx, cy, r0, r1, color, level):
    """Dithered ring of glow on transparent pixels only (sprite halos)."""
    for y in range(max(0, cy - r1), min(h, cy + r1 + 1)):
        for x in range(max(0, cx - r1), min(w, cx + r1 + 1)):
            dd = (x - cx) ** 2 + (y - cy) ** 2
            if r0 * r0 <= dd <= r1 * r1 and BAYER4[y & 3][x & 3] < level:
                if px[x, y][3] == 0:
                    px[x, y] = color


def ell3(d, box, dk, mid, lt, s=2):
    """3-tone shaded ellipse with shared outline: dark base, mid body
    shifted up-left, small top-left highlight."""
    x0, y0, x1, y1 = box
    d.ellipse([x0, y0, x1, y1], fill=dk)
    d.ellipse([x0, y0, x1 - s, y1 - s], fill=mid)
    w3 = (x1 - x0) // 3
    h3 = (y1 - y0) // 3
    d.ellipse([x0 + s, y0 + s, x0 + s + w3, y0 + s + h3], fill=lt)
    d.ellipse([x0, y0, x1, y1], outline=OUTLINE)


def leg(d, hip, foot, lift, color, width=2):
    """Two-segment leg: hip -> knee -> foot; knee raised `lift` px."""
    kx = (hip[0] + foot[0]) // 2
    ky = min(hip[1], foot[1]) - lift
    d.line([hip, (kx, ky)], fill=color, width=width)
    d.line([(kx, ky), foot], fill=color, width=width)


def rim_light(t, mapping, dirs=((0, -1), (-1, 0))):
    """SNES rim light: recolor body pixels sitting just inside the shared
    OUTLINE wherever that outline faces transparency on the lit (top/left)
    side. `mapping` limits the pass to body colors -> their rim tones, so
    glows/effects are never touched. Deterministic single pass."""
    px = t.load()
    w, h = t.size

    def clear(x, y):
        return not (0 <= x < w and 0 <= y < h) or px[x, y][3] == 0

    hits = []
    for y in range(h):
        for x in range(w):
            if px[x, y] != OUTLINE:
                continue
            for dx, dy in dirs:
                if clear(x + dx, y + dy):
                    nx, ny = x - dx, y - dy
                    if 0 <= nx < w and 0 <= ny < h and px[nx, ny] in mapping:
                        hits.append((nx, ny, mapping[px[nx, ny]]))
                    break
    for x, y, c in hits:
        px[x, y] = c
    return t


# ---------------------------------------------------------------------------
# 1. Tileset v2 (M8 overworld depth pass) — 256x128, 16 cols x 8 rows of
#    16px tiles: base terrains, marching-squares transition sets, tree
#    trunk/canopy family, wall top+face pairs, decor, shadow-edge tiles.
#    All tile art, the id layout, and the collide/anim tile-property tables
#    live in tools/tileset_v2.py (single source of truth shared with the
#    tools/gen_maps.py map compositor).

gen_tileset = tileset_v2.build_sheet


# ---------------------------------------------------------------------------
# 2. Hero overworld (M8) — 8 frames 16x24 on a 128x48 sheet (bottom 24px row
#    is empty: CI's source-asset-lint requires 16-divisible PNG dims, so the
#    sheet is two frame rows tall and only the top row is used). FF6
#    proportion: head ~10 of 24 px, 3/4 stance, 5-ramp cloak + shared
#    outline + rim light. Frame order unchanged: 0,1 down / 2,3 up /
#    4,5 left / 6,7 right (2-frame walk per facing).

HERO_PAL = {
    "cloak_dk": (44, 50, 70, 255),
    "cloak": (58, 66, 88, 255),
    "cloak_lt": (80, 92, 120, 255),
    "cloak_hi": (112, 128, 158, 255),
    "skin": (232, 200, 160, 255),
    "skin_dk": (196, 158, 120, 255),
    "boot": (70, 50, 34, 255),
    "ember": (232, 144, 48, 255),
    "ember_lt": (248, 200, 88, 255),
}


def hero_frame(facing, step=0):
    t = new_img(16, 24)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = HERO_PAL
    b = 1 if step else 0  # head bob on the off-step
    sw = 1 if step else 0  # cloak-hem sway
    side = facing in ("left", "right")
    lead = -1 if facing == "left" else 1

    # ---- boots (y20-23), alternating stance = the walk read ----
    def boot(x0, y0, w=2):
        d.rectangle([x0, y0, x0 + w - 1, 23], fill=P["boot"])
        d.line([(x0, 23), (x0 + w - 1, 23)], fill=OUTLINE)

    if not side:
        if step == 0:
            boot(4, 21)
            boot(9, 21)
        else:
            boot(4, 20)  # left heel lifted mid-stride
            boot(9, 22)
    else:
        if step == 0:
            boot(5, 21)
            boot(8, 21)
        else:
            boot(7 + lead * 2, 21, 3)  # lead foot reaches
            boot(7 - lead * 2, 20)  # trail heel pushes off

    # ---- cloak body (y10-20): lit left flank, shaded right, ember hem ----
    hem_l = 2 - (sw if not side else max(0, -lead) * sw)
    hem_r = 13 + (sw if not side else max(0, lead) * sw)
    d.polygon([(4, 10), (11, 10), (hem_r, 20), (hem_l, 20)], fill=P["cloak"], outline=OUTLINE)
    d.line([(4, 11), (hem_l + 1, 19)], fill=P["cloak_lt"])
    d.line([(5, 11), (hem_l + 2, 19)], fill=P["cloak_lt"])
    d.line([(10, 11), (hem_r - 1, 19)], fill=P["cloak_dk"])
    d.line([(11, 12), (hem_r - 1, 19)], fill=P["cloak_dk"])
    dither(px, 3, 16, 12, 19, P["cloak_dk"], 4, ox=sw, only=P["cloak"])
    for hx in range(hem_l + 2 + sw, hem_r - 1, 3):  # ember hem trim (sparse)
        px[hx, 20] = P["ember"]
    px[hem_l + 2 + sw, 20] = P["ember_lt"]

    # ---- hood + head (y1-10, ~10px = FF6 big-head proportion) ----
    d.ellipse([3, 1 + b, 12, 10 + b], fill=P["cloak"], outline=OUTLINE)
    d.arc([3, 1 + b, 12, 10 + b], 160, 300, fill=P["cloak_lt"])  # rim sheen
    px[4, 2 + b] = P["cloak_hi"]
    px[5, 1 + b] = P["cloak_hi"]

    if facing == "down":
        d.rectangle([5, 5 + b, 10, 9 + b], fill=P["skin"])
        d.line([(5, 5 + b), (10, 5 + b)], fill=P["cloak_dk"])  # hood brim
        d.line([(5, 9 + b), (10, 9 + b)], fill=P["skin_dk"])  # chin shade
        px[5, 8 + b] = P["skin_dk"]
        px[10, 8 + b] = P["skin_dk"]
        px[6, 7 + b] = OUTLINE  # eyes
        px[9, 7 + b] = OUTLINE
        px[7, 11] = P["ember"]  # clasp
        px[8, 11] = P["ember_lt"]
        d.line([(8 - sw, 13), (8 + sw, 19)], fill=P["cloak_dk"])  # cloak split
        d.line([(5, 14), (6, 14)], fill=P["cloak_dk"])  # belt hint
        d.line([(9, 14), (10, 14)], fill=P["cloak_dk"])
    elif facing == "up":
        d.line([(8, 2 + b), (8, 9 + b)], fill=P["cloak_dk"])  # hood back seam
        d.ellipse([4, 2 + b, 8, 6 + b], fill=P["cloak_lt"])  # crown sheen
        px[5, 3 + b] = P["cloak_hi"]
        d.line([(5, 11), (10, 11)], fill=P["cloak_dk"])  # shoulder crease
        d.line([(10, 12), (11, 16)], fill=P["cloak_dk"])  # pack strap
        if step:
            px[10, 12] = P["cloak_lt"]  # strap catches light mid-stride
    elif facing == "left":
        d.rectangle([4, 5 + b, 8, 9 + b], fill=P["skin"])
        d.line([(4, 5 + b), (8, 5 + b)], fill=P["cloak_dk"])
        d.line([(4, 9 + b), (8, 9 + b)], fill=P["skin_dk"])
        px[8, 8 + b] = P["skin_dk"]  # jaw
        px[5, 7 + b] = OUTLINE  # eye
        d.line([(9, 3 + b), (11, 8 + b)], fill=P["cloak_dk"])  # hood fold
        px[4, 11] = P["ember"]  # clasp at the throat
        d.line([(10, 12), (hem_r - 1, 18)], fill=P["cloak_dk"])  # trailing hem
        d.line([(6, 13), (5, 16)], fill=P["cloak_dk"])  # near arm
    else:  # right
        d.rectangle([7, 5 + b, 11, 9 + b], fill=P["skin"])
        d.line([(7, 5 + b), (11, 5 + b)], fill=P["cloak_dk"])
        d.line([(7, 9 + b), (11, 9 + b)], fill=P["skin_dk"])
        px[7, 8 + b] = P["skin_dk"]
        px[10, 7 + b] = OUTLINE
        d.line([(6, 3 + b), (4, 8 + b)], fill=P["cloak_lt"])
        px[11, 11] = P["ember"]
        d.line([(5, 12), (hem_l + 1, 18)], fill=P["cloak_dk"])
        d.line([(9, 13), (10, 16)], fill=P["cloak_dk"])

    # SNES rim light on the lit (top/left) silhouette
    rim_light(t, {P["cloak"]: P["cloak_lt"], P["cloak_lt"]: P["cloak_hi"]})
    return t


def gen_hero():
    img = new_img(128, 48)
    i = 0
    for facing in ("down", "up", "left", "right"):
        for step in (0, 1):
            img.paste(hero_frame(facing, step), (i * 16, 0))
            i += 1
    return img


# ---------------------------------------------------------------------------
# 2b. Overworld minis (M8) — 128x16, 8 frames 16x16: patrol-creature minis
#     replacing the red-rect markers. 0,1 spider bob · 2,3 wisp flicker ·
#     4,5 revenant sway · 6 soft blob shadow (alpha via palette, drawn by
#     the engine under hero + patrols) · 7 spare (transparent).

MINI_PAL = {
    "moss_dk": (52, 64, 38, 255),
    "moss": (76, 92, 56, 255),
    "moss_lt": (102, 120, 74, 255),
    "eye": (154, 88, 184, 255),
    "teal_dk": (48, 140, 150, 255),
    "teal": (88, 196, 204, 255),
    "teal_lt": (142, 218, 224, 255),
    "white": (246, 252, 255, 255),
    "bone": (210, 200, 172, 255),
    "bone_dk": (166, 156, 130, 255),
    "cloth_dk": (50, 38, 72, 255),
    "cloth": (74, 58, 100, 255),
    "rev_eye": (92, 204, 196, 255),
    "sh_core": (20, 22, 40, 120),
    "sh_edge": (20, 22, 40, 60),
}


def mini_spider(step):
    t = new_img(16, 16)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = MINI_PAL
    b = -1 if step else 0
    s = 1 if step else 0
    # four legs per side: knee up, foot planted (outer pair steps)
    for k, (hx, fx) in enumerate(((4, 1), (5, 3), (10, 12), (11, 14))):
        outer = k in (0, 3)
        fy = 14 - (s if outer else 0)
        ky = 8 + b - (1 if outer else 0)
        fx2 = fx + (s if k >= 2 else -s) * (1 if outer else 0)
        d.line([(hx, 10 + b), (min(15, max(0, (hx + fx2) // 2)), ky)], fill=OUTLINE)
        d.line([(min(15, max(0, (hx + fx2) // 2)), ky), (max(0, min(15, fx2)), fy)], fill=OUTLINE)
    # abdomen + cephalothorax
    d.ellipse([2, 6 + b, 9, 12 + b], fill=P["moss_dk"], outline=OUTLINE)
    d.ellipse([3, 7 + b, 8, 10 + b], fill=P["moss"])
    px[4, 8 + b] = P["moss_lt"]
    px[5, 7 + b] = P["moss_lt"]
    d.ellipse([8, 8 + b, 13, 12 + b], fill=P["moss"], outline=OUTLINE)
    px[10, 9 + b] = P["moss_lt"]
    # bone chevron on the abdomen + violet eyes
    px[5, 10 + b] = P["bone"]
    px[6, 9 + b] = P["bone"]
    px[12, 10 + b] = P["eye"]
    px[11, 10 + b] = P["eye"]
    px[12, 11 + b] = P["moss_dk"]
    return t


def mini_wisp(step):
    t = new_img(16, 16)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = MINI_PAL
    p = 1 if step else 0
    cy = 7 - p
    # trailing wisp dot
    px[3, 12] = P["teal_dk"]
    px[2, 13] = P["teal_dk"] if not step else P["teal"]
    # orb: outline ring, pale rim, teal body, white heart
    d.ellipse([4, cy - 4, 12, cy + 4], fill=OUTLINE)
    d.ellipse([5, cy - 3, 11, cy + 3], fill=P["teal_lt"])
    d.ellipse([6, cy - 2, 10, cy + 2], fill=P["teal"])
    d.rectangle([7, cy - 1, 9, cy], fill=P["white"])  # flame heart
    px[9, cy] = P["teal_lt"]
    px[10, cy + 2] = P["teal_dk"]
    px[6, cy + 2] = P["teal_dk"]
    # flame lick + sparks flicker with the phase
    px[8, cy - 5] = P["teal_lt"] if step else P["teal_dk"]
    px[7 + p * 2, cy - 6] = P["teal_dk"] if step else P["teal_lt"]
    px[12, cy + 5] = P["teal_dk"]
    if step:
        px[3, cy - 3] = P["teal_dk"]
    return t


def mini_revenant(step):
    t = new_img(16, 16)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = MINI_PAL
    lean = 1 if step else 0
    # grave-cloth robe with a ragged hem
    d.polygon(
        [(5 + lean, 6), (10 + lean, 6), (12, 14), (10, 13), (8, 15), (6, 13), (4, 14)],
        fill=P["cloth"],
        outline=OUTLINE,
    )
    d.line([(6 + lean, 7), (5, 12)], fill=P["cloth_dk"])
    d.line([(9 + lean, 7), (10, 12)], fill=P["cloth_dk"])
    # skull
    d.ellipse([5 + lean, 1, 10 + lean, 6], fill=P["bone"], outline=OUTLINE)
    d.line([(6 + lean, 5), (9 + lean, 5)], fill=P["bone_dk"])  # jaw
    px[6 + lean, 3] = P["rev_eye"]
    px[9 + lean, 3] = P["rev_eye"]
    px[6 + lean, 1] = P["white"] if step else P["bone"]  # crown glint
    # bone arm
    d.line([(10 + lean, 8), (12 + lean, 10)], fill=P["bone_dk"])
    return t


def mini_shadow():
    t = new_img(16, 16)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = MINI_PAL
    d.ellipse([3, 10, 12, 14], fill=P["sh_core"])
    # soft dithered fringe
    for y in range(9, 16):
        for x in range(2, 14):
            if px[x, y][3] == 0 and BAYER4[y & 3][x & 3] < 6:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < 16 and 0 <= ny < 16 and px[nx, ny] == P["sh_core"]:
                        px[x, y] = P["sh_edge"]
                        break
    return t


def gen_minis():
    img = new_img(128, 16)
    frames = (
        mini_spider(0), mini_spider(1), mini_wisp(0), mini_wisp(1),
        mini_revenant(0), mini_revenant(1), mini_shadow(),
    )
    for i, f in enumerate(frames):
        img.paste(f, (i * 16, 0))
    return img  # frame 7 intentionally transparent (spare)


# ---------------------------------------------------------------------------
# 3a. Spider — 7 frames 64x64: 0,1 idle · 2,3 step tell · 4,5,6 bite.
#     Forward (toward hero) = +x. Per-frame leg gait for articulation.

SPIDER_PAL = {
    "moss_deep": (34, 44, 28, 255),
    "moss_dk": (52, 64, 38, 255),
    "moss": (76, 92, 56, 255),
    "moss_lt": (102, 120, 74, 255),
    "pale": (128, 146, 96, 255),
    "pale_lt": (152, 170, 118, 255),
    "bone": (198, 190, 162, 255),
    "bone_dk": (150, 142, 116, 255),
    "bone_lt": (226, 220, 198, 255),
    "eye_deep": (104, 52, 136, 255),
    "eye": (154, 88, 184, 255),
    "eye_lt": (200, 140, 220, 255),
    "rim": (172, 196, 170, 255),
    "shadow": (34, 36, 58, 255),
}


def draw_spider(f):
    t = new_img(64, 64)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = SPIDER_PAL
    dx, bob, tilt = f["dx"], f["bob"], f["tilt"]
    fangs, arc = f["fangs"], f["arc"]
    cx = 26 + dx
    cy = 40 + bob
    ground = 57
    # soft ground shadow (dithered edge)
    d.ellipse([cx - 21, ground - 2, cx + 19, ground + 4], fill=P["shadow"])
    dither(px, cx - 21, ground - 2, cx + 19, ground + 4, OUTLINE, 6, only=P["shadow"])
    # lunge speed streaks (behind everything)
    for s in range(arc):
        sy = cy - 6 + s * 6
        d.line([(2, sy), (cx - 23, sy)], fill=P["pale"])
    hips = [(cx - 11, cy + 1), (cx - 5, cy - 1), (cx + 1, cy - 1), (cx + 7, cy + 1)]
    base_feet = [cx - 20, cx - 9, cx + 9, cx + 17]
    # far legs (outline-dark, receding behind the body)
    for k in range(4):
        fdx, fdy = f["feet"][k]
        hx, hy = hips[k]
        fx, fy = base_feet[k] + fdx - 4, ground + min(0, fdy + 2)
        leg(d, (hx - 3, hy + 2), (fx, fy), 7, OUTLINE, 2)
    # abdomen: 5-ramp shaded mass with bone chevrons + spinneret
    ell3(d, [cx - 20, cy - 12, cx - 1, cy + 9], P["moss_dk"], P["moss"], P["moss_lt"])
    dither(px, cx - 20, cy + 1, cx - 1, cy + 9, P["moss_deep"], 6, only=P["moss_dk"])
    dither(px, cx - 20, cy - 2, cx - 1, cy + 6, P["moss_dk"], 5, only=P["moss"])
    dither(px, cx - 18, cy - 11, cx - 5, cy - 3, P["pale"], 6, only=P["moss_lt"])
    dither(px, cx - 16, cy - 10, cx - 8, cy - 5, P["pale_lt"], 5, only=P["pale"])
    d.polygon([(cx - 21, cy - 3), (cx - 17, cy - 6), (cx - 17, cy)], fill=P["moss_dk"])
    # bristle flicks along the abdomen crown
    for i, bxx in enumerate(range(cx - 17, cx - 4, 3)):
        byy = cy - 13 - (i % 2)
        if 0 <= bxx < 64 and 0 <= byy:
            px[bxx, byy] = P["moss_lt"] if i % 2 else P["moss"]
    for i, mx in enumerate((cx - 16, cx - 11)):
        my = cy - 3 + i
        d.line([(mx, my), (mx + 2, my - 3)], fill=P["bone"])
        d.line([(mx + 2, my - 3), (mx + 4, my)], fill=P["bone"])
        px[mx + 2, my - 3] = P["bone_lt"]  # chevron peak catches light
        d.line([(mx + 1, my + 1), (mx + 3, my - 1)], fill=P["bone_dk"])  # underside
    # cephalothorax (tilts up on tell/bite), same 5-ramp treatment
    ell3(d, [cx - 3, cy - 8 - tilt, cx + 12, cy + 7 - tilt], P["moss_dk"], P["moss"], P["moss_lt"])
    dither(px, cx - 3, cy - tilt, cx + 12, cy + 7 - tilt, P["moss_deep"], 5, only=P["moss_dk"])
    dither(px, cx - 2, cy - 7 - tilt, cx + 6, cy - 2 - tilt, P["pale"], 4, only=P["moss_lt"])
    # under-chin core shadow toward the fangs
    dither(px, cx + 4, cy + 2 - tilt, cx + 12, cy + 7 - tilt, P["moss_deep"], 7, only=P["moss_dk"])
    dither(px, cx + 5, cy + 1 - tilt, cx + 11, cy + 5 - tilt, P["moss_dk"], 6, only=P["moss"])
    # near legs (outlined mid-tone, in front) with lit knees + claw tips
    for k in range(4):
        fdx, fdy = f["feet"][k]
        hx, hy = hips[k]
        fx, fy = base_feet[k] + fdx, ground + fdy
        leg(d, (hx, hy), (fx, fy), 10, OUTLINE, 3)
        leg(d, (hx, hy - 1), (fx, fy - 1), 10, P["moss"], 1)
        kx = (hx + fx) // 2
        ky = min(hy, fy) - 10
        if 0 <= kx < 64 and 0 <= ky < 64:
            px[kx, ky] = P["moss_lt"]  # knee highlight
        t.putpixel((max(0, min(63, fx)), max(0, min(63, fy))), OUTLINE)
        if 0 <= fx - 1 < 64 and 0 <= fy - 1 < 64:
            px[fx - 1, fy - 1] = P["bone_dk"]  # claw glint
    # eye cluster (cold violet, 3-tone with a faint under-glow) + pedipalps
    ey = cy - 4 - tilt
    d.rectangle([cx + 8, ey, cx + 9, ey + 1], fill=P["eye"])
    t.putpixel((cx + 8, ey), P["eye_lt"])
    d.rectangle([cx + 5, ey - 1, cx + 6, ey], fill=P["eye"])
    t.putpixel((cx + 6, ey), P["eye_deep"])
    t.putpixel((cx + 5, ey - 1), P["eye_lt"])
    t.putpixel((cx + 11, ey + 1), P["eye"])
    t.putpixel((cx + 10, ey + 2), P["eye_deep"])
    d.line([(cx + 10, cy + 3 - tilt), (cx + 13, cy + 5 - tilt)], fill=P["bone_dk"])
    d.line([(cx + 8, cy + 4 - tilt), (cx + 10, cy + 7 - tilt)], fill=P["bone_dk"])
    # fangs: open (1) then snapped (2), light-to-dark tip ramp
    if fangs:
        spread = 3 if fangs == 1 else 1
        for fx0, fy0 in ((cx + 11, cy + 2 - tilt), (cx + 13, cy - 1 - tilt)):
            d.polygon(
                [(fx0, fy0), (fx0 + 1 + spread, fy0 + 5), (fx0 - 2, fy0 + 2)],
                fill=P["bone"],
            )
            t.putpixel((fx0, fy0), P["bone_dk"])
            t.putpixel((fx0 + 1, fy0 + 2), P["bone_lt"])
    # cold dusk rim light along the lit silhouette
    rim_light(t, {P["moss_lt"]: P["rim"], P["moss"]: P["rim"], P["moss_dk"]: P["moss_lt"], P["pale"]: P["rim"]})
    return t


def gen_spider():
    frames = [
        # dx, bob, tilt, fangs, arc, per-near-leg (foot dx, foot dy)
        dict(dx=0, bob=0, tilt=0, fangs=0, arc=0, feet=[(0, 0), (0, 0), (0, 0), (0, 0)]),
        dict(dx=0, bob=1, tilt=0, fangs=0, arc=0, feet=[(1, -1), (0, 0), (1, 0), (-1, -1)]),
        dict(dx=5, bob=-1, tilt=4, fangs=0, arc=0, feet=[(0, 0), (1, 0), (8, -12), (9, -8)]),
        dict(dx=7, bob=-2, tilt=6, fangs=0, arc=0, feet=[(1, 0), (2, 0), (10, -16), (12, -11)]),
        dict(dx=9, bob=-2, tilt=6, fangs=1, arc=0, feet=[(0, 0), (0, 0), (6, -10), (14, -4)]),
        dict(dx=15, bob=1, tilt=1, fangs=2, arc=3, feet=[(2, 0), (2, 0), (12, -2), (16, -1)]),
        dict(dx=7, bob=0, tilt=0, fangs=0, arc=2, feet=[(0, 0), (1, 0), (4, -2), (6, 0)]),
    ]
    img = new_img(448, 64)
    for i, f in enumerate(frames):
        img.paste(draw_spider(f), (i * 64, 0))
    return img


# ---------------------------------------------------------------------------
# 3b. Wisp — 7 frames: 0,1 idle glow-pulse · 2,3 cast flare · 4,5,6 dash

WISP_PAL = {
    "white": (246, 252, 255, 255),
    "spark": (255, 255, 214, 255),
    "pale": (196, 232, 240, 255),
    "teal_lt": (142, 218, 224, 255),
    "teal": (88, 196, 204, 255),
    "teal_mid": (64, 168, 178, 255),
    "teal_dk": (48, 140, 150, 255),
    "deep": (30, 96, 106, 255),
    "deep2": (20, 64, 76, 255),
    "trail": (24, 66, 76, 255),
    "rim": (224, 246, 250, 255),
}


def draw_wisp(f):
    t = new_img(64, 64)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = WISP_PAL
    dx, dy = f["dx"], f["dy"]
    pulse, halo, streak, trail_n = f["pulse"], f["halo"], f["streak"], f["trail"]
    stretch = f.get("stretch", 0)
    cx = 28 + dx
    cy = 26 + dy
    # trailing wisp chain (shrinks while dashing), each orb its own ramp
    for k in range(trail_n):
        tx = cx - 12 - k * 8 - dx // 2
        ty = cy + 9 + k * 6
        r = 4 - k
        col = P["deep"] if k == 0 else P["trail"]
        d.ellipse([tx - r, ty - r, tx + r, ty + r], fill=col, outline=OUTLINE)
        dither(px, tx - r, ty, tx + r, ty + r, P["deep2"], 6, only=col)
        if r >= 3:
            px[tx - 1, ty - 1] = P["teal_dk"]
            px[tx - 2, ty - 2] = P["teal_mid"] if k == 0 else P["deep"]
    # dash streaks, hot core fading cold
    for s in range(streak):
        sy = cy - 5 + s * 5
        d.line([(cx - 26 - s * 3, sy), (cx - 14, sy)], fill=P["pale"])
        d.line([(cx - 18 - s * 3, sy), (cx - 14, sy)], fill=P["teal_lt"])
        d.line([(cx - 22 - s * 3, sy + 1), (cx - 14, sy + 1)], fill=P["teal_dk"])
    # orb: outline ring, pale rim, layered teal body, deep under-shadow
    rx = 11 + (1 if pulse > 1 else 0) + stretch
    ry = 11 + (1 if pulse > 1 else 0) - stretch // 2
    d.ellipse([cx - rx - 1, cy - ry - 1, cx + rx + 1, cy + ry + 1], fill=OUTLINE)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=P["pale"])
    d.ellipse([cx - rx + 2, cy - ry + 2, cx + rx - 1, cy + ry - 1], fill=P["teal_lt"])
    d.ellipse([cx - rx + 4, cy - ry + 4, cx + rx - 2, cy + ry - 2], fill=P["teal"])
    dither(px, cx - rx + 2, cy - ry + 2, cx + rx - 2, cy, P["teal_lt"], 5, only=P["teal"])
    d.ellipse([cx - 4, cy + ry - 7, cx + rx - 3, cy + ry - 2], fill=P["teal_mid"])
    d.ellipse([cx - 3, cy + ry - 6, cx + rx - 4, cy + ry - 2], fill=P["teal_dk"])
    dither(px, cx - 2, cy + ry - 5, cx + rx - 5, cy + ry - 2, P["deep"], 6, only=P["teal_dk"])
    # upper-left rim shine on the orb glass
    d.arc([cx - rx + 1, cy - ry + 1, cx + rx - 1, cy + ry - 1], 195, 250, fill=P["rim"])
    # flame-teardrop core with a spark heart
    cr = 3 + pulse
    d.ellipse([cx - cr, cy - 1, cx + cr, cy + cr + 2], fill=P["white"])
    d.polygon([(cx - 2, cy + 1), (cx + (1 if dy else -1), cy - 5 - pulse), (cx + 2, cy + 1)], fill=P["white"])
    px[cx - 2, cy + 1] = P["pale"]
    px[cx, cy + 1 + pulse // 2] = P["spark"]
    px[cx - 1, cy + 2] = P["spark"]
    # flame lick escaping the rim
    lx = cx + (2 if dy else -2)
    d.polygon([(lx - 2, cy - ry), (lx, cy - ry - 5 - pulse), (lx + 2, cy - ry)], fill=P["teal_dk"])
    px[lx, cy - ry - 1] = P["teal_mid"]
    # ambient glow halo (dither ring, pulses on idle)
    glow_ring(px, 64, 64, cx, cy, rx + 2, rx + 5 + pulse, P["teal_dk"], 3 + pulse)
    glow_ring(px, 64, 64, cx, cy, rx + 5 + pulse, rx + 8 + pulse, P["deep2"], 2 + pulse)
    # idle life: tiny sparks rising off the flame crown
    if not halo and not streak:
        for k in range(3):
            sx = cx - 4 + k * 4 + pulse
            sy = cy - ry - 6 - (k * 5 + pulse * 3) % 7
            if 0 <= sx < 64 and 0 <= sy < 64 and px[sx, sy][3] == 0:
                px[sx, sy] = P["pale"] if k % 2 else P["teal_lt"]
    # cast rings + sparkles
    if halo:
        hr = rx + 3 + halo * 3
        d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], outline=P["white"])
        if halo > 1:
            hr2 = hr + 5
            d.ellipse([cx - hr2, cy - hr2, cx + hr2, cy + hr2], outline=P["teal_dk"])
        for k in range(4):
            sx = cx + (hr - 1) * (1 if k % 2 else -1)
            sy = cy + (hr - 1) * (1 if k < 2 else -1)
            sx, sy = max(2, min(61, sx)), max(2, min(61, sy))
            px[sx, sy] = P["spark"]
            px[sx - 1, sy] = P["pale"]
            px[sx + 1, sy] = P["pale"]
            px[sx, sy - 1] = P["pale"]
            px[sx, sy + 1] = P["pale"]
    return t


def gen_wisp():
    frames = [
        # dx, dy, pulse, halo, streak, trail, stretch
        dict(dx=0, dy=0, pulse=0, halo=0, streak=0, trail=3),
        dict(dx=0, dy=2, pulse=2, halo=0, streak=0, trail=3),
        dict(dx=0, dy=0, pulse=1, halo=1, streak=0, trail=3),
        dict(dx=0, dy=-1, pulse=2, halo=2, streak=0, trail=3),
        dict(dx=5, dy=0, pulse=1, halo=0, streak=1, trail=2, stretch=2),
        dict(dx=14, dy=1, pulse=1, halo=0, streak=2, trail=1, stretch=4),
        dict(dx=22, dy=0, pulse=2, halo=0, streak=3, trail=0, stretch=2),
    ]
    img = new_img(448, 64)
    for i, f in enumerate(frames):
        img.paste(draw_wisp(f), (i * 64, 0))
    return img


# ---------------------------------------------------------------------------
# 3c. Revenant — 7 frames: 0,1 idle sway · 2,3 reassemble (bone gaps) ·
#     4,5,6 club swing

REV_PAL = {
    "bone": (210, 200, 172, 255),
    "bone_dk": (166, 156, 130, 255),
    "bone_lt": (232, 224, 200, 255),
    "bone_hi": (246, 242, 224, 255),
    "cloth_deep": (36, 26, 54, 255),
    "cloth_dk": (50, 38, 72, 255),
    "cloth": (74, 58, 100, 255),
    "cloth_lt": (102, 84, 132, 255),
    "cloth_hi": (128, 110, 158, 255),
    "rot": (86, 92, 66, 255),
    "eye": (92, 204, 196, 255),
    "eye_dk": (48, 124, 118, 255),
    "rim": (152, 192, 186, 255),
    "shadow": (34, 36, 58, 255),
}


def rev_skull(t, d, x, y, P):
    d.ellipse([x - 5, y, x + 5, y + 9], fill=P["bone"], outline=OUTLINE)
    d.ellipse([x - 4, y + 1, x + 2, y + 5], fill=P["bone_lt"])
    d.ellipse([x - 3, y + 1, x - 1, y + 3], fill=P["bone_hi"])  # crown shine
    px = t.load()
    dither(px, x - 4, y + 6, x + 5, y + 9, P["bone_dk"], 6, only=P["bone"])
    d.line([(x - 4, y + 3), (x + 4, y + 3)], fill=P["bone_dk"])  # brow
    # sockets with cold teal glow
    d.rectangle([x - 3, y + 4, x - 2, y + 5], fill=OUTLINE)
    d.rectangle([x + 2, y + 4, x + 3, y + 5], fill=OUTLINE)
    t.putpixel((x - 3, y + 4), P["eye"])
    t.putpixel((x + 2, y + 4), P["eye"])
    t.putpixel((x - 3, y + 5), P["eye_dk"])
    t.putpixel((x + 2, y + 5), P["eye_dk"])
    t.putpixel((x, y + 7), OUTLINE)  # nasal
    # cheek crack
    d.line([(x + 3, y + 6), (x + 4, y + 8)], fill=P["bone_dk"])
    # jaw + teeth
    d.rectangle([x - 3, y + 9, x + 3, y + 12], fill=P["bone_dk"], outline=OUTLINE)
    for tx in (x - 2, x, x + 2):
        t.putpixel((tx, y + 10), P["bone"])
        t.putpixel((tx, y + 11), P["bone_lt"])


def rev_ribcage(t, d, x, y, P):
    d.ellipse([x - 7, y, x + 7, y + 12], fill=OUTLINE)
    d.line([(x - 7, y), (x + 7, y)], fill=P["bone"])  # clavicle
    t.putpixel((x - 6, y), P["bone_hi"])
    t.putpixel((x - 5, y), P["bone_hi"])
    for k in range(3):
        d.arc([x - 6, y + 1 + k * 3, x + 6, y + 7 + k * 3], 200, 340, fill=P["bone"])
        d.arc([x - 6, y + 2 + k * 3, x + 6, y + 8 + k * 3], 210, 300, fill=P["bone_dk"])
    d.line([(x, y + 1), (x, y + 12)], fill=P["bone_dk"])  # spine
    t.putpixel((x, y + 2), P["bone_lt"])
    t.putpixel((x, y + 6), P["bone_lt"])


def rev_robe(t, d, x, y, P, sway=0):
    px = t.load()
    hem = y + 26
    d.polygon(
        [
            (x - 9, y), (x + 9, y), (x + 11 + sway, hem),
            (x + 7 + sway, hem - 4), (x + 3 + sway, hem + 1),
            (x + sway, hem - 3), (x - 4 + sway, hem + 2),
            (x - 8 + sway, hem - 3), (x - 11 + sway, hem),
        ],
        fill=P["cloth"],
        outline=OUTLINE,
    )
    # 5-ramp cloth: deep folds, dithered hem shadow, lit crest, moss rot
    d.line([(x - 4, y + 2), (x - 6 + sway, hem - 4)], fill=P["cloth_dk"])
    d.line([(x - 3, y + 2), (x - 5 + sway, hem - 4)], fill=P["cloth_deep"])
    d.line([(x + 2, y + 2), (x + 4 + sway, hem - 6)], fill=P["cloth_dk"])
    d.line([(x + 6, y + 4), (x + 8 + sway, hem - 5)], fill=P["cloth_deep"])
    d.line([(x - 8, y + 2), (x - 9 + sway, hem - 5)], fill=P["cloth_lt"])
    d.line([(x - 7, y + 1), (x - 8, y + 8)], fill=P["cloth_hi"])
    dither(px, x - 10 + sway, hem - 8, x + 10 + sway, hem + 1, P["cloth_deep"], 6, only=P["cloth"])
    dither(px, x - 9, y + 1, x + 9, y + 10, P["cloth_lt"], 3, only=P["cloth"])
    # grave-moss stains creeping up the hem
    for k, (mx, my) in enumerate(((x - 6 + sway, hem - 2), (x + 2 + sway, hem - 1), (x + 8 + sway, hem - 3))):
        t.putpixel((mx, my), P["rot"])
        t.putpixel((mx + 1, my - (k % 2)), P["rot"])


def _rev_rim(t):
    P = REV_PAL
    return rim_light(
        t,
        {
            P["cloth"]: P["rim"],
            P["cloth_lt"]: P["rim"],
            P["cloth_hi"]: P["rim"],
            P["cloth_dk"]: P["cloth_lt"],
            P["bone"]: P["bone_hi"],
            P["bone_lt"]: P["bone_hi"],
        },
    )


def draw_revenant(f):
    t = new_img(64, 64)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = REV_PAL
    scatter, lean, arm, arc = f["scatter"], f["lean"], f["arm"], f["arc"]
    cx = 30 + lean
    ground = 58
    s = scatter
    # soft shadow (smaller while the pieces float)
    d.ellipse([cx - 14 + s * 3, ground - 2, cx + 14 - s * 3, ground + 3], fill=P["shadow"])
    dither(px, cx - 14 + s * 3, ground - 2, cx + 14 - s * 3, ground + 3, OUTLINE, 6, only=P["shadow"])
    if s:
        # -- reassembling: pieces apart with visible bone gaps --
        rev_robe(t, d, cx - 2 - s * 4, 30 + s * 3, P)
        rev_ribcage(t, d, cx + 6 + s * 5, 16 - s * 2, P)
        rev_skull(t, d, cx - 8 - s * 6, 2 + s, P)
        # loose bones drifting home
        d.line([(cx - 16 - s * 3, 24), (cx - 12 - s * 3, 30)], fill=P["bone"], width=2)
        d.line([(cx + 16 + s * 4, 30), (cx + 19 + s * 4, 36)], fill=P["bone"], width=2)
        d.line([(cx + 2, 40 + s * 2), (cx + 7, 42 + s * 2)], fill=P["bone_dk"], width=2)
        # gathering grave-light motes
        for k in range(4 + s * 2):
            mx = cx + ((k * 11 + s * 7) % 30) - 15
            my = 8 + ((k * 17 + s * 5) % 34)
            t.putpixel((mx, my), P["eye"] if k % 2 else P["eye_dk"])
        return _rev_rim(t)
    # -- assembled --
    rev_robe(t, d, cx, 28, P, sway=lean // 2)
    # shins under the hem
    d.line([(cx - 4, 54), (cx - 5, ground)], fill=P["bone_dk"], width=2)
    d.line([(cx + 4, 54), (cx + 5, ground)], fill=P["bone_dk"], width=2)
    rev_ribcage(t, d, cx, 15, P)
    rev_skull(t, d, cx - lean // 2, 2, P)
    if arm == 0 and not arc:  # idle: grave-light motes drifting around the skull
        for k in range(4):
            mx = cx - 16 + (k * 11 + (lean & 3) * 5) % 32
            my = 4 + (k * 13 + (lean & 3) * 3) % 22
            if 0 <= mx < 64 and 0 <= my < 64 and px[mx, my][3] == 0:
                px[mx, my] = P["eye"] if k % 2 else P["eye_dk"]
    # far arm hanging
    d.line([(cx - 7, 17), (cx - 11, 25)], fill=P["bone_dk"], width=2)
    d.line([(cx - 11, 25), (cx - 9, 34)], fill=P["bone_dk"], width=2)
    # near arm + femur club by pose
    if arm == 0:
        d.line([(cx + 7, 17), (cx + 11, 25)], fill=P["bone"], width=2)
        d.line([(cx + 11, 25), (cx + 9, 34)], fill=P["bone"], width=2)
        d.line([(cx + 9, 34), (cx + 13, 42)], fill=P["bone_dk"], width=3)
        d.ellipse([cx + 12, 41, cx + 16, 45], fill=P["bone"], outline=OUTLINE)
    elif arm == 1:  # windup overhead
        d.line([(cx + 7, 17), (cx + 12, 10)], fill=P["bone"], width=2)
        d.line([(cx + 12, 10), (cx + 19, 5)], fill=P["bone_dk"], width=3)
        d.ellipse([cx + 18, 2, cx + 23, 7], fill=P["bone"], outline=OUTLINE)
        t.putpixel((cx + 19, 3), P["bone_lt"])
    elif arm == 2:  # swing forward
        d.line([(cx + 7, 18), (cx + 17, 19)], fill=P["bone"], width=2)
        d.line([(cx + 17, 19), (cx + 28, 24)], fill=P["bone_dk"], width=3)
        d.ellipse([cx + 26, 22, cx + 31, 27], fill=P["bone"], outline=OUTLINE)
    else:  # follow-through low
        d.line([(cx + 7, 19), (cx + 15, 30)], fill=P["bone"], width=2)
        d.line([(cx + 15, 30), (cx + 22, 41)], fill=P["bone_dk"], width=3)
        d.ellipse([cx + 20, 40, cx + 25, 45], fill=P["bone"], outline=OUTLINE)
    if arc:  # spectral swing trail
        d.arc([cx + 6, 2, cx + 34, 30], 280, 20, fill=P["eye"])
        d.arc([cx + 4, 4, cx + 30, 34], 290, 10, fill=P["eye_dk"])
    return _rev_rim(t)


def gen_revenant():
    frames = [
        dict(scatter=0, lean=0, arm=0, arc=0),
        dict(scatter=0, lean=-2, arm=0, arc=0),
        dict(scatter=2, lean=0, arm=0, arc=0),
        dict(scatter=1, lean=0, arm=0, arc=0),
        dict(scatter=0, lean=-3, arm=1, arc=0),
        dict(scatter=0, lean=4, arm=2, arc=1),
        dict(scatter=0, lean=2, arm=3, arc=0),
    ]
    img = new_img(448, 64)
    for i, f in enumerate(frames):
        img.paste(draw_revenant(f), (i * 64, 0))
    return img


# ---------------------------------------------------------------------------
# 3d. Chimera — 15 frames 96x96.
#   0,1 cloaked idle (fold shift) · 2,3,4 cloaked attack · 5,6 uncloaked idle ·
#   7,8,9 uncloaked attack · 10,11 breath tell · 12,13,14 flame breath

CHIMERA_PAL = {
    "cloak_dk": (44, 48, 64, 255),
    "cloak": (58, 63, 82, 255),
    "cloak_lt": (78, 84, 106, 255),
    "bone": (200, 192, 168, 255),
    "tawny_dk": (104, 66, 36, 255),
    "tawny": (138, 90, 48, 255),
    "tawny_lt": (168, 120, 72, 255),
    "wing_dk": (64, 48, 70, 255),
    "wing": (90, 68, 96, 255),
    "scale": (74, 122, 114, 255),
    "scale_lt": (110, 160, 148, 255),
    "ember": (240, 160, 48, 255),
    "fl_or": (232, 120, 40, 255),
    "fl_ye": (248, 216, 88, 255),
    "fl_wh": (255, 248, 232, 255),
}


def chimera_claws(d, x, y, dir_, P):
    for k in range(3):
        d.polygon(
            [(x + k * 3 - 1, y), (x + k * 3 + 4, y + dir_ * 4 + k - 1), (x + k * 3, y + 3)],
            fill=P["bone"],
        )


def draw_cloaked(f):
    t = new_img(96, 96)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = CHIMERA_PAL
    sway, limb, arc = f["sway"], f["limb"], f["arc"]
    ax = 46 + sway
    # ground shadow
    d.ellipse([20, 85, 78, 93], fill=OUTLINE)
    # shroud: tall ambiguous mass with a ragged hem
    hem = []
    for k, hx in enumerate(range(22 - sway, 78 + sway, 7)):
        hem.append((hx, 88 - (k % 2) * 3))
    d.polygon(
        [(ax, 10), (ax + 10, 16), (62, 30), (72 + sway, 60), (76 + sway, 88)]
        + hem[::-1]
        + [(20 - sway, 88), (26 + sway // 2, 56), (30, 30), (ax - 8, 16)],
        fill=P["cloak"],
        outline=OUTLINE,
    )
    # shade the right side + hem, light the left
    dither(px, 58, 26, 78, 88, P["cloak_dk"], 5, only=P["cloak"])
    dither(px, 20, 78, 78, 88, P["cloak_dk"], 4, ox=2, only=P["cloak"])
    dither(px, 28, 18, 42, 60, P["cloak_lt"], 2, only=P["cloak"])
    # falling folds — these shift with sway (the cloak "breathes")
    for fx0, top, bot in ((-10, 24, 84), (-2, 18, 87), (8, 26, 84)):
        xx = ax + fx0
        for y in range(top, bot):
            wob = ((y // 6 + sway) % 3) - 1
            if 0 <= xx + wob < 96:
                px[xx + wob, y] = P["cloak_dk"]
        for y in range(top + 4, bot - 6, 2):
            wob = ((y // 6 + sway) % 3) - 1
            if 0 <= xx + wob - 1 < 96:
                px[xx + wob - 1, y] = P["cloak_lt"]
    # hood crown sheen above the cavity
    dither(px, ax - 7, 12, ax + 8, 20, P["cloak_lt"], 3, ox=1, only=P["cloak"])
    # hood cavity with the single ember eye glint
    d.ellipse([ax - 6, 20, ax + 10, 34], fill=P["cloak_dk"])
    d.ellipse([ax - 3, 24, ax + 7, 33], fill=OUTLINE)
    ex = ax + 2
    d.rectangle([ex, 27, ex + (0 if sway else 1), 28], fill=P["ember"])
    if not sway:
        px[ex, 26] = P["fl_ye"]
    # claws peeking under the hem
    for k in range(3):
        hx = 56 + k * 6
        d.polygon([(hx, 89), (hx + 2, 82), (hx + 4, 89)], fill=P["bone"])
        px[hx + 2, 83] = P["fl_wh"]
    # attack limb bursting out
    if limb == 1:
        d.line([(60, 46), (76, 28)], fill=P["cloak_lt"], width=5)
        d.line([(62, 49), (78, 31)], fill=P["cloak_dk"], width=2)
        chimera_claws(d, 74, 26, -1, P)
    elif limb == 2:
        d.line([(60, 50), (86, 50)], fill=P["cloak_lt"], width=5)
        d.line([(60, 53), (84, 53)], fill=P["cloak_dk"], width=2)
        chimera_claws(d, 84, 48, 0, P)
    elif limb == 3:
        d.line([(60, 54), (78, 72)], fill=P["cloak_lt"], width=5)
        d.line([(58, 56), (76, 75)], fill=P["cloak_dk"], width=2)
        chimera_claws(d, 76, 72, 1, P)
    if arc:  # short swipe streaks trailing the claw path
        d.line([(64, 42), (80, 42)], fill=P["bone"])
        d.line([(68, 46), (86, 46)], fill=P["bone"])
    # deep hem shade + faint ember spill from the hood (the swallowed heart)
    dither(px, 22, 82, 76, 88, OUTLINE, 5, ox=1, only=P["cloak_dk"])
    px[ax - 2, 35] = P["fl_or"]
    px[ax + 5, 34] = P["fl_or"]
    # rim light along the shroud's lit silhouette
    rim_light(t, {P["cloak"]: P["cloak_lt"], P["cloak_lt"]: P["bone"], P["cloak_dk"]: P["cloak"]})
    return t


def draw_uncloaked(f):
    """head: 0 normal, 1 pulled back, 2 reared (tell), 3 forward (breath)."""
    t = new_img(96, 96)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = CHIMERA_PAL
    dx, wing_up, head = f["dx"], f["wing"], f["head"]
    glow, cone, arc, foreleg = f["glow"], f["cone"], f["arc"], f["foreleg"]
    bx = 34 + dx
    by = 60
    # ground shadow
    d.ellipse([bx - 30, 86, bx + 32, 94], fill=OUTLINE)
    # tail with a flame tuft (drawn first, behind everything)
    d.line([(bx - 20, by + 2), (bx - 34, by - 10)], fill=P["tawny"], width=3)
    d.line([(bx - 21, by + 3), (bx - 35, by - 9)], fill=P["tawny_dk"], width=1)
    d.polygon(
        [(bx - 33, by - 9), (bx - 40, by - 13), (bx - 36, by - 16), (bx - 38, by - 20), (bx - 32, by - 15)],
        fill=P["ember"],
        outline=OUTLINE,
    )
    px[bx - 36, by - 14] = P["fl_ye"]
    # wings: broad membrane fans with ribs and scalloped trailing edges
    wy = 4 if wing_up else 14
    for side in (0, 1):
        if side == 0:  # far wing, left/back
            root = (bx - 4, by - 12)
            tips = [(bx - 46, wy - 2), (bx - 42, wy + 12), (bx - 32, wy + 22)]
            mid = (bx - 14, by - 20)
        else:  # near wing, right/front (behind the neck)
            root = (bx + 10, by - 14)
            tips = [(bx + 38, wy), (bx + 42, wy + 12), (bx + 36, wy + 22)]
            mid = (bx + 22, by - 22)
        # membrane: fan polygon with scallop dips between finger tips
        pts = [root, tips[0]]
        for k in range(1, 3):
            ax_, ay_ = tips[k - 1]
            bx_, by_ = tips[k]
            pts.append(((ax_ + bx_) // 2 + (2 if side else -2), (ay_ + by_) // 2 + 4))
            pts.append((bx_, by_))
        pts.append(mid)
        d.polygon(pts, fill=P["wing"], outline=OUTLINE)
        # bone fingers radiating from the root
        for tp in tips:
            d.line([root, tp], fill=P["wing_dk"])
        d.line([root, tips[0]], fill=P["bone"])  # leading edge finger catches light
        # membrane shading toward the trailing edge
        lo_x = min(p[0] for p in pts)
        hi_x = max(p[0] for p in pts)
        dither(px, max(0, lo_x), by - 26, min(95, hi_x), by - 12, P["wing_dk"], 5, only=P["wing"])
    # far legs
    for lx in (bx - 16, bx + 10):
        d.rectangle([lx, by + 8, lx + 4, 86], fill=P["tawny_dk"], outline=OUTLINE)
    # leonine body: 3-tone mass (dithered highlight — no hard lump), haunch
    d.ellipse([bx - 26, by - 16, bx + 24, by + 16], fill=P["tawny_dk"])
    d.ellipse([bx - 26, by - 16, bx + 22, by + 14], fill=P["tawny"])
    dither(px, bx - 22, by - 15, bx + 6, by - 2, P["tawny_lt"], 6, only=P["tawny"])
    d.ellipse([bx - 26, by - 16, bx + 24, by + 16], outline=OUTLINE)
    d.ellipse([bx - 23, by - 5, bx - 3, by + 14], fill=P["tawny"])
    d.arc([bx - 23, by - 5, bx - 3, by + 14], 40, 200, fill=P["tawny_dk"])
    d.ellipse([bx - 20, by - 2, bx - 10, by + 7], fill=P["tawny_lt"])
    dither(px, bx - 24, by + 6, bx + 22, by + 15, P["tawny_dk"], 6, only=P["tawny"])
    # near legs with bone claws
    for k, lx in enumerate((bx - 20, bx + 14)):
        up = 8 if (foreleg and k == 1) else 0
        d.rectangle([lx, by + 8 - up, lx + 5, 88 - up], fill=P["tawny"], outline=OUTLINE)
        d.line([(lx + 1, by + 8 - up), (lx + 1, 86 - up)], fill=P["tawny_lt"])
        for c in range(3):
            px[lx + 1 + c * 2, 88 - up] = P["bone"]
    # secondary head: scaled serpent neck + wedge head with open jaw (teal)
    d.line([(bx + 2, by - 12), (bx + 7, by - 24)], fill=P["scale"], width=5)
    dither(px, bx - 1, by - 24, bx + 10, by - 12, P["scale_lt"], 5, only=P["scale"])
    d.ellipse([bx + 1, by - 34, bx + 13, by - 24], fill=P["scale"], outline=OUTLINE)
    d.polygon(
        [(bx + 11, by - 32), (bx + 20, by - 30), (bx + 12, by - 27)],
        fill=P["scale"],
        outline=OUTLINE,
    )  # snout wedge
    d.polygon([(bx + 12, by - 26), (bx + 18, by - 24), (bx + 12, by - 24)], fill=P["scale_lt"])  # jaw
    d.ellipse([bx + 3, by - 32, bx + 8, by - 28], fill=P["scale_lt"])
    px[bx + 9, by - 31] = P["fl_ye"]  # eye
    px[bx + 10, by - 31] = OUTLINE
    # main head position by pose
    if head == 1:
        hx, hy = bx + 20, by - 34
    elif head == 2:
        hx, hy = bx + 16, by - 44
    elif head == 3:
        hx, hy = bx + 34, by - 26
    else:
        hx, hy = bx + 26, by - 28
    # neck joining head to shoulders, lit along its top edge
    d.line([(bx + 14, by - 10), (hx - 2, hy + 8)], fill=P["tawny"], width=7)
    d.line([(bx + 17, by - 6), (hx + 1, hy + 10)], fill=P["tawny_dk"], width=2)
    d.line([(bx + 11, by - 12), (hx - 4, hy + 6)], fill=P["tawny_lt"], width=2)
    # ember mane (it owns fire): spiked ring of flame around the head
    for mk in range(7):
        ang_x = (-14, -16, -13, -6, 2, -12, -4)[mk]
        ang_y = (-6, 2, -13, -16, -15, 10, 13)[mk]
        sx, sy = hx + ang_x, hy + ang_y
        d.polygon(
            [(hx - 2, hy), (sx + 3, sy + 3), (sx - 1, sy - 2)],
            fill=P["ember"],
        )
    d.ellipse([hx - 12, hy - 12, hx + 8, hy + 12], fill=P["ember"], outline=OUTLINE)
    dither(px, hx - 12, hy - 12, hx + 8, hy + 12, P["fl_or"], 5, only=P["ember"])
    # face: broad skull, short muzzle, heavy brow
    d.ellipse([hx - 7, hy - 8, hx + 9, hy + 8], fill=P["tawny"], outline=OUTLINE)
    d.ellipse([hx - 5, hy - 6, hx + 2, hy - 1], fill=P["tawny_lt"])
    d.polygon(
        [(hx + 7, hy - 3), (hx + 13, hy - 1), (hx + 13, hy + 3), (hx + 7, hy + 5)],
        fill=P["tawny_lt"],
        outline=OUTLINE,
    )  # muzzle
    px[hx + 12, hy] = OUTLINE  # nose
    d.line([(hx + 2, hy - 5), (hx + 6, hy - 4)], fill=P["tawny_dk"])  # brow
    d.rectangle([hx + 3, hy - 3, hx + 4, hy - 2], fill=P["fl_ye"])  # eye
    px[hx + 5, hy - 3] = OUTLINE  # slit
    d.polygon([(hx - 4, hy - 10), (hx - 2, hy - 14), (hx, hy - 9)], fill=P["tawny"], outline=OUTLINE)  # ear
    if head in (2, 3):  # jaw dropped open, teeth showing
        d.polygon([(hx + 5, hy + 5), (hx + 15, hy + 8), (hx + 6, hy + 10)], fill=P["tawny_dk"], outline=OUTLINE)
        px[hx + 7, hy + 5] = P["fl_wh"]
        px[hx + 10, hy + 6] = P["fl_wh"]
        px[hx + 13, hy + 7] = P["fl_wh"]
    else:  # closed jaw line
        d.line([(hx + 7, hy + 5), (hx + 12, hy + 4)], fill=OUTLINE)
    # throat glow building through the tell
    if glow:
        gr = 2 + glow * 2
        gx, gy = hx - 3, hy + 11
        d.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=P["fl_or"])
        d.ellipse([gx - gr + 2, gy - gr + 2, gx + gr - 2, gy + gr - 2], fill=P["fl_ye"])
        if glow >= 2:  # embers glow through the chest hide
            dither(px, bx + 10, by - 12, bx + 21, by - 2, P["fl_or"], 3, ox=1, oy=2, only=P["tawny"])
    # flame cone
    if cone:
        mx, my = hx + 14, hy + 4
        exx = 94
        half = 4 + cone * 4
        d.polygon([(mx, my), (exx, my - half), (exx, my + half)], fill=P["fl_or"])
        d.polygon([(mx, my), (exx, my - half + 3), (exx, my + half - 3)], fill=P["fl_ye"])
        if cone >= 2:
            d.polygon([(mx, my), (exx, my - 2), (exx, my + 2)], fill=P["fl_wh"])
        for k in range(cone * 2):  # flicker past the cone edge
            fx = mx + 10 + k * 6
            fy = my - half - 2 + (k % 3) * (half + 2)
            if 0 <= fx < 96 and 0 <= fy < 96:
                d.rectangle([fx, fy, fx + 1, fy + 1], fill=P["fl_ye"])
    # lunge streaks
    if arc:
        for s in range(3):
            sy = by - 18 + s * 8
            d.line([(bx - 46, sy), (bx - 32, sy)], fill=P["bone"])
    # scale glints on the haunch + deep belly shade (richer ramp work)
    dither(px, bx - 24, by + 8, bx + 20, by + 15, OUTLINE, 3, ox=2, only=P["tawny_dk"])
    for k, (gx, gy) in enumerate(((bx - 18, by + 2), (bx - 13, by + 5), (bx - 8, by + 1))):
        px[gx, gy] = P["scale"] if k % 2 else P["scale_lt"]
    # rim light: cool bone catch on the lit silhouette, wings included
    rim_light(
        t,
        {
            P["tawny"]: P["tawny_lt"],
            P["tawny_lt"]: P["bone"],
            P["tawny_dk"]: P["tawny"],
            P["wing"]: P["cloak_lt"],
            P["wing_dk"]: P["wing"],
            P["scale"]: P["scale_lt"],
        },
    )
    return t


def gen_chimera():
    cloaked = [
        dict(sway=0, limb=0, arc=0),
        dict(sway=2, limb=0, arc=0),
        dict(sway=-1, limb=1, arc=0),
        dict(sway=0, limb=2, arc=1),
        dict(sway=1, limb=3, arc=0),
    ]
    uncloaked = [
        dict(dx=0, wing=1, head=0, glow=0, cone=0, arc=0, foreleg=0),
        dict(dx=0, wing=0, head=0, glow=0, cone=0, arc=0, foreleg=0),
        dict(dx=-4, wing=0, head=1, glow=0, cone=0, arc=0, foreleg=1),
        dict(dx=8, wing=1, head=0, glow=0, cone=0, arc=1, foreleg=0),
        dict(dx=3, wing=0, head=0, glow=0, cone=0, arc=0, foreleg=0),
        dict(dx=-6, wing=0, head=2, glow=1, cone=0, arc=0, foreleg=0),
        dict(dx=-6, wing=1, head=2, glow=2, cone=0, arc=0, foreleg=0),
        dict(dx=-8, wing=1, head=3, glow=1, cone=1, arc=0, foreleg=0),
        dict(dx=-8, wing=0, head=3, glow=0, cone=2, arc=0, foreleg=0),
        dict(dx=-8, wing=1, head=3, glow=0, cone=3, arc=0, foreleg=0),
    ]
    img = new_img(1440, 96)
    for i, f in enumerate(cloaked):
        img.paste(draw_cloaked(f), (i * 96, 0))
    for j, f in enumerate(uncloaked):
        img.paste(draw_uncloaked(f), ((5 + j) * 96, 0))
    return img


# ---------------------------------------------------------------------------
# 4. UI panel — 48x48 SNES window, 9-slice safe with 16px corners. All ring
#    colors depend only on (distance-to-edge, nearest edge), so every middle
#    strip is uniform along its stretch axis and slices cleanly.

UI_PAL = {
    "edge": (16, 14, 36, 255),
    "bevel_hi": (208, 208, 240, 255),
    "bevel_lo": (150, 150, 198, 255),
    "grad_top": (124, 106, 208, 255),
    "grad_hi2": (100, 86, 184, 255),
    "grad_mid": (84, 70, 160, 255),
    "grad_lo2": (66, 52, 136, 255),
    "grad_bot": (50, 38, 112, 255),
    "inner": (30, 26, 62, 255),
    "fill": (16, 14, 40, 235),  # dark translucent navy interior (~0.92 alpha)
}


def gen_ui_panel():
    t = new_img(48, 48)
    px = t.load()
    P = UI_PAL
    for y in range(48):
        for x in range(48):
            dt, db, dl, dr = y, 47 - y, x, 47 - x
            dist = min(dt, db, dl, dr)
            if dist <= 1:
                c = P["edge"]  # 2px outer dark edge
            elif dist <= 3:
                c = P["bevel_hi"] if dist == 2 else P["bevel_lo"]  # 2px light bevel
            elif dist <= 6:
                # 3-step vertical gradient frame: bright crown, mid flanks,
                # deep sill — bands meet in 45-degree miters at the corners.
                if dt == dist:
                    c = (P["grad_top"], P["grad_hi2"], P["grad_mid"])[dist - 4]
                elif db == dist:
                    c = (P["grad_bot"], P["grad_lo2"], P["grad_mid"])[dist - 4]
                else:
                    c = P["grad_mid"]
            elif dist == 7:
                c = P["inner"]  # inner shadow line
            else:
                c = P["fill"]
            px[x, y] = c
    return t


# ---------------------------------------------------------------------------
# 4b. Touch controls (M7) — 160x32, five 32x32 frames:
#   0 D-pad base (beveled chrome cross, ui-panel family, center dimple)
#   1 pressed-arm overlay: the UP arm re-lit with bright bevel + ember tint;
#     same cross geometry as frame 0, so the engine rotates this one frame
#     for the other three directions and it lands pixel-exact.
#   2 'A' button (chrome disc, ember accent ring, EmberSpark glyph)
#   3 'B' button (same disc, cooler violet accent)
#   4 pause (small chrome square, '||' glyph)
#   Whole sheet <= 16 colors; faces are solid fills so the controls stay
#   readable at 1x over game art.

TOUCH_EMBER = {
    "dk": (168, 64, 24, 255),
    "mid": (232, 120, 40, 255),
    "lt": (248, 200, 88, 255),
}
TOUCH_FACE = (16, 14, 40, 255)  # opaque navy face (solid at 1x, unlike fill)

CROSS_ARM = (10, 21)  # arm thickness span — centered on 15.5
CROSS_END = (2, 29)   # arm reach span
GRAD_RAMP = ("grad_top", "grad_hi2", "grad_mid", "grad_lo2", "grad_bot")


def _cross_hit(x, y):
    (a0, a1), (e0, e1) = CROSS_ARM, CROSS_END
    return (a0 <= x <= a1 and e0 <= y <= e1) or (a0 <= y <= a1 and e0 <= x <= e1)


def _cross_depth():
    """BFS ring depth inside the cross (0 = the dark outline ring)."""
    d = {}
    q = deque()
    for y in range(32):
        for x in range(32):
            if not _cross_hit(x, y):
                continue
            if any(not _cross_hit(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                d[(x, y)] = 0
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in d and _cross_hit(*n):
                d[n] = d[(x, y)] + 1
                q.append(n)
    return d


def _dpad_arrow(px, facing, color):
    """3-row molded arrow near an arm tip, pointing outward."""
    for row, (a, b) in enumerate(((15, 16), (14, 17), (13, 18))):
        for k in range(a, b + 1):
            if facing == "up":
                px[k, 4 + row] = color
            elif facing == "down":
                px[k, 27 - row] = color
            elif facing == "left":
                px[4 + row, k] = color
            else:
                px[27 - row, k] = color


def touch_dpad_base():
    t = new_img(32, 32)
    px = t.load()
    P = UI_PAL
    for (x, y), d in _cross_depth().items():
        if d == 0:
            c = P["edge"]
        elif d == 1:
            if not _cross_hit(x, y - 2) or not _cross_hit(x - 2, y):
                c = P["bevel_hi"]  # lit top/left flank
            else:
                c = P["bevel_lo"]  # shaded flank + concave elbows
        else:
            c = P[GRAD_RAMP[min(4, (y - 2) * 5 // 28)]]
        px[x, y] = c
    # subtle concave center dimple: dark upper rim, light catch below
    for y in range(12, 20):
        for x in range(12, 20):
            r = math.hypot(x - 15.5, y - 15.5)
            if r <= 3.4:
                if r > 2.3:
                    px[x, y] = P["inner"] if y < 16 else P["bevel_lo"]
                else:
                    px[x, y] = P["grad_lo2"]
    for f in ("up", "down", "left", "right"):
        _dpad_arrow(px, f, P["inner"])
    return t


def touch_dpad_pressed():
    """Overlay frame: only the UP arm, brightened + ember-warm."""
    t = new_img(32, 32)
    px = t.load()
    P = UI_PAL
    E = TOUCH_EMBER
    for (x, y), d in _cross_depth().items():
        if not (CROSS_ARM[0] <= x <= CROSS_ARM[1] and y <= 13):
            continue
        if d == 0:
            c = P["edge"]
        elif d == 1:
            c = P["bevel_hi"]  # bright bevel all the way around
        elif y <= 4:
            c = E["lt"]
        elif y <= 10:
            c = E["mid"]
        else:
            c = E["dk"]  # warm fade toward the cross center
        px[x, y] = c
    _dpad_arrow(px, "up", E["dk"])
    return t


def _stamp_glyph(px, ch, x0, y0, color, shadow):
    """Bold (double-struck) EmberSpark glyph with a 1px drop shadow."""
    rows = pixelfont.G[ch]
    for ox, oy, c in ((1, 1, shadow), (2, 1, shadow), (0, 0, color), (1, 0, color)):
        for gy, row in enumerate(rows):
            for gx, bit in enumerate(row):
                if bit == "X":
                    px[x0 + gx + ox, y0 + gy + oy] = c


def touch_button(accent, glyph):
    """Round chrome button: dark edge, accent ring, bevel, navy face."""
    t = new_img(32, 32)
    px = t.load()
    P = UI_PAL
    a_lt, a_mid, a_dk = accent
    for y in range(32):
        for x in range(32):
            r = math.hypot(x - 15.5, y - 15.5)
            if r > 13.6:
                continue
            if r > 12.3:
                c = P["edge"]
            elif r > 10.8:  # accent ring, lit upper-left
                c = a_lt if x + y < 27 else (a_dk if x + y > 36 else a_mid)
            elif r > 9.6:
                c = P["bevel_hi"] if x + y < 31 else P["bevel_lo"]
            elif r > 8.6:
                c = P["inner"]
            else:
                c = TOUCH_FACE
            px[x, y] = c
    dither(px, 9, 9, 22, 13, P["grad_lo2"], 3, only=TOUCH_FACE)  # face sheen
    px[7, 7] = P["bevel_hi"]  # specular glint on the accent ring
    px[8, 7] = P["bevel_hi"]
    _stamp_glyph(px, glyph, 13, 12, P["bevel_hi"], P["edge"])
    return t


def touch_pause():
    t = new_img(32, 32)
    px = t.load()
    P = UI_PAL
    s0, s1 = 6, 25
    for y in range(s0, s1 + 1):
        for x in range(s0, s1 + 1):
            if x in (s0, s1) and y in (s0, s1):
                continue  # rounded corners
            d = min(x - s0, s1 - x, y - s0, s1 - y)
            if d == 0:
                c = P["edge"]
            elif d == 1:
                c = P["bevel_hi"] if (y == s0 + 1 or x == s0 + 1) else P["bevel_lo"]
            elif d == 2:
                c = P[GRAD_RAMP[min(4, (y - s0 - 2) * 5 // (s1 - s0 - 3))]]
            elif d == 3:
                c = P["inner"]
            else:
                c = TOUCH_FACE
            px[x, y] = c
    for bx in (13, 17):  # '||' glyph: two lit bars with shaded right edges
        for yy in range(12, 20):
            px[bx, yy] = P["bevel_hi"]
            px[bx + 1, yy] = P["bevel_lo"]
    return t


def gen_ui_touch():
    img = new_img(160, 32)
    frames = (
        touch_dpad_base(),
        touch_dpad_pressed(),
        touch_button((TOUCH_EMBER["lt"], TOUCH_EMBER["mid"], TOUCH_EMBER["dk"]), "A"),
        touch_button((UI_PAL["bevel_lo"], UI_PAL["grad_top"], UI_PAL["grad_lo2"]), "B"),
        touch_pause(),
    )
    for i, f in enumerate(frames):
        img.paste(f, (i * 32, 0))
    return img


# ---------------------------------------------------------------------------
# 5. Tile shimmer overlay — 96x16, 6 frames 16x16. Frames 0/2/4 are pixel-
#    identical to tileset-v2's full water / marsh-water / ember tiles (the
#    tiles carrying the anim property); frames 1/3/5 are the alternate
#    shimmer phases. The engine swaps overlay frames on a timer, so each
#    pair must share its base pixels (checked below).

# (tile-anim frame, tileset-v2 tile id) for the pixel-identity self-check
TILE_ANIM_PAIRS = (
    (0, tileset_v2.WATER0),
    (2, tileset_v2.MARSH0),
    (4, tileset_v2.EMBER),
)


def gen_tile_anim():
    img = new_img(96, 16)
    for i, tile in enumerate(
        (
            tileset_v2.t_water_full(0), tileset_v2.t_water_full(1),
            tileset_v2.t_marsh_full(0), tileset_v2.t_marsh_full(1),
            tileset_v2.t_ember_glow(0), tileset_v2.t_ember_glow(1),
        )
    ):
        img.paste(tile, (i * 16, 0))
    return img


# ---------------------------------------------------------------------------
# 6. PWA icons (M7) — the EMBERHEART: a pixel ember/flame heart (warm
#    oranges/golds) over a near-black blue-violet dusk. Key art is drawn once
#    at a 32x32 base and nearest-neighbour upscaled, so every icon reads as
#    intentional chunky pixels, never blur. The maskable icon redraws the art
#    at shrink 0.85 so every art pixel sits inside the W3C safe zone (the
#    centered circle of radius 40% of the icon edge) over a full-bleed
#    background; a self-check below measures that exactly.
#
#    apple-touch-icon.png is 180x180 — NOT divisible by 16 — and CI's
#    source-asset-lint grid-checks every PNG under public/assets/, so the
#    apple icon lives at public/ ROOT, outside assets/ (the 16-divisible
#    192/512 icons live in public/assets/icons/).

ICON_PAL = {
    "bg": (16, 13, 36, 255),        # near-black blue-violet dusk
    "bg_dk": (10, 8, 26, 255),      # corner vignette
    "violet": (38, 30, 74, 255),    # upper dusk haze
    "star": (150, 150, 198, 255),   # lavender dusk stars (panel bevel_lo)
    "deep": (120, 42, 26, 255),     # dark rust: heart rim, warm bg haze
    "ember_dk": (168, 64, 24, 255),
    "ember": (232, 120, 40, 255),
    "ember_lt": (248, 200, 88, 255),
    "white": (255, 244, 214, 255),  # hottest core
}

MASKABLE_SHRINK = 0.85


def _heart_hit(x, y, s):
    """Emberheart silhouette: two lobe circles + a cone tangent to them
    meeting at the bottom point. Design units relative to the canvas
    center (15.5, 15.5), scaled by `s`."""
    X = (x - 15.5) / s
    Y = (y - 15.5) / s
    for lx in (-6.0, 6.0):
        if (X - lx) ** 2 + (Y + 0.5) ** 2 <= 49.0:
            return True
    if Y > 12.5 or Y < -0.5:
        return False
    if Y >= 5.165:  # below the tangency: straight taper to the point
        return abs(X) <= 1.3786 * (12.5 - Y)
    # between the lobes: fill up to the lobes' outer envelope
    return abs(X) <= 6.0 + math.sqrt(max(0.0, 49.0 - (Y + 0.5) ** 2))


def _flame_depth(x, y, s):
    """> 0 inside a flame lick; magnitude = design-px distance to its edge.
    A wobbling main tongue rising from the notch plus two side licks."""
    X = (x - 15.5) / s
    Y = (y - 15.5) / s
    best = 0.0
    if -13.5 <= Y <= -4.0:
        k = (Y + 13.5) / 9.5
        wob = (0.15, 0.9, -0.6)[int(-Y) % 3]
        best = max(best, 0.6 + 3.1 * k - abs(X - wob * (1 - k)))
    if -9.5 <= Y <= -5.0:
        best = max(best, 0.4 + 1.4 * (Y + 9.5) / 4.5 - abs(X + 5.2))
    if -10.5 <= Y <= -5.5:
        best = max(best, 0.4 + 1.3 * (Y + 10.5) / 5.0 - abs(X - 4.9))
    return best


def emberheart_art(s=1.0):
    """32x32 key art on transparency: flame licks behind, shaded heart in
    front (5-color ember ramp), molten notch core, drifting sparks."""
    t = new_img(32, 32)
    px = t.load()
    P = ICON_PAL
    heart = [[_heart_hit(x, y, s) for x in range(32)] for y in range(32)]
    for y in range(32):
        for x in range(32):
            if heart[y][x]:
                continue
            m = _flame_depth(x, y, s)
            if m <= 0:
                continue
            Y = (y - 15.5) / s
            if Y <= -12.3:
                c = P["ember_lt"]  # bright tip
            elif m > 2.3:
                c = P["white"]
            elif m > 1.2:
                c = P["ember_lt"]
            else:
                c = P["ember"]
            px[x, y] = c
    for y in range(32):
        for x in range(32):
            if not heart[y][x]:
                continue
            X = (x - 15.5) / s
            Y = (y - 15.5) / s
            c = P["ember"]
            # vertical ramp: mid orange crown -> dark ember -> rust tip
            if Y > 4.0 and BAYER4[y & 3][x & 3] < min(16, int((Y - 4.0) * 4)):
                c = P["ember_dk"]
            if Y > 8.0:
                c = P["ember_dk"]
            if Y > 10.0 and BAYER4[(y + 1) & 3][x & 3] < min(16, int((Y - 10.0) * 5)):
                c = P["deep"]
            # right-side form shadow
            if X > 7.5 and -2.0 <= Y <= 4.0 and BAYER4[y & 3][(x + 2) & 3] < 6:
                c = P["ember_dk"]
            # upper-left lobe highlight + hot glint, right lobe counter-sheen
            if ((X + 6.3) / 3.6) ** 2 + ((Y + 3.8) / 2.8) ** 2 <= 1.0:
                c = P["ember_lt"]
            if ((X + 7.2) / 1.5) ** 2 + ((Y + 4.6) / 1.2) ** 2 <= 1.0:
                c = P["white"]
            if ((X - 5.6) / 2.1) ** 2 + ((Y + 4.2) / 1.6) ** 2 <= 1.0 and BAYER4[y & 3][x & 3] < 8:
                c = P["ember_lt"]
            # molten core where the flame meets the notch
            if abs(X) + abs(Y + 1.2) * 1.3 <= 3.4:
                c = P["ember_lt"]
            if abs(X) + abs(Y + 1.2) * 1.3 <= 1.7:
                c = P["white"]
            # dark rust rim on the silhouette
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < 32 and 0 <= ny < 32) or not heart[ny][nx]:
                    c = P["deep"]
                    break
            px[x, y] = c
    # drifting sparks (design offsets scale with the art)
    for dx_, dy_, key in (
        (-11.5, -6.0, "ember_lt"), (10.2, -7.6, "white"), (13.0, 1.5, "ember"),
        (-12.8, 3.5, "ember"), (7.6, -10.6, "ember_lt"),
    ):
        sx = int(round(15.5 + dx_ * s))
        sy = int(round(15.5 + dy_ * s))
        if 0 <= sx < 32 and 0 <= sy < 32 and px[sx, sy][3] == 0:
            px[sx, sy] = P[key]
    return t


def icon_bg(n):
    """Full-bleed n x n dusk background: violet upper haze, warm ember pool
    behind the heart's lower half, corner vignette, lavender stars."""
    t = new_img(n, n, ICON_PAL["bg"])
    px = t.load()
    P = ICON_PAL
    third = n // 3
    dither(px, 0, 0, n - 1, third, P["violet"], 2)
    dither(px, 0, third + 1, n - 1, 2 * third, P["violet"], 1, oy=1)
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            if px[x, y] == P["bg"] and (x - c) ** 2 + (y - 0.62 * n) ** 2 <= (0.36 * n) ** 2 \
                    and BAYER4[y & 3][x & 3] < 2:
                px[x, y] = P["deep"]
            if (x - c) ** 2 + (y - c) ** 2 >= (0.66 * n) ** 2 and BAYER4[(y + 2) & 3][x & 3] < 3:
                px[x, y] = P["bg_dk"]
    for fx, fy in ((0.16, 0.14), (0.8, 0.09), (0.9, 0.33), (0.07, 0.45), (0.68, 0.2)):
        px[int(fx * n), int(fy * n)] = P["star"]
    return t


def _nn(img, size):
    return img.resize((size, size), Image.NEAREST)


def gen_icon_192():
    return _nn(Image.alpha_composite(icon_bg(32), emberheart_art()), 192)


def gen_icon_512():
    return _nn(Image.alpha_composite(icon_bg(32), emberheart_art()), 512)


def gen_icon_maskable():
    return _nn(Image.alpha_composite(icon_bg(32), emberheart_art(MASKABLE_SHRINK)), 512)


def gen_apple_icon():
    base = icon_bg(36)  # 36x36 base -> exact 5x nearest-neighbour to 180
    base.alpha_composite(emberheart_art(), (2, 2))
    return _nn(base, 180)


# ---------------------------------------------------------------------------
# Self-checks (PLAN §6 source-asset-lint mirror; exit non-zero on failure)


def unique_colors(img):
    """Unique (r,g,b,a) values with a>0 — full transparency excluded."""
    return {c for _, c in img.convert("RGBA").getcolors(maxcolors=1 << 24) if c[3] > 0}


def check(cond, msg):
    if not cond:
        print(f"SELF-CHECK FAILED: {msg}", file=sys.stderr)
        sys.exit(1)


# Sheets allowed to exceed the 96px frame-height rule: battle backdrops are
# full 256x144 scenes, and the v2 tileset is a 128px-tall grid of 16px
# tiles, not sprite frames. (CI's source-asset-lint only enforces the
# divisible-by-16 grid, which both satisfy — verified against
# .github/workflows/ci.yml.)
H96_EXEMPT = ("backdrops", "tilesets")

REQUIRED_MANIFEST_IDS = (
    "enemy.spider", "enemy.wisp", "enemy.revenant", "enemy.chimera",
    "enemy.minis", "hero.overworld", "backdrop.forest", "backdrop.marsh",
    "backdrop.ruin", "backdrop.lair", "ui.panel", "ui.touch", "tile.anim",
)


def self_check(generated):
    for path in generated:
        img = Image.open(path)
        w, h = img.size
        rel = os.path.relpath(path, ROOT)
        check(w % 16 == 0 and h % 16 == 0, f"{path}: {w}x{h} not divisible by 16")
        exempt = any(os.sep + e + os.sep in path for e in H96_EXEMPT)
        check(exempt or h <= 96, f"{path}: frame height exceeds 96")
        if path.endswith(os.path.join("tilesets", "overworld.png")):
            check((w, h) == (256, 128), f"{path}: tileset must be 256x128, got {w}x{h}")
            # per-tile <= 16 colors, master pool <= 32 on the sheet
            used = 0
            for i in range(tileset_v2.TILECOUNT):
                cx, cy = (i % 16) * 16, (i // 16) * 16
                tile = img.crop((cx, cy, cx + 16, cy + 16))
                cols = unique_colors(tile)
                check(len(cols) <= 16, f"{path} tile {i}: {len(cols)} unique colors (> 16)")
                used += bool(cols)
            total = len(unique_colors(img))
            check(total <= 32, f"{path}: {total} colors exceed the 32-color master pool")
            print(f"  ok {rel}  {w}x{h}  {used} tiles used, sheet pool {total} colors, per-tile <= 16")
        else:
            n = len(unique_colors(img))
            check(n <= 16, f"{path}: {n} unique colors (> 16)")
            print(f"  ok {rel}  {w}x{h}  {n} colors")

    # hero sheet: 128x48, 8 distinct 16x24 frames on the top row, bottom
    # frame row fully transparent (sheet padded to the CI 16px grid)
    hero = Image.open(os.path.join(SPRITES, "hero-overworld.png"))
    check(hero.size == (128, 48), f"hero-overworld.png: {hero.size} != (128, 48)")
    frames = [hero.crop((i * 16, 0, i * 16 + 16, 24)).tobytes() for i in range(8)]
    for a in range(8):
        for b in range(a + 1, 8):
            check(frames[a] != frames[b], f"hero-overworld frames {a} and {b} are identical")
    pad = hero.crop((0, 24, 128, 48))
    check(pad.getchannel("A").getextrema()[1] == 0, "hero-overworld pad row not transparent")
    print("  ok hero-overworld.png  8 distinct 16x24 frames, pad row clear")

    # minis: frames 0-6 non-empty, idle pairs distinct, frame 7 clear,
    # shadow blob (frame 6) soft — its darkest pixel stays translucent
    minis = Image.open(os.path.join(SPRITES, "overworld-minis.png"))
    check(minis.size == (128, 16), f"overworld-minis.png: {minis.size} != (128, 16)")
    mf = [minis.crop((i * 16, 0, i * 16 + 16, 16)) for i in range(8)]
    for i in range(7):
        check(mf[i].getchannel("A").getextrema()[1] > 0, f"minis frame {i} is empty")
    for a, b in ((0, 1), (2, 3), (4, 5)):
        check(mf[a].tobytes() != mf[b].tobytes(), f"minis frames {a}/{b} identical (no bob)")
    check(mf[7].getchannel("A").getextrema()[1] == 0, "minis frame 7 must stay transparent")
    check(mf[6].getchannel("A").getextrema()[1] < 255, "minis shadow blob must be translucent")
    print("  ok overworld-minis.png  3 idle pairs + soft shadow, spare frame clear")

    # tile-anim frames 0/2/4 must be pixel-identical to the tileset-v2 tiles
    # that carry the anim property (water/marshwater/ember)
    tiles = Image.open(os.path.join(TILESETS, "overworld.png"))
    anim = Image.open(os.path.join(SPRITES, "tile-anim.png"))
    for frame, tid in TILE_ANIM_PAIRS:
        a = anim.crop((frame * 16, 0, frame * 16 + 16, 16)).tobytes()
        tx, ty = (tid % 16) * 16, (tid // 16) * 16
        b = tiles.crop((tx, ty, tx + 16, ty + 16)).tobytes()
        check(a == b, f"tile-anim frame {frame} != tileset tile id {tid}")
        alt = anim.crop((frame * 16 + 16, 0, frame * 16 + 32, 16)).tobytes()
        check(alt != a, f"tile-anim frames {frame}/{frame + 1} are identical (no shimmer)")
    anim_ids = tileset_v2.anim_ids()
    check(
        {tid for _, tid in TILE_ANIM_PAIRS} == set(anim_ids),
        "TILE_ANIM_PAIRS out of sync with tileset_v2 anim properties",
    )
    print("  ok tile-anim.png  frames 0/2/4 match the anim-property tiles, pairs animate")

    # ui-touch: 5 frames; the base cross must rotate cleanly and the pressed
    # overlay must land pixel-exact on it (the engine rotates frame 1)
    touch = Image.open(os.path.join(SPRITES, "ui-touch.png"))
    check(touch.size == (160, 32), f"ui-touch.png: {touch.size} != (160, 32)")
    tf = [touch.crop((i * 32, 0, i * 32 + 32, 32)) for i in range(5)]
    for i, f in enumerate(tf):
        check(f.getchannel("A").getextrema()[1] > 0, f"ui-touch frame {i} is empty")
        for j in range(i + 1, 5):
            check(f.tobytes() != tf[j].tobytes(), f"ui-touch frames {i}/{j} identical")
    m0 = tf[0].getchannel("A").point(lambda v: 255 if v else 0)
    check(
        m0.tobytes() == m0.transpose(Image.ROTATE_90).tobytes(),
        "ui-touch D-pad silhouette is not 4-fold rotation symmetric",
    )
    a0 = tf[0].getchannel("A").tobytes()
    a1 = tf[1].getchannel("A").tobytes()
    for i in range(32 * 32):
        if a1[i]:
            x, y = i % 32, i // 32
            check(a0[i] != 0, f"ui-touch overlay pixel ({x},{y}) outside the D-pad base")
            check(
                CROSS_ARM[0] <= x <= CROSS_ARM[1] and y <= 13,
                f"ui-touch overlay pixel ({x},{y}) not confined to the UP arm",
            )
    m1 = tf[1].getchannel("A")
    check(
        m1.tobytes() == m1.transpose(Image.FLIP_LEFT_RIGHT).tobytes(),
        "ui-touch overlay silhouette is not mirror-symmetric",
    )
    print("  ok ui-touch.png  5 frames; overlay aligned to base, silhouette rotation-safe")

    # bitmap font: .fnt parses, chars 32-126 all present and in-bounds
    font_png = Image.open(os.path.join(FONTS, "font.png"))
    with open(os.path.join(FONTS, "font.fnt"), encoding="utf-8") as f:
        errs = pixelfont.validate_fnt(f.read(), font_png.size)
    check(not errs, "; ".join(errs) if errs else "")
    print(f"  ok font.fnt  chars 32-126 present, metrics in-bounds ({font_png.size[0]}x{font_png.size[1]})")

    with open(ART_MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    for rid in REQUIRED_MANIFEST_IDS:
        check(rid in manifest, f"art-manifest missing required id '{rid}'")
    for key, entry in manifest.items():
        p = os.path.join(PUB, entry["file"])
        check(os.path.isfile(p), f"art-manifest '{key}' -> {entry['file']} missing under public/")
        img = Image.open(p)
        w, h = img.size
        fw, fh = entry["frameWidth"], entry["frameHeight"]
        check(w % fw == 0 and h % fh == 0, f"{key}: sheet {w}x{h} not divisible by {fw}x{fh}")
        nframes = (w // fw) * (h // fh)
        idxs = [i for a in entry["anims"].values() for i in a["frames"]]
        if idxs:
            check(max(idxs) < nframes, f"{key}: anim frame {max(idxs)} outside sheet ({nframes} frames)")
        print(f"  ok manifest {key} -> {entry['file']} ({nframes} frames)")
    print("All self-checks passed.")


def self_check_icons():
    dims = {
        ICON_192: (192, 192),
        ICON_512: (512, 512),
        ICON_MASKABLE: (512, 512),
        APPLE_ICON: (180, 180),
    }
    for path, want in dims.items():
        img = Image.open(path).convert("RGBA")
        rel = os.path.relpath(path, ROOT)
        check(img.size == want, f"{path}: {img.size} != {want}")
        n = len(unique_colors(img))
        check(n <= 16, f"{path}: {n} unique colors (> 16)")
        check(img.getchannel("A").getextrema()[0] == 255, f"{path}: not fully opaque")
        print(f"  ok {rel}  {want[0]}x{want[1]}  {n} colors, opaque")
    # the apple icon (180 is not 16-divisible) must sit OUTSIDE public/assets,
    # or CI's source-asset-lint PNG grid rule would fail the build
    check(
        os.path.dirname(APPLE_ICON) == PUB,
        "apple-touch-icon.png must live at public/ root, outside assets/",
    )
    # maskable safe zone: every key-art pixel block (diff vs the pure
    # background) stays inside the centered circle of radius 40% of the edge
    mask_img = Image.open(ICON_MASKABLE).convert("RGBA").load()
    bg = _nn(icon_bg(32), 512).load()
    safe_r = 0.4 * 512
    worst = 0.0
    for y in range(512):
        for x in range(512):
            if mask_img[x, y] != bg[x, y]:
                dx = max(abs(x - 256.0), abs(x + 1.0 - 256.0))
                dy = max(abs(y - 256.0), abs(y + 1.0 - 256.0))
                worst = max(worst, math.hypot(dx, dy))
    check(worst > 0.0, "maskable icon has no key art at all")
    check(
        worst <= safe_r,
        f"maskable key art reaches {worst:.1f}px from center (safe zone {safe_r:.1f}px)",
    )
    print(f"  ok maskable safe zone: key art within {worst:.1f}px of center (limit {safe_r:.1f}px)")
    print("All icon self-checks passed.")


# ---------------------------------------------------------------------------


def main():
    for dirpath in (TILESETS, SPRITES, BACKDROPS_DIR, FONTS, ICONS_DIR):
        os.makedirs(dirpath, exist_ok=True)
    outputs = {
        os.path.join(TILESETS, "overworld.png"): gen_tileset,
        os.path.join(SPRITES, "hero-overworld.png"): gen_hero,
        os.path.join(SPRITES, "overworld-minis.png"): gen_minis,
        os.path.join(SPRITES, "spider.png"): gen_spider,
        os.path.join(SPRITES, "wisp.png"): gen_wisp,
        os.path.join(SPRITES, "revenant.png"): gen_revenant,
        os.path.join(SPRITES, "chimera.png"): gen_chimera,
        os.path.join(SPRITES, "tile-anim.png"): gen_tile_anim,
        os.path.join(SPRITES, "ui-panel.png"): gen_ui_panel,
        os.path.join(SPRITES, "ui-touch.png"): gen_ui_touch,
        os.path.join(FONTS, "font.png"): pixelfont.build_font_png,
    }
    for name, fn in gen_backdrops.BACKDROPS.items():
        outputs[os.path.join(BACKDROPS_DIR, f"{name}.png")] = fn
    for path, gen in outputs.items():
        gen().save(path)
        print(f"wrote {os.path.relpath(path, ROOT)}")
    icon_outputs = {
        ICON_192: gen_icon_192,
        ICON_512: gen_icon_512,
        ICON_MASKABLE: gen_icon_maskable,
        APPLE_ICON: gen_apple_icon,
    }
    for path, gen in icon_outputs.items():
        gen().save(path)
        print(f"wrote {os.path.relpath(path, ROOT)}")
    fnt_path = os.path.join(FONTS, "font.fnt")
    with open(fnt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(pixelfont.build_fnt_xml())
    print(f"wrote {os.path.relpath(fnt_path, ROOT)}")
    self_check(list(outputs.keys()))
    self_check_icons()


if __name__ == "__main__":
    main()
