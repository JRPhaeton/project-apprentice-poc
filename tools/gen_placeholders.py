#!/usr/bin/env python3
"""Deterministic FINAL-art generator — Assets lane (M4 art pass).

Evolved from the M2 placeholder generator under the same deterministic
contract: no randomness anywhere — dithering is Bayer-matrix arithmetic and
all detail placement is pure arithmetic, so re-running reproduces every file
byte-for-byte. Generates the shipping art set per docs/ART_BIBLE.md (LOCKED):
same sheets, dimensions, frame counts and manifest logical IDs as M2,
materially better pixels, plus the M4 tileset extension to 16 tiles.

Outputs (all self-authored, CC0 — see assets/CREDITS.md):
  public/assets/tilesets/overworld.png      256x16  16 tiles 16x16
      0 grass, 1 path, 2 tree, 3 water, 4 wall, 5 sign, 6 flower,
      7 dark-grass, 8 mud, 9 marsh-water, 10 reed, 11 ruin-floor,
      12 ruin-wall, 13 ruin-door, 14 rubble-bones, 15 ember-glow
  public/assets/sprites/hero-overworld.png   64x16   4 frames 16x16
  public/assets/sprites/spider.png          448x64   7 frames 64x64
  public/assets/sprites/wisp.png            448x64   7 frames 64x64
  public/assets/sprites/revenant.png        448x64   7 frames 64x64
  public/assets/sprites/chimera.png        1440x96  15 frames 96x96

Palette discipline (ART_BIBLE §2): the tileset draws from one <=32-color
master pool with <=16 colors per 16x16 tile; every sprite sheet <=16 colors;
shared near-black-blue outline across battle sprites; the warm ember accent
is reserved for the hero, interaction glints, and the Chimera's fire.

Run from anywhere:  python3 tools/gen_placeholders.py
Exit code is non-zero if any self-check fails.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "public")
TILESETS = os.path.join(PUB, "assets", "tilesets")
SPRITES = os.path.join(PUB, "assets", "sprites")
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
    pixels currently equal to that color (region-safe shading)."""
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if BAYER4[(y + oy) & 3][(x + ox) & 3] < level:
                if only is None or px[x, y] == only:
                    px[x, y] = color


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


# ---------------------------------------------------------------------------
# Tileset master palette (<= 32 colors on the sheet, <= 16 per tile).

T = {
    "grass_dk": (47, 96, 42, 255),
    "grass": (79, 148, 64, 255),
    "grass_lt": (108, 172, 88, 255),
    "canopy_dk": (24, 60, 30, 255),
    "canopy": (38, 88, 42, 255),
    "canopy_lt": (60, 116, 58, 255),
    "trunk": (96, 64, 36, 255),
    "trunk_lt": (130, 90, 52, 255),
    "sand": (203, 176, 120, 255),
    "sand_lt": (224, 200, 148, 255),
    "sand_dk": (168, 140, 90, 255),
    "water_dk": (30, 64, 116, 255),
    "water": (47, 98, 168, 255),
    "water_lt": (84, 140, 200, 255),
    "stone_dk": (70, 74, 84, 255),
    "stone": (108, 112, 122, 255),
    "stone_lt": (146, 150, 160, 255),
    "mud_dk": (70, 50, 34, 255),
    "mud": (102, 74, 48, 255),
    "mud_lt": (134, 102, 66, 255),
    "marsh_dk": (34, 58, 52, 255),
    "marsh": (52, 86, 74, 255),
    "marsh_lt": (74, 112, 92, 255),
    "reed_dk": (96, 108, 50, 255),
    "reed": (140, 150, 72, 255),
    "bone": (216, 208, 184, 255),
    "void": OUTLINE,
    "ember_dk": (168, 64, 24, 255),
    "ember": (232, 120, 40, 255),
    "ember_lt": (248, 200, 88, 255),
    "fl_white": (244, 244, 240, 255),
    "fl_yellow": (236, 201, 60, 255),
}


def tile_base(color):
    t = new_img(16, 16)
    ImageDraw.Draw(t).rectangle([0, 0, 15, 15], fill=color)
    return t


