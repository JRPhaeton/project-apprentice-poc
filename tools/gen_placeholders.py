#!/usr/bin/env python3
"""Deterministic placeholder-art generator — Assets lane (PLAN §6, placeholder-first).

Generates every M2 placeholder sheet programmatically (no randomness at all:
speckle/detail patterns are pure arithmetic), then self-checks:

  * every generated PNG's dimensions are divisible by 16 (PLAN §2 grid);
  * per-sheet unique-color count <= 16, excluding fully transparent pixels;
  * every file path in src/data/art-manifest.json resolves under public/,
    its sheet dimensions are divisible by its frameWidth/frameHeight, and the
    sheet holds every frame index its anims reference.

Outputs (all self-authored, CC0 — see assets/CREDITS.md):
  public/assets/tilesets/overworld.png      128x16   8 tiles 16x16
  public/assets/sprites/hero-overworld.png   64x16   4 frames 16x16
  public/assets/sprites/spider.png          448x64   7 frames 64x64
  public/assets/sprites/wisp.png            448x64   7 frames 64x64
  public/assets/sprites/revenant.png        448x64   7 frames 64x64
  public/assets/sprites/chimera.png        1440x96  15 frames 96x96

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

# ---------------------------------------------------------------------------
# Palettes (ART_BIBLE §2: desaturated dusk, cold enemies, warm ember accent
# reserved for the hero / hope-coded elements; shared near-black-blue outline).

OUTLINE = (20, 22, 40, 255)  # near-black blue, shared battle-sprite outline

TILE_PAL = {
    "grass": (79, 148, 64, 255),
    "grass_lt": (99, 168, 84, 255),
    "grass_dk": (59, 122, 48, 255),
    "sand": (203, 176, 120, 255),
    "sand_dk": (168, 144, 92, 255),
    "canopy": (29, 74, 32, 255),
    "canopy_lt": (47, 106, 51, 255),
    "trunk": (110, 74, 40, 255),
    "water": (47, 98, 168, 255),
    "water_dk": (38, 80, 140, 255),
    "wave": (210, 230, 244, 255),
    "stone": (142, 146, 152, 255),
    "stone_dk": (99, 103, 109, 255),
    "stone_lt": (174, 178, 184, 255),
    "fl_white": (244, 244, 240, 255),
    "fl_yellow": (236, 201, 60, 255),
}  # exactly 16 colors for the whole tileset sheet

HERO_PAL = {
    "cloak": (58, 66, 88, 255),
    "cloak_lt": (76, 88, 117, 255),
    "skin": (232, 200, 160, 255),
    "ember": (232, 144, 48, 255),  # warm ember accent (hope-coded)
}

SPIDER_PAL = {
    "moss": (76, 92, 56, 255),
    "moss_lt": (102, 120, 74, 255),
    "bone": (198, 190, 162, 255),
    "eye": (154, 88, 184, 255),  # cold violet
}

WISP_PAL = {
    "white": (244, 251, 255, 255),
    "pale": (191, 232, 240, 255),
    "teal": (82, 192, 200, 255),
    "teal_dk": (46, 136, 144, 255),
    "trail": (30, 88, 96, 255),
}

REVENANT_PAL = {
    "bone": (205, 196, 170, 255),
    "bone_dk": (168, 158, 132, 255),
    "cloth": (90, 72, 120, 255),
    "cloth_dk": (66, 52, 88, 255),
    "eye": (88, 200, 192, 255),  # cold teal glow
}

CHIMERA_PAL = {
    "cloak": (58, 63, 82, 255),
    "cloak_lt": (76, 82, 104, 255),
    "bone": (200, 192, 168, 255),
    "ember": (240, 160, 48, 255),  # eye glint / mane / glow (it owns fire)
    "tawny": (138, 90, 48, 255),
    "tawny_lt": (168, 120, 72, 255),
    "wing": (90, 68, 96, 255),
    "scale": (74, 122, 114, 255),  # secondary head
    "fl_or": (232, 120, 40, 255),
    "fl_ye": (248, 216, 88, 255),
    "fl_wh": (255, 248, 232, 255),
}


# ---------------------------------------------------------------------------
# Helpers


def new_img(w, h, bg=(0, 0, 0, 0)):
    return Image.new("RGBA", (w, h), bg)


def speckle(px, x0, y0, w, h, color, mod, salt):
    """Deterministic arithmetic speckle — no RNG anywhere."""
    for y in range(h):
        for x in range(w):
            if (x * 7 + y * 13 + salt) % mod == 0:
                px[x0 + x, y0 + y] = color


def leg(d, hip, foot, lift, color, width=2):
    """Two-segment leg: hip -> knee -> foot; knee raised `lift` px."""
    kx = (hip[0] + foot[0]) // 2
    ky = min(hip[1], foot[1]) - lift
    d.line([hip, (kx, ky)], fill=color, width=width)
    d.line([(kx, ky), foot], fill=color, width=width)


# ---------------------------------------------------------------------------
# 1. Overworld tileset — 8 tiles, EXACT order:
#    0 grass, 1 path, 2 tree, 3 water, 4 wall, 5 sign, 6 flower, 7 dark-grass


def gen_tileset():
    img = new_img(128, 16)
    px = img.load()
    d = ImageDraw.Draw(img)
    P = TILE_PAL

    def base(i, color):
        d.rectangle([i * 16, 0, i * 16 + 15, 15], fill=color)

    def grass_tile(i, base_c, lt, dk, salt):
        base(i, base_c)
        speckle(px, i * 16, 0, 16, 16, lt, 11, salt)
        speckle(px, i * 16, 0, 16, 16, dk, 13, salt + 5)

    # 0 grass — mid green with speckle
    grass_tile(0, P["grass"], P["grass_lt"], P["grass_dk"], 0)

    # 1 path — sandy with darker pebble dots
    base(1, P["sand"])
    speckle(px, 16, 0, 16, 16, P["sand_dk"], 9, 2)

    # 2 tree — dark canopy on trunk over grass; fills tile (reads blocking)
    grass_tile(2, P["grass"], P["grass_lt"], P["grass_dk"], 3)
    ox = 32
    d.rectangle([ox + 6, 10, ox + 9, 15], fill=P["trunk"])  # trunk
    d.ellipse([ox + 1, 0, ox + 14, 11], fill=P["canopy"])  # canopy
    d.ellipse([ox + 3, 1, ox + 9, 6], fill=P["canopy_lt"])  # highlight
    speckle(px, ox + 2, 2, 12, 9, P["canopy"], 7, 1)  # re-texture highlight

    # 3 water — blue with wave lines
    base(3, P["water"])
    ox = 48
    d.rectangle([ox, 12, ox + 15, 15], fill=P["water_dk"])
    speckle(px, ox, 0, 16, 12, P["water_dk"], 15, 4)
    d.line([(ox + 2, 4), (ox + 8, 4)], fill=P["wave"])
    d.line([(ox + 8, 10), (ox + 14, 10)], fill=P["wave"])

    # 4 wall — grey stone courses (running bond)
    base(4, P["stone"])
    ox = 64
    for row, my in enumerate((3, 7, 11, 15)):
        d.line([(ox, my), (ox + 15, my)], fill=P["stone_dk"])  # mortar course
        top = my - 3
        d.line([(ox, top), (ox + 15, top)], fill=P["stone_lt"])  # stone top lite
        joints = (5, 11) if row % 2 == 0 else (2, 8, 14)
        for jx in joints:
            d.line([(ox + jx, top + 1), (ox + jx, my - 1)], fill=P["stone_dk"])

    # 5 sign — brown post + board over grass
    grass_tile(5, P["grass"], P["grass_lt"], P["grass_dk"], 7)
    ox = 80
    d.rectangle([ox + 7, 8, ox + 8, 15], fill=P["trunk"])  # post
    d.rectangle([ox + 2, 2, ox + 13, 8], fill=P["trunk"])  # board frame
    d.rectangle([ox + 3, 3, ox + 12, 7], fill=P["sand"])  # board face
    d.line([(ox + 4, 4), (ox + 9, 4)], fill=P["stone_dk"])  # text dashes
    d.line([(ox + 4, 6), (ox + 11, 6)], fill=P["stone_dk"])

    # 6 flower — grass + white/yellow dots
    grass_tile(6, P["grass"], P["grass_lt"], P["grass_dk"], 9)
    ox = 96
    for fx, fy, c in (
        (2, 3, "fl_white"),
        (10, 2, "fl_yellow"),
        (5, 9, "fl_yellow"),
        (12, 11, "fl_white"),
    ):
        d.rectangle([ox + fx, fy, ox + fx + 1, fy + 1], fill=P[c])

    # 7 dark-grass — deeper green with speckle
    grass_tile(7, P["grass_dk"], P["grass"], P["canopy"], 6)

    return img


# ---------------------------------------------------------------------------
# 2. Hero overworld — 4 frames 16x16: 0 down, 1 up, 2 left, 3 right


def gen_hero():
    img = new_img(64, 16)
    d = ImageDraw.Draw(img)
    P = HERO_PAL

    def frame(i, facing):
        ox = i * 16
        # cloak body (trapezoid) + hood
        d.polygon(
            [(ox + 4, 6), (ox + 11, 6), (ox + 13, 15), (ox + 2, 15)],
            fill=P["cloak"],
            outline=OUTLINE,
        )
        d.ellipse([ox + 4, 1, ox + 11, 8], fill=P["cloak"], outline=OUTLINE)
        # ember trim at hem — warm accent (ART_BIBLE: hope-coded)
        d.line([(ox + 3, 14), (ox + 12, 14)], fill=P["ember"])
        if facing == "down":
            d.rectangle([ox + 6, 4, ox + 9, 6], fill=P["skin"])  # face centered
            d.point((ox + 7, 8), fill=P["ember"])  # clasp
        elif facing == "up":
            d.line([(ox + 7, 2), (ox + 7, 7)], fill=P["cloak_lt"])  # hood seam
        elif facing == "left":
            d.rectangle([ox + 4, 4, ox + 6, 6], fill=P["skin"])  # profile left
            d.line([(ox + 9, 3), (ox + 11, 7)], fill=P["cloak_lt"])
        else:  # right
            d.rectangle([ox + 9, 4, ox + 11, 6], fill=P["skin"])  # profile right
            d.line([(ox + 6, 3), (ox + 4, 7)], fill=P["cloak_lt"])

    for i, facing in enumerate(("down", "up", "left", "right")):
        frame(i, facing)
    return img


# ---------------------------------------------------------------------------
# 3a. Spider — 7 frames 64x64: 0,1 idle bob · 2,3 step tell · 4,5,6 bite lunge
#     Forward (toward hero) = +x.


def draw_spider(d, ox, dx, bob, lift, tilt, fangs, arc):
    cx = ox + 24 + dx
    cy = 40 + bob
    P = SPIDER_PAL
    ground = 56
    # legs (4 back moss-dark, drawn first, then 4 front outline-color)
    hips = [(cx - 12, cy), (cx - 6, cy - 2), (cx + 2, cy - 2), (cx + 8, cy)]
    feet_x = [cx - 20, cx - 10, cx + 10, cx + 18]
    for k, (hip, fx) in enumerate(zip(hips, feet_x)):
        if k >= 2 and lift >= 10:
            # tell rear-up: front legs pawing in the air, forward and high
            fy = cy - 6 - (lift - 10)
            fx += 6
        else:
            raised = lift if k >= 2 else lift // 2
            fy = ground - raised - (1 if (k + bob) % 2 else 0)
        leg(d, (hip[0] - 2, hip[1] + 1), (fx - 2, fy), 8, P["moss"], 2)
        leg(d, hip, (fx, fy), 10, OUTLINE, 2)
    # abdomen + cephalothorax (tilt lifts the front on tell/bite)
    d.ellipse([cx - 18, cy - 11, cx, cy + 9], fill=P["moss"], outline=OUTLINE)
    d.ellipse([cx - 15, cy - 8, cx - 5, cy - 1], fill=P["moss_lt"])  # shading
    d.ellipse(
        [cx - 2, cy - 7 - tilt, cx + 12, cy + 7 - tilt], fill=P["moss"], outline=OUTLINE
    )
    d.ellipse([cx, cy - 5 - tilt, cx + 8, cy - tilt], fill=P["moss_lt"])
    # bone markings on abdomen
    d.line([(cx - 14, cy - 4), (cx - 8, cy - 4)], fill=P["bone"])
    d.line([(cx - 12, cy + 1), (cx - 6, cy + 1)], fill=P["bone"])
    # eyes (cold violet)
    d.rectangle([cx + 8, cy - 4 - tilt, cx + 9, cy - 3 - tilt], fill=P["eye"])
    d.rectangle([cx + 5, cy - 4 - tilt, cx + 6, cy - 3 - tilt], fill=P["eye"])
    # fangs
    if fangs:
        spread = 3 if fangs == 1 else 1  # open then snapped shut
        d.polygon(
            [
                (cx + 11, cy + 2 - tilt),
                (cx + 12 + spread, cy + 7 - tilt),
                (cx + 9, cy + 4 - tilt),
            ],
            fill=P["bone"],
        )
        d.polygon(
            [
                (cx + 13, cy - 1 - tilt),
                (cx + 15 + spread, cy + 3 - tilt),
                (cx + 12, cy + 1 - tilt),
            ],
            fill=P["bone"],
        )
    for s in range(arc):  # lunge speed streaks behind the body
        sy = cy - 6 + s * 6
        d.line([(cx - 34 - arc * 2, sy), (cx - 22, sy)], fill=P["bone"])


def gen_spider():
    img = new_img(448, 64)
    d = ImageDraw.Draw(img)
    # frame: dx, bob, lift, tilt, fangs, arc
    frames = [
        (0, 0, 0, 0, 0, 0),  # 0 idle
        (0, 1, 0, 0, 0, 0),  # 1 idle bob
        (5, -1, 10, 4, 0, 0),  # 2 tell: forward, front legs rear up
        (6, -2, 13, 5, 0, 0),  # 3 tell: further, legs pawing higher
        (9, -2, 8, 5, 1, 0),  # 4 bite: rear up, fangs open
        (14, 1, 2, 1, 2, 3),  # 5 bite: full lunge + streaks
        (7, 0, 1, 0, 0, 2),  # 6 bite: recoil
    ]
    for i, (dx, bob, lift, tilt, fangs, arc) in enumerate(frames):
        draw_spider(d, i * 64, dx, bob, lift, tilt, fangs, arc)
    return img


# ---------------------------------------------------------------------------
# 3b. Wisp — 7 frames: 0,1 idle flicker · 2,3 cast flare+halo · 4,5,6 dash


def draw_wisp(d, ox, dx, dy, core, halo, streak, trail_n):
    P = WISP_PAL
    cx = ox + 26 + dx
    cy = 28 + dy
    # trailing wisp (down-left chain, shrinks while dashing)
    for t in range(trail_n):
        tx = cx - 10 - t * 7 - (dx // 2)
        ty = cy + 8 + t * 5
        r = 4 - t
        d.ellipse([tx - r, ty - r, tx + r, ty + r], fill=P["trail"])
    # speed streaks behind the dash
    for s in range(streak):
        sy = cy - 4 + s * 4
        d.line([(cx - 24 - s * 3, sy), (cx - 12, sy)], fill=P["pale"])
    # orb: outline ring, pale, teal, white-hot core
    r = 11 + (1 if core > 1 else 0)
    d.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1], fill=OUTLINE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=P["pale"])
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=P["teal"])
    cr = 3 + core * 2
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=P["white"])
    # flame lick on top (flickers between idle frames)
    lx = cx + (2 if dy else -2)
    d.polygon([(lx - 3, cy - r), (lx, cy - r - 6 - core), (lx + 3, cy - r)], fill=P["teal_dk"])
    # cast halo ring(s)
    if halo:
        hr = 14 + halo * 3
        d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], outline=P["white"], width=1)
        if halo > 1:
            d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], outline=P["teal_dk"], width=1)


def gen_wisp():
    img = new_img(448, 64)
    d = ImageDraw.Draw(img)
    # frame: dx, dy, core, halo, streak, trail_n
    frames = [
        (0, 0, 0, 0, 0, 3),  # 0 idle
        (0, 2, 1, 0, 0, 3),  # 1 idle flicker (bob + brighter core)
        (0, 0, 1, 1, 0, 3),  # 2 cast: flare + halo
        (0, -1, 2, 2, 0, 3),  # 3 cast: full flare, double halo
        (6, 0, 1, 0, 1, 2),  # 4 dash start
        (16, 1, 1, 0, 2, 1),  # 5 dash mid
        (26, 0, 2, 0, 3, 0),  # 6 dash impact (no trail left)
    ]
    for i, (dx, dy, core, halo, streak, trail_n) in enumerate(frames):
        draw_wisp(d, i * 64, dx, dy, core, halo, streak, trail_n)
    return img


# ---------------------------------------------------------------------------
# 3c. Revenant — 7 frames: 0,1 idle sway · 2,3 reassemble · 4,5,6 swing


def draw_revenant_piece(d, kind, x, y, P):
    if kind == "head":  # skull with teal eye sockets
        d.ellipse([x - 5, y, x + 5, y + 10], fill=P["bone"], outline=OUTLINE)
        d.rectangle([x - 3, y + 4, x - 2, y + 5], fill=P["eye"])
        d.rectangle([x + 2, y + 4, x + 3, y + 5], fill=P["eye"])
        d.line([(x - 2, y + 8), (x + 2, y + 8)], fill=P["bone_dk"])
    elif kind == "torso":  # grave-cloth chest with rib lines
        d.polygon(
            [(x - 8, y), (x + 8, y), (x + 6, y + 14), (x - 6, y + 14)],
            fill=P["cloth"],
            outline=OUTLINE,
        )
        for r in range(3):
            d.line([(x - 4, y + 3 + r * 4), (x + 4, y + 3 + r * 4)], fill=P["bone"])
    elif kind == "hips":  # tattered lower cloth
        d.polygon(
            [(x - 6, y), (x + 6, y), (x + 7, y + 8), (x + 2, y + 6), (x - 2, y + 9), (x - 7, y + 8)],
            fill=P["cloth_dk"],
            outline=OUTLINE,
        )


def draw_revenant(d, ox, scatter, lean, arm, arc):
    P = REVENANT_PAL
    cx = ox + 30 + lean
    ground = 56
    s = scatter
    # legs (skip while scattered — pieces float)
    if s == 0:
        d.line([(cx - 4, 42), (cx - 6 - lean, ground)], fill=P["bone_dk"], width=2)
        d.line([(cx + 4, 42), (cx + 6 - lean, ground)], fill=P["bone_dk"], width=2)
    draw_revenant_piece(d, "hips", cx - s * 5, 34 + s * 3, P)
    draw_revenant_piece(d, "torso", cx + s * 4, 20 - s * 2, P)
    draw_revenant_piece(d, "head", cx - lean // 2 - s * 7, 8 - s * 3, P)
    # arms + bone club
    if s:
        d.line([(cx - 14 - s * 4, 24), (cx - 10 - s * 4, 34)], fill=P["bone"], width=2)
        d.line([(cx + 14 + s * 4, 22), (cx + 12 + s * 4, 32)], fill=P["bone"], width=2)
    else:
        d.line([(cx - 7, 22), (cx - 11, 36)], fill=P["bone"], width=2)  # off arm
        if arm == 0:  # at rest
            d.line([(cx + 7, 22), (cx + 11, 36)], fill=P["bone"], width=2)
        elif arm == 1:  # windup: club overhead
            d.line([(cx + 7, 22), (cx + 12, 12)], fill=P["bone"], width=2)
            d.line([(cx + 12, 12), (cx + 20, 4)], fill=P["bone_dk"], width=3)
        elif arm == 2:  # swing: club forward
            d.line([(cx + 7, 22), (cx + 18, 20)], fill=P["bone"], width=2)
            d.line([(cx + 18, 20), (cx + 30, 24)], fill=P["bone_dk"], width=3)
        else:  # follow-through: club low
            d.line([(cx + 7, 22), (cx + 16, 32)], fill=P["bone"], width=2)
            d.line([(cx + 16, 32), (cx + 24, 42)], fill=P["bone_dk"], width=3)
    if arc:  # swing trail: short teal streaks along the club's path
        d.line([(cx + 14, 6), (cx + 22, 12)], fill=P["eye"])
        d.line([(cx + 20, 10), (cx + 27, 17)], fill=P["eye"])


def gen_revenant():
    img = new_img(448, 64)
    d = ImageDraw.Draw(img)
    # frame: scatter, lean, arm, arc
    frames = [
        (0, 0, 0, 0),  # 0 idle
        (0, -2, 0, 0),  # 1 idle sway
        (2, 0, 0, 0),  # 2 reassemble: chunks scattered wide
        (1, 0, 0, 0),  # 3 reassemble: converging
        (0, -3, 1, 0),  # 4 attack windup (club overhead)
        (0, 4, 2, 1),  # 5 swing (club forward + arc)
        (0, 2, 3, 0),  # 6 follow-through
    ]
    for i, (scatter, lean, arm, arc) in enumerate(frames):
        draw_revenant(d, i * 64, scatter, lean, arm, arc)
    return img


# ---------------------------------------------------------------------------
# 3d. Chimera — 15 frames 96x96.
#   0,1 cloaked idle · 2,3,4 cloaked attack · 5,6 uncloaked idle ·
#   7,8,9 uncloaked attack · 10,11 breath tell · 12,13,14 flame breath


def draw_cloaked(d, ox, sway, limb, arc):
    P = CHIMERA_PAL
    ax = ox + 46 + sway  # apex x
    # shroud: tall ambiguous mass — robed-pilgrim silhouette
    d.polygon(
        [
            (ax, 12),
            (ox + 62, 30),
            (ox + 74 + sway, 88),
            (ox + 22 - sway, 88),
            (ox + 30, 30),
        ],
        fill=P["cloak"],
        outline=OUTLINE,
    )
    d.polygon(
        [(ax, 16), (ox + 34, 32), (ox + 30 - sway, 86), (ox + 40, 86)],
        fill=P["cloak_lt"],
    )  # lit fold
    # single eye glint under the hood (2px, blinks to 1px on sway frame)
    d.rectangle(
        [ox + 50, 32, ox + 50 + (0 if sway else 1), 33], fill=P["ember"]
    )
    # claws peeking at the hem
    for k in range(3):
        hx = ox + 58 + k * 5
        d.polygon([(hx, 88), (hx + 2, 82), (hx + 4, 88)], fill=P["bone"])
    # attack limb bursting from the cloak
    if limb == 1:  # windup: raised up-right
        d.line([(ox + 60, 46), (ox + 76, 28)], fill=P["cloak_lt"], width=4)
        claw_at(d, ox + 76, 28, -1, P)
    elif limb == 2:  # swipe: extended forward
        d.line([(ox + 60, 50), (ox + 88, 50)], fill=P["cloak_lt"], width=4)
        claw_at(d, ox + 88, 50, 0, P)
    elif limb == 3:  # follow-through: low
        d.line([(ox + 60, 54), (ox + 80, 72)], fill=P["cloak_lt"], width=4)
        claw_at(d, ox + 80, 72, 1, P)
    if arc:  # swipe trail above the extended limb
        d.line([(ox + 62, 42), (ox + 78, 42)], fill=P["bone"])
        d.line([(ox + 68, 46), (ox + 84, 46)], fill=P["bone"])


def claw_at(d, x, y, dir_, P):
    for k in range(3):
        d.polygon(
            [(x + k * 3 - 2, y), (x + k * 3 + 6, y + dir_ * 4 + k - 2), (x + k * 3, y + 3)],
            fill=P["bone"],
        )


def draw_uncloaked(d, ox, dx, wing_up, head, glow, cone, arc, foreleg):
    """head: 0 normal, 1 pulled back, 2 reared (tell), 3 forward (breath)."""
    P = CHIMERA_PAL
    bx = ox + 34 + dx  # body center x
    by = 62
    # wings out — wide membrane fans, bigger silhouette than the cloak
    wy = 8 if wing_up else 18
    d.polygon(
        [(bx - 2, by - 12), (bx - 40, wy - 2), (bx - 30, wy + 16), (bx - 18, by - 18)],
        fill=P["wing"],
        outline=OUTLINE,
    )
    d.polygon(
        [(bx + 8, by - 14), (bx + 30, wy - 6), (bx + 34, wy + 12), (bx + 18, by - 20)],
        fill=P["wing"],
        outline=OUTLINE,
    )
    # tail
    d.line([(bx - 22, by), (bx - 36, by - 14)], fill=P["tawny"], width=3)
    d.ellipse([bx - 38, by - 18, bx - 33, by - 13], fill=P["ember"])  # ember tuft
    # leonine body + haunch
    d.ellipse([bx - 24, by - 14, bx + 24, by + 14], fill=P["tawny"], outline=OUTLINE)
    d.ellipse([bx - 24, by - 8, bx - 6, by + 12], fill=P["tawny_lt"])
    # legs
    for k, lx in enumerate((bx - 18, bx - 8, bx + 8, bx + 16)):
        up = 8 if (foreleg and k >= 2) else 0
        d.rectangle([lx, by + 10 - up, lx + 4, 88 - up], fill=P["tawny"], outline=OUTLINE)
    # secondary head (scaled, teal) behind the main head
    d.ellipse([bx + 2, by - 34, bx + 16, by - 22], fill=P["scale"], outline=OUTLINE)
    d.rectangle([bx + 12, by - 30, bx + 13, by - 29], fill=P["fl_ye"])
    # main head position by pose
    if head == 1:
        hx, hy = bx + 20, by - 34  # pulled back
    elif head == 2:
        hx, hy = bx + 16, by - 44  # reared (tell)
    elif head == 3:
        hx, hy = bx + 34, by - 26  # thrust forward (breath)
    else:
        hx, hy = bx + 26, by - 28
    # ember mane arc + head + muzzle
    d.ellipse([hx - 12, hy - 12, hx + 10, hy + 12], fill=P["ember"])  # mane
    d.ellipse([hx - 8, hy - 8, hx + 10, hy + 8], fill=P["tawny"], outline=OUTLINE)
    d.rectangle([hx + 6, hy - 2, hx + 15, hy + 4], fill=P["tawny_lt"])  # muzzle
    d.rectangle([hx + 1, hy - 4, hx + 2, hy - 3], fill=P["fl_ye"])  # eye
    if head in (2, 3):  # open jaw
        d.polygon([(hx + 8, hy + 4), (hx + 16, hy + 8), (hx + 8, hy + 7)], fill=OUTLINE)
    # throat glow building during the tell
    if glow:
        gr = 2 + glow * 2
        gx, gy = hx - 2, hy + 8
        d.ellipse([gx - gr, gy - gr, gx + gr, gy + gr], fill=P["fl_or"])
        d.ellipse([gx - gr + 2, gy - gr + 2, gx + gr - 2, gy + gr - 2], fill=P["fl_ye"])
    # flame cone
    if cone:
        mx, my = hx + 14, hy + 3  # mouth
        ex = ox + 94
        half = 4 + cone * 4
        d.polygon([(mx, my), (ex, my - half), (ex, my + half)], fill=P["fl_or"])
        d.polygon(
            [(mx, my), (ex, my - half + 3), (ex, my + half - 3)], fill=P["fl_ye"]
        )
        if cone >= 2:
            d.polygon([(mx, my), (ex, my - 2), (ex, my + 2)], fill=P["fl_wh"])
        for k in range(cone * 2):  # flicker pixels past the cone edge
            fx = mx + 10 + k * 6
            fy = my - half - 2 + (k % 3) * (half + 2)
            d.rectangle([fx, fy, fx + 1, fy + 1], fill=P["fl_ye"])
    if arc:  # lunge speed streaks behind the body
        for s in range(3):
            sy = by - 18 + s * 8
            d.line([(bx - 44, sy), (bx - 30, sy)], fill=P["bone"])


def gen_chimera():
    img = new_img(1440, 96)
    d = ImageDraw.Draw(img)
    # cloaked frames 0-4: sway, limb, arc
    cloaked = [(0, 0, 0), (2, 0, 0), (-1, 1, 0), (0, 2, 1), (1, 3, 0)]
    for i, (sway, limb, arc) in enumerate(cloaked):
        draw_cloaked(d, i * 96, sway, limb, arc)
    # uncloaked frames 5-14: dx, wing_up, head, glow, cone, arc, foreleg
    uncloaked = [
        (0, 1, 0, 0, 0, 0, 0),  # 5 idle, wings high
        (0, 0, 0, 0, 0, 0, 0),  # 6 idle, wings mid
        (-4, 0, 1, 0, 0, 0, 1),  # 7 attack windup (head back, foreleg up)
        (8, 1, 0, 0, 0, 1, 0),  # 8 attack lunge forward + arc
        (3, 0, 0, 0, 0, 0, 0),  # 9 attack recover
        (-6, 0, 2, 1, 0, 0, 0),  # 10 breath tell: head rears, glow starts
        (-6, 1, 2, 2, 0, 0, 0),  # 11 breath tell: reared high, glow blazing
        (-8, 1, 3, 1, 1, 0, 0),  # 12 breath: short cone
        (-8, 0, 3, 0, 2, 0, 0),  # 13 breath: mid cone + white core
        (-8, 1, 3, 0, 3, 0, 0),  # 14 breath: full cone
    ]
    for j, (dx, wing_up, head, glow, cone, arc, foreleg) in enumerate(uncloaked):
        draw_uncloaked(d, (5 + j) * 96, dx, wing_up, head, glow, cone, arc, foreleg)
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
        check(w % 16 == 0 and h % 16 == 0, f"{path}: {w}x{h} not divisible by 16")
        check(w <= 96 * 15 and h <= 96, f"{path}: exceeds max sheet bounds")
        n = len(unique_colors(img))
        check(n <= 16, f"{path}: {n} unique colors (> 16)")
        print(f"  ok {os.path.relpath(path, ROOT)}  {w}x{h}  {n} colors")

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