def grass_tile(base, lt, dk, salt, n_blades=6):
    t = tile_base(base)
    px = t.load()
    dither(px, 0, 0, 15, 15, lt, 3, ox=salt, oy=salt * 2)
    dither(px, 0, 9, 15, 15, dk, 2, ox=salt + 2, oy=salt)
    for k in range(n_blades):
        x = (k * 5 + salt * 3) % 14 + 1
        y = (k * 7 + salt * 5) % 11 + 2
        px[x, y] = dk
        px[x, min(15, y + 1)] = dk
        px[x, y - 1] = lt
    return t


def t_grass():
    return grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 0)


def t_path():
    t = tile_base(T["sand"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 5, T["sand_lt"], 4)
    dither(px, 0, 10, 15, 15, T["sand_dk"], 4, ox=1)
    # wheel-rut dashes
    d.line([(2, 8), (5, 8)], fill=T["sand_dk"])
    d.line([(9, 8), (12, 8)], fill=T["sand_dk"])
    # pebbles: dark stone with a light catch
    for (x, y) in ((3, 4), (10, 6), (13, 12), (5, 12)):
        px[x, y] = T["mud"]
        px[x + 1, y] = T["mud_dk"]
        px[x, y - 1] = T["sand_lt"]
    return t


def t_tree():
    t = grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 3, n_blades=3)
    d = ImageDraw.Draw(t)
    px = t.load()
    # trunk with lit edge
    d.rectangle([6, 10, 9, 15], fill=T["trunk"])
    d.line([(6, 10), (6, 15)], fill=T["trunk_lt"])
    # canopy: dark base, mid lump, top-left highlight, dithered blend
    d.ellipse([1, 0, 14, 12], fill=T["canopy_dk"])
    d.ellipse([2, 0, 12, 9], fill=T["canopy"])
    d.ellipse([3, 1, 8, 5], fill=T["canopy_lt"])
    dither(px, 2, 4, 13, 11, T["canopy"], 5, only=T["canopy_dk"])
    dither(px, 3, 1, 11, 6, T["canopy_lt"], 4, only=T["canopy"])
    # leaf notches at the rim
    for (x, y) in ((1, 4), (14, 6), (4, 12), (11, 12)):
        px[x, y] = T["canopy_dk"]
    return t


def t_water():
    t = tile_base(T["water"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 5, T["water_lt"], 3)
    dither(px, 0, 8, 15, 15, T["water_dk"], 6, ox=2)
    dither(px, 0, 13, 15, 15, T["water_dk"], 10, ox=1)
    # broken wave crests
    d.line([(1, 3), (5, 3)], fill=T["water_lt"])
    d.line([(8, 3), (11, 3)], fill=T["water_lt"])
    d.line([(4, 9), (7, 9)], fill=T["water_lt"])
    d.line([(11, 9), (14, 9)], fill=T["water_lt"])
    px[2, 2] = T["fl_white"]
    px[9, 8] = T["fl_white"]
    return t


def t_wall():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    for row in range(4):
        y0 = row * 4
        d.line([(0, y0 + 3), (15, y0 + 3)], fill=T["stone_dk"])  # mortar
        joints = (5, 11) if row % 2 == 0 else (2, 8, 14)
        for jx in joints:
            d.line([(jx, y0), (jx, y0 + 2)], fill=T["stone_dk"])
        # lit top edge broken at the joints, per-stone shading
        prev = -1
        for jx in list(joints) + [16]:
            if jx - prev > 1:
                d.line([(prev + 1, y0), (jx - 1, y0)], fill=T["stone_lt"])
            prev = jx
        dither(px, 0, y0 + 2, 15, y0 + 2, T["stone_dk"], 5, oy=row)
    # a crack in one stone
    d.line([(9, 5), (10, 6)], fill=T["stone_dk"])
    px[10, 5] = T["stone_dk"]
    return t


def t_sign():
    t = grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 7, n_blades=3)
    d = ImageDraw.Draw(t)
    px = t.load()
    # post with lit edge + shadow on grass
    d.line([(5, 15), (10, 15)], fill=T["grass_dk"])
    d.rectangle([7, 8, 8, 15], fill=T["trunk"])
    d.line([(7, 8), (7, 14)], fill=T["trunk_lt"])
    # board: frame + lighter face + text dashes
    d.rectangle([2, 1, 13, 8], fill=T["trunk"])
    d.rectangle([3, 2, 12, 7], fill=T["sand"])
    dither(px, 3, 2, 12, 7, T["sand_lt"], 3)
    d.line([(4, 3), (10, 3)], fill=T["mud_dk"])
    d.line([(4, 5), (11, 5)], fill=T["mud_dk"])
    # ember interaction glints (nails)
    px[2, 1] = T["ember"]
    px[13, 1] = T["ember"]
    return t


def t_flower():
    t = grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 9, n_blades=4)
    px = t.load()

    def flower(x, y, petal, core):
        px[x, y - 1] = petal
        px[x - 1, y] = petal
        px[x + 1, y] = petal
        px[x, y + 1] = petal
        px[x, y] = core
        px[x, y + 2] = T["grass_dk"]  # stem

    flower(3, 4, T["fl_white"], T["fl_yellow"])
    flower(11, 3, T["fl_yellow"], T["mud"])
    flower(7, 10, T["fl_white"], T["fl_yellow"])
    px[13, 12] = T["fl_yellow"]
    px[1, 11] = T["fl_white"]
    return t


def t_dark_grass():
    return grass_tile(T["grass_dk"], T["grass"], T["canopy_dk"], 5, n_blades=5)


def t_mud():
    t = tile_base(T["mud"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 4, T["mud_lt"], 3)
    dither(px, 0, 6, 15, 15, T["mud_dk"], 5, ox=2)
    # wet sunken blotches with a single shine pixel
    d.ellipse([2, 8, 7, 11], fill=T["mud_dk"])
    d.ellipse([9, 3, 14, 6], fill=T["mud_dk"])
    px[3, 9] = T["marsh_lt"]
    px[10, 4] = T["marsh_lt"]
    # dried streaks
    d.line([(3, 2), (6, 2)], fill=T["mud_lt"])
    d.line([(11, 13), (14, 13)], fill=T["mud_lt"])
    return t


def t_marsh_water():
    t = tile_base(T["marsh"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 4, T["marsh_lt"], 2)
    dither(px, 0, 6, 15, 15, T["marsh_dk"], 6, ox=1)
    dither(px, 0, 12, 15, 15, T["marsh_dk"], 10, ox=3)
    # dull broken ripples
    d.line([(2, 4), (5, 4)], fill=T["marsh_lt"])
    d.line([(9, 10), (12, 10)], fill=T["marsh_lt"])
    # reed hints poking through
    d.line([(3, 9), (3, 15)], fill=T["reed_dk"])
    px[3, 8] = T["reed"]
    d.line([(12, 11), (12, 15)], fill=T["reed_dk"])
    px[12, 10] = T["reed"]
    px[2, 10] = T["marsh_dk"]
    px[13, 12] = T["marsh_dk"]
    return t


def t_reed():
    t = tile_base(T["marsh"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["marsh_dk"], 4, ox=1)
    dither(px, 0, 12, 15, 15, T["marsh_dk"], 9)
    # reflections at the waterline
    d.line([(1, 13), (3, 13)], fill=T["marsh_lt"])
    d.line([(8, 14), (10, 14)], fill=T["marsh_lt"])
    # stalks: lit reed with dark flicks, two cattail heads
    for (x, top, head) in ((2, 5, 0), (6, 2, 1), (10, 5, 1), (13, 8, 0)):
        d.line([(x, top), (x, 15)], fill=T["reed"])
        px[x + 1, min(15, top + 4)] = T["reed_dk"]
        px[x + 1, min(15, top + 8)] = T["reed_dk"]
        px[x - 1, top + 1] = T["reed_dk"]  # leaf flick
        if head:
            d.rectangle([x, top, x, top + 2], fill=T["trunk"])
            px[x, top - 1] = T["reed_dk"]
    return t


def t_ruin_floor():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["stone_dk"], 3, ox=1)
    # flagstone joints (offset slabs)
    d.line([(0, 7), (15, 7)], fill=T["stone_dk"])
    for x in (5, 11):
        d.line([(x, 0), (x, 7)], fill=T["stone_dk"])
    for x in (2, 8, 13):
        d.line([(x, 8), (x, 15)], fill=T["stone_dk"])
    # slab top-left bevels
    for (bx, by) in ((0, 0), (6, 0), (12, 0), (0, 8), (3, 8), (9, 8)):
        d.line([(bx, by), (bx + 1, by)], fill=T["stone_lt"])
    # crack + chipped corner
    d.line([(3, 2), (4, 4)], fill=T["stone_dk"])
    d.line([(4, 4), (3, 6)], fill=T["stone_dk"])
    px[4, 2] = T["stone_lt"]
    # moss in the seams
    px[6, 6] = T["grass_dk"]
    px[12, 9] = T["grass_dk"]
    px[3, 13] = T["grass_dk"]
    px[13, 9] = T["grass"]
    return t


def t_ruin_wall():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    # two courses of heavy 8px blocks, offset joints
    for row in range(2):
        y0 = row * 8
        d.line([(0, y0), (15, y0)], fill=T["stone"])  # lit top edge
        d.line([(0, y0 + 7), (15, y0 + 7)], fill=T["void"])  # deep mortar
        dither(px, 0, y0 + 4, 15, y0 + 6, T["void"], 4, oy=row)
        joints = (8,) if row == 0 else (4, 12)
        for jx in joints:
            d.line([(jx, y0 + 1), (jx, y0 + 6)], fill=T["void"])
            if jx < 15:
                d.line([(jx + 1, y0 + 1), (jx + 1, y0 + 2)], fill=T["stone"])
    # crack + one chipped highlight
    d.line([(11, 9), (12, 11)], fill=T["void"])
    d.line([(12, 11), (11, 13)], fill=T["void"])
    px[2, 2] = T["stone_lt"]
    px[10, 10] = T["stone"]
    return t


def t_ruin_door():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    # masonry jambs + lintel
    d.line([(0, 0), (15, 0)], fill=T["stone"])
    for x0 in (0, 13):
        d.rectangle([x0, 0, x0 + 2, 15], fill=T["stone_dk"])
        d.line([(x0, 1), (x0, 15)], fill=T["stone"])
        px[x0 + 1, 5] = T["void"]
        px[x0 + 1, 10] = T["void"]
    # keystone
    d.rectangle([6, 0, 9, 2], fill=T["stone"])
    px[6, 2] = T["stone_lt"]
    # dark arch interior
    d.rectangle([3, 3, 12, 15], fill=T["void"])
    px[3, 3] = T["stone_dk"]
    px[12, 3] = T["stone_dk"]
    # ember glow seam between the door leaves, hotter toward the ground
    d.line([(8, 6), (8, 9)], fill=T["ember_dk"])
    d.line([(8, 10), (8, 13)], fill=T["ember"])
    d.line([(8, 14), (8, 15)], fill=T["ember_lt"])
    px[7, 15] = T["ember"]
    px[9, 15] = T["ember"]
    dither(px, 5, 13, 11, 15, T["ember_dk"], 3, only=T["void"])
    return t


def t_rubble():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["void"], 4, ox=2)
    dither(px, 0, 0, 15, 15, T["stone"], 2, ox=1, oy=2)
    # broken slabs
    d.polygon([(2, 9), (6, 8), (7, 12), (3, 13)], fill=T["stone"])
    px[3, 9] = T["stone_lt"]
    d.polygon([(10, 3), (13, 4), (12, 7), (9, 6)], fill=T["stone"])
    px[11, 4] = T["stone_lt"]
    d.line([(3, 13), (7, 12)], fill=T["void"])
    d.line([(9, 6), (12, 7)], fill=T["void"])
    # bones: femur, rib arc, a scattered joint
    d.line([(4, 3), (7, 4)], fill=T["bone"])
    px[3, 3] = T["bone"]
    px[4, 2] = T["bone"]
    px[8, 4] = T["bone"]
    px[8, 5] = T["bone"]
    d.arc([10, 10, 15, 15], 180, 300, fill=T["bone"])
    px[13, 13] = T["stone"]
    px[1, 6] = T["bone"]
    return t


def t_ember_glow():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["void"], 6, ox=1)
    # faint slab joints
    d.line([(0, 3), (4, 3)], fill=T["void"])
    d.line([(11, 12), (15, 12)], fill=T["void"])
    # glowing crack network, hot at the nodes
    d.line([(1, 10), (5, 8)], fill=T["ember"])
    d.line([(5, 8), (8, 9)], fill=T["ember"])
    d.line([(8, 9), (11, 6)], fill=T["ember"])
    d.line([(11, 6), (14, 7)], fill=T["ember_dk"])
    d.line([(5, 8), (6, 12)], fill=T["ember_dk"])
    d.line([(11, 6), (12, 3)], fill=T["ember_dk"])
    px[8, 9] = T["ember_lt"]
    px[11, 6] = T["ember_lt"]
    # warm dithered halo hugging the crack
    dither(px, 2, 6, 13, 11, T["ember_dk"], 2, only=T["stone_dk"])
    # drifting sparks
    px[4, 4] = T["ember_lt"]
    px[13, 13] = T["ember"]
    return t


def gen_tileset():
    tiles = [
        t_grass, t_path, t_tree, t_water, t_wall, t_sign, t_flower,
        t_dark_grass, t_mud, t_marsh_water, t_reed, t_ruin_floor,
        t_ruin_wall, t_ruin_door, t_rubble, t_ember_glow,
    ]
    img = new_img(256, 16)
    for i, fn in enumerate(tiles):
        img.paste(fn(), (i * 16, 0))
    return img


# ---------------------------------------------------------------------------
# 2. Hero overworld — 4 frames 16x16: 0 down, 1 up, 2 left, 3 right

HERO_PAL = {
    "cloak_dk": (44, 50, 70, 255),
    "cloak": (58, 66, 88, 255),
    "cloak_lt": (80, 92, 120, 255),
    "skin": (232, 200, 160, 255),
    "skin_dk": (196, 158, 120, 255),
    "ember": (232, 144, 48, 255),
    "ember_lt": (248, 200, 88, 255),
}


def hero_frame(facing):
    t = new_img(16, 16)
    d = ImageDraw.Draw(t)
    px = t.load()
    P = HERO_PAL
    # silhouette: hood + cloak body, outlined
    d.polygon([(4, 7), (11, 7), (13, 15), (2, 15)], fill=P["cloak"], outline=OUTLINE)
    d.ellipse([3, 1, 12, 9], fill=P["cloak"], outline=OUTLINE)
    # 3-tone cloak: lit left, shaded right
    d.line([(4, 8), (3, 14)], fill=P["cloak_lt"])
    d.line([(5, 8), (4, 14)], fill=P["cloak_lt"])
    d.line([(11, 8), (12, 14)], fill=P["cloak_dk"])
    d.line([(10, 8), (11, 14)], fill=P["cloak_dk"])
    d.line([(4, 2), (4, 5)], fill=P["cloak_lt"])  # hood rim light
    # ember hem trim — hope-coded warm accent, dashed so it stays an accent
    for hx in range(3, 13, 2):
        px[hx, 14] = P["ember"]
    # boots
    px[5, 15] = OUTLINE
    px[6, 15] = OUTLINE
    px[9, 15] = OUTLINE
    px[10, 15] = OUTLINE
    if facing == "down":
        d.rectangle([5, 4, 10, 6], fill=P["skin"])
        d.line([(5, 6), (10, 6)], fill=P["skin_dk"])
        px[6, 5] = OUTLINE
        px[9, 5] = OUTLINE
        d.line([(5, 3), (10, 3)], fill=P["cloak_dk"])  # hood brim shadow
        px[7, 8] = P["ember"]  # clasp
        px[8, 8] = P["ember_lt"]
        d.line([(8, 9), (8, 13)], fill=P["cloak_dk"])  # cloak split
    elif facing == "up":
        d.line([(8, 2), (8, 8)], fill=P["cloak_dk"])  # hood back seam
        d.ellipse([5, 2, 8, 5], fill=P["cloak_lt"])  # hood sheen
        d.line([(6, 10), (9, 10)], fill=P["cloak_dk"])  # shoulder crease
    elif facing == "left":
        d.rectangle([4, 4, 7, 6], fill=P["skin"])
        px[5, 5] = OUTLINE
        d.line([(4, 6), (7, 6)], fill=P["skin_dk"])
        d.line([(8, 3), (10, 7)], fill=P["cloak_dk"])  # hood profile fold
        px[4, 8] = P["ember"]  # clasp at the throat
        d.line([(10, 9), (12, 13)], fill=P["cloak_dk"])  # trailing hem
    else:  # right
        d.rectangle([8, 4, 11, 6], fill=P["skin"])
        px[10, 5] = OUTLINE
        d.line([(8, 6), (11, 6)], fill=P["skin_dk"])
        d.line([(7, 3), (5, 7)], fill=P["cloak_lt"])
        px[11, 8] = P["ember"]
        d.line([(5, 9), (3, 13)], fill=P["cloak_dk"])
    return t


def gen_hero():
    img = new_img(64, 16)
    for i, facing in enumerate(("down", "up", "left", "right")):
        img.paste(hero_frame(facing), (i * 16, 0))
    return img


# ---------------------------------------------------------------------------
# 3a. Spider — 7 frames 64x64: 0,1 idle · 2,3 step tell · 4,5,6 bite.
#     Forward (toward hero) = +x. Per-frame leg gait for articulation.

SPIDER_PAL = {
    "moss_dk": (52, 64, 38, 255),
    "moss": (76, 92, 56, 255),
    "moss_lt": (102, 120, 74, 255),
    "pale": (128, 146, 96, 255),
    "bone": (198, 190, 162, 255),
    "bone_dk": (150, 142, 116, 255),
    "eye": (154, 88, 184, 255),
    "eye_lt": (200, 140, 220, 255),
}


def draw_spider(f):
    t = new_img(64, 64)
    d = ImageDraw.Draw(t)
    P = SPIDER_PAL
    dx, bob, tilt = f["dx"], f["bob"], f["tilt"]
    fangs, arc = f["fangs"], f["arc"]
    cx = 26 + dx
    cy = 40 + bob
    ground = 57
    # ground shadow
    d.ellipse([cx - 21, ground - 2, cx + 19, ground + 4], fill=OUTLINE)
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
    # abdomen: 3-tone with bone chevrons + spinneret
    ell3(d, [cx - 20, cy - 12, cx - 1, cy + 9], P["moss_dk"], P["moss"], P["moss_lt"])
    d.polygon([(cx - 21, cy - 3), (cx - 17, cy - 6), (cx - 17, cy)], fill=P["moss_dk"])
    for i, mx in enumerate((cx - 16, cx - 11)):
        my = cy - 3 + i
        d.line([(mx, my), (mx + 2, my - 3)], fill=P["bone"])
        d.line([(mx + 2, my - 3), (mx + 4, my)], fill=P["bone"])
    # cephalothorax (tilts up on tell/bite)
    ell3(d, [cx - 3, cy - 8 - tilt, cx + 12, cy + 7 - tilt], P["moss_dk"], P["moss"], P["moss_lt"])
    # near legs (outlined mid-tone, in front) with dark claw tips
    for k in range(4):
        fdx, fdy = f["feet"][k]
        hx, hy = hips[k]
        fx, fy = base_feet[k] + fdx, ground + fdy
        leg(d, (hx, hy), (fx, fy), 10, OUTLINE, 3)
        leg(d, (hx, hy - 1), (fx, fy - 1), 10, P["moss"], 1)
        t.putpixel((max(0, min(63, fx)), max(0, min(63, fy))), OUTLINE)
    # eye cluster (cold violet) + pedipalps
    ey = cy - 4 - tilt
    d.rectangle([cx + 8, ey, cx + 9, ey + 1], fill=P["eye"])
    t.putpixel((cx + 8, ey), P["eye_lt"])
    d.rectangle([cx + 5, ey - 1, cx + 6, ey], fill=P["eye"])
    t.putpixel((cx + 11, ey + 1), P["eye"])
    d.line([(cx + 10, cy + 3 - tilt), (cx + 13, cy + 5 - tilt)], fill=P["bone_dk"])
    d.line([(cx + 8, cy + 4 - tilt), (cx + 10, cy + 7 - tilt)], fill=P["bone_dk"])
    # fangs: open (1) then snapped (2)
    if fangs:
        spread = 3 if fangs == 1 else 1
        for fx0, fy0 in ((cx + 11, cy + 2 - tilt), (cx + 13, cy - 1 - tilt)):
            d.polygon(
                [(fx0, fy0), (fx0 + 1 + spread, fy0 + 5), (fx0 - 2, fy0 + 2)],
                fill=P["bone"],
            )
            t.putpixel((fx0, fy0), P["bone_dk"])
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
    "pale": (196, 232, 240, 255),
    "teal": (88, 196, 204, 255),
    "teal_dk": (48, 140, 150, 255),
    "deep": (30, 96, 106, 255),
    "trail": (24, 66, 76, 255),
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
    # trailing wisp chain (shrinks while dashing)
    for k in range(trail_n):
        tx = cx - 12 - k * 8 - dx // 2
        ty = cy + 9 + k * 6
        r = 4 - k
        col = P["deep"] if k == 0 else P["trail"]
        d.ellipse([tx - r, ty - r, tx + r, ty + r], fill=col, outline=OUTLINE)
        if r >= 3:
            px[tx - 1, ty - 1] = P["teal_dk"]
    # dash streaks
    for s in range(streak):
        sy = cy - 5 + s * 5
        d.line([(cx - 26 - s * 3, sy), (cx - 14, sy)], fill=P["pale"])
        d.line([(cx - 22 - s * 3, sy + 1), (cx - 14, sy + 1)], fill=P["teal_dk"])
    # orb: outline ring, pale rim, teal body, deep under-shadow, white flame core
    rx = 11 + (1 if pulse > 1 else 0) + stretch
    ry = 11 + (1 if pulse > 1 else 0) - stretch // 2
    d.ellipse([cx - rx - 1, cy - ry - 1, cx + rx + 1, cy + ry + 1], fill=OUTLINE)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=P["pale"])
    d.ellipse([cx - rx + 3, cy - ry + 3, cx + rx - 2, cy + ry - 2], fill=P["teal"])
    d.ellipse([cx - 3, cy + ry - 6, cx + rx - 4, cy + ry - 2], fill=P["teal_dk"])
    # flame-teardrop core
    cr = 3 + pulse
    d.ellipse([cx - cr, cy - 1, cx + cr, cy + cr + 2], fill=P["white"])
    d.polygon([(cx - 2, cy + 1), (cx + (1 if dy else -1), cy - 5 - pulse), (cx + 2, cy + 1)], fill=P["white"])
    px[cx - 2, cy + 1] = P["pale"]
    # flame lick escaping the rim
    lx = cx + (2 if dy else -2)
    d.polygon([(lx - 2, cy - ry), (lx, cy - ry - 5 - pulse), (lx + 2, cy - ry)], fill=P["teal_dk"])
    # ambient glow halo (dither ring, pulses on idle)
    glow_ring(px, 64, 64, cx, cy, rx + 2, rx + 5 + pulse, P["teal_dk"], 3 + pulse)
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
            px[sx, sy] = P["white"]
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
    "cloth_dk": (50, 38, 72, 255),
    "cloth": (74, 58, 100, 255),
    "cloth_lt": (102, 84, 132, 255),
    "eye": (92, 204, 196, 255),
    "eye_dk": (48, 124, 118, 255),
}


def rev_skull(t, d, x, y, P):
    d.ellipse([x - 5, y, x + 5, y + 9], fill=P["bone"], outline=OUTLINE)
    d.ellipse([x - 4, y + 1, x + 2, y + 5], fill=P["bone_lt"])
    d.line([(x - 4, y + 3), (x + 4, y + 3)], fill=P["bone_dk"])  # brow
    # sockets with cold teal glow
    d.rectangle([x - 3, y + 4, x - 2, y + 5], fill=OUTLINE)
    d.rectangle([x + 2, y + 4, x + 3, y + 5], fill=OUTLINE)
    t.putpixel((x - 3, y + 4), P["eye"])
    t.putpixel((x + 2, y + 4), P["eye"])
    t.putpixel((x, y + 7), OUTLINE)  # nasal
    # jaw + teeth
    d.rectangle([x - 3, y + 9, x + 3, y + 12], fill=P["bone_dk"], outline=OUTLINE)
    for tx in (x - 2, x, x + 2):
        t.putpixel((tx, y + 10), P["bone"])


def rev_ribcage(t, d, x, y, P):
    d.ellipse([x - 7, y, x + 7, y + 12], fill=OUTLINE)
    d.line([(x - 7, y), (x + 7, y)], fill=P["bone"])  # clavicle
    for k in range(3):
        d.arc([x - 6, y + 1 + k * 3, x + 6, y + 7 + k * 3], 200, 340, fill=P["bone"])
    d.line([(x, y + 1), (x, y + 12)], fill=P["bone_dk"])  # spine


def rev_robe(t, d, x, y, P, sway=0):
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
    d.line([(x - 4, y + 2), (x - 6 + sway, hem - 4)], fill=P["cloth_dk"])
    d.line([(x + 2, y + 2), (x + 4 + sway, hem - 6)], fill=P["cloth_dk"])
    d.line([(x - 8, y + 2), (x - 9 + sway, hem - 5)], fill=P["cloth_lt"])


def draw_revenant(f):
    t = new_img(64, 64)
    d = ImageDraw.Draw(t)
    P = REV_PAL
    scatter, lean, arm, arc = f["scatter"], f["lean"], f["arm"], f["arc"]
    cx = 30 + lean
    ground = 58
    s = scatter
    # shadow (smaller while the pieces float)
    d.ellipse([cx - 14 + s * 3, ground - 2, cx + 14 - s * 3, ground + 3], fill=OUTLINE)
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
        return t
    # -- assembled --
    rev_robe(t, d, cx, 28, P, sway=lean // 2)
    # shins under the hem
    d.line([(cx - 4, 54), (cx - 5, ground)], fill=P["bone_dk"], width=2)
    d.line([(cx + 4, 54), (cx + 5, ground)], fill=P["bone_dk"], width=2)
    rev_ribcage(t, d, cx, 15, P)
    rev_skull(t, d, cx - lean // 2, 2, P)
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
    return t


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
    # neck joining head to shoulders
    d.line([(bx + 14, by - 10), (hx - 2, hy + 8)], fill=P["tawny"], width=7)
    d.line([(bx + 17, by - 6), (hx + 1, hy + 10)], fill=P["tawny_dk"], width=2)
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
# Self-checks (PLAN §6 source-asset-lint mirror; exit non-zero on failure)


def unique_colors(img):
    """Unique (r,g,b,a) values with a>0 — full transparency excluded."""
    return {c for _, c in img.convert("RGBA").getcolors(maxcolors=1 << 24) if c[3] > 0}


def check(cond, msg):
    if not cond:
        print(f"SELF-CHECK FAILED: {msg}", file=sys.stderr)
        sys.exit(1)


def self_check(generated):
    for path in generated:
        img = Image.open(path)
        w, h = img.size
        rel = os.path.relpath(path, ROOT)
        check(w % 16 == 0 and h % 16 == 0, f"{path}: {w}x{h} not divisible by 16")
        check(h <= 96, f"{path}: frame height exceeds 96")
        if path.endswith(os.path.join("tilesets", "overworld.png")):
            check((w, h) == (256, 16), f"{path}: tileset must be 256x16, got {w}x{h}")
            # per-tile <= 16 colors, master pool <= 32 on the sheet
            for i in range(16):
                tile = img.crop((i * 16, 0, i * 16 + 16, 16))
                n = len(unique_colors(tile))
                check(n <= 16, f"{path} tile {i}: {n} unique colors (> 16)")
            total = len(unique_colors(img))
            check(total <= 32, f"{path}: {total} colors exceed the 32-color master pool")
            print(f"  ok {rel}  {w}x{h}  16 tiles, sheet pool {total} colors, per-tile <= 16")
        else:
            n = len(unique_colors(img))
            check(n <= 16, f"{path}: {n} unique colors (> 16)")
            print(f"  ok {rel}  {w}x{h}  {n} colors")

    with open(ART_MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    for key, entry in manifest.items():
        p = os.path.join(PUB, entry["file"])
        check(os.path.isfile(p), f"art-manifest '{key}' -> {entry['file']} missing under public/")
        img = Image.open(p)
        w, h = img.size
        fw, fh = entry["frameWidth"], entry["frameHeight"]
        check(w % fw == 0 and h % fh == 0, f"{key}: sheet {w}x{h} not divisible by {fw}x{fh}")
        nframes = (w // fw) * (h // fh)
        max_idx = max(i for a in entry["anims"].values() for i in a["frames"])
        check(max_idx < nframes, f"{key}: anim frame {max_idx} outside sheet ({nframes} frames)")
        print(f"  ok manifest {key} -> {entry['file']} ({nframes} frames)")
    print("All self-checks passed.")


# ---------------------------------------------------------------------------


def main():
    os.makedirs(TILESETS, exist_ok=True)
    os.makedirs(SPRITES, exist_ok=True)
    outputs = {
        os.path.join(TILESETS, "overworld.png"): gen_tileset,
        os.path.join(SPRITES, "hero-overworld.png"): gen_hero,
        os.path.join(SPRITES, "spider.png"): gen_spider,
        os.path.join(SPRITES, "wisp.png"): gen_wisp,
        os.path.join(SPRITES, "revenant.png"): gen_revenant,
        os.path.join(SPRITES, "chimera.png"): gen_chimera,
    }
    for path, gen in outputs.items():
        gen().save(path)
        print(f"wrote {os.path.relpath(path, ROOT)}")
    self_check(list(outputs.keys()))


if __name__ == "__main__":
    main()
