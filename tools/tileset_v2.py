"""Tileset v2 (M8) — FF6-style overworld sheet, 256x128 (16 cols x 8 rows).

Deterministic (Bayer-matrix dithering + arithmetic detail only; re-runs are
byte-identical). This module is the single source of truth for the v2 tile
LAYOUT and tile PROPS: tools/gen_placeholders.py (sheet + tile-anim writer)
and tools/gen_maps.py (the topology-preserving map compositor) both import
from here. The compositor is the only consumer of tile indices — the engine
scans tile *properties* (collide: bool, anim: 'water'|'marshwater'|'ember'),
never indices, so this layout is free to change.

Layout (0-based tile ids; Tiled gid = id + 1):
  row 0 (0-15)   bases + decor:
      0 grass-A · 1 grass-B · 2 dark-grass · 3 ember-glow [anim ember]
      4 sign (grass base) · 5 sign (dark-grass) · 6 sign (ruin-floor)
      7 ruin-door · 8 flower · 9 reed · 10 rubble · 11 rock (grass)
      12 stump (grass) · 13 bones (dark) · 14 rock (dark) · 15 pebbles (ruin)
  row 1 (16-31)  path<->grass marching-squares set, id 16 + edge-mask
                 (mask bits: 1=N, 2=E, 4=S, 8=W fringe on that side; mask 0
                 is the full interior tile)
  row 2 (32-47)  water<->grass set, id 32 + mask — ALL collide; 32 [anim water]
  row 3 (48-63)  mud<->dark-grass set, id 48 + mask (walkable)
  row 4 (64-79)  tree CANOPY set, id 64 + mask — OVERHEAD-layer tiles, the
                 mask cuts a scalloped edge on each masked side; prop-free
  row 5 (80-95)  80-91 marsh-water<->mud minimal set (MINIMAL_MASKS order) —
                 ALL collide; 80 [anim marshwater] · 92 trunk (grass base)
                 [collide] · 93 trunk (dark) [collide] · 94 canopy hang-S
                 (tree to the S: lobes along the bottom edge) · 95 hang-W
  row 6 (96-111) 96-107 ruin-floor edge minimal set (fringe: dark-grass) ·
                 108 hang-E · 109/110/111 shadow-edge grass/dark/mud
  row 7 (112-127) 112 wall-face [collide] · 113 wall-top (overhead cap)
                 · 114 gate-face [collide] · 115 ruin-wall-face [collide]
                 · 116 ruin-wall-top (cap) · 117 cliff-face [collide]
                 · 118 cliff-top (cap) · 119 wall cap-lip · 120 ruin cap-lip
                 · 121/122 shadow-edge ruin-floor/path · 123 grass-C (feathered
                 dark patch for isolated dark cells in grass rooms) · 124-127
                 transparent spares

Wall convention: every wall/ruin-wall cell's GROUND tile is a collide FACE
tile (so the collide grid lives entirely on the ground layer); the prop-free
TOP tiles are the overhead-layer caps drawn over interior wall cells, and
the lip tiles re-draw just a face's lit cap edge on the overhead layer so a
16x24 hero walking behind a one-row wall tucks his feet behind it.
"""

from PIL import Image, ImageDraw

OUTLINE = (20, 22, 40, 255)  # shared near-black-blue outline / tile "void"

BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))

SHEET_W, SHEET_H = 256, 128
COLUMNS = 16
TILECOUNT = 128

# ---------------------------------------------------------------------------
# Master palette — M11 "Modern 2D" pool (<= 64 colors on the sheet, <= 24 per
# tile; GDD row 11 / ART_BIBLE §2). Every terrain family is a 4-5 step ramp
# with HUE-SHIFTED ends: shadows pull cool (blue/teal/purple), lights pull
# warm — never a plain darken/lighten of the same hue.

T = {
    # grass — warm sunlit greens; shadows dive toward cool teal
    "grass_dp": (28, 60, 56, 255),
    "grass_dk": (44, 90, 56, 255),
    "grass": (79, 148, 64, 255),
    "grass_lt": (118, 178, 84, 255),
    "grass_hi": (170, 212, 108, 255),
    # canopy — deep woods; cool blue depth, warm lime caps
    "canopy_dp": (16, 40, 46, 255),
    "canopy_dk": (24, 60, 38, 255),
    "canopy": (38, 88, 42, 255),
    "canopy_lt": (66, 122, 56, 255),
    "canopy_hi": (110, 160, 76, 255),
    # bark — purple-brown shadow, warm ochre striation light
    "trunk_dk": (58, 40, 48, 255),
    "trunk": (96, 64, 36, 255),
    "trunk_lt": (134, 94, 52, 255),
    "trunk_hi": (176, 136, 84, 255),
    # path sand — dusty warm; shadow pulls mauve
    "sand_dk": (152, 122, 96, 255),
    "sand": (203, 176, 120, 255),
    "sand_lt": (226, 202, 146, 255),
    "sand_hi": (246, 228, 178, 255),
    # water — depth gradient: pale warm sparkle down to cold navy
    "water_dp": (16, 38, 88, 255),
    "water_dk": (30, 64, 124, 255),
    "water": (47, 98, 168, 255),
    "water_lt": (92, 148, 204, 255),
    "water_hi": (156, 202, 234, 255),
    # stone — purple-cool shadows, warm-grey sunlit faces
    "stone_dp": (46, 46, 70, 255),
    "stone_dk": (70, 74, 94, 255),
    "stone": (108, 112, 122, 255),
    "stone_lt": (148, 150, 156, 255),
    "stone_hi": (188, 186, 180, 255),
    # mud — wet earth; cool maroon shadow, warm wet-glint light
    "mud_dp": (52, 36, 42, 255),
    "mud_dk": (72, 50, 42, 255),
    "mud": (102, 74, 48, 255),
    "mud_lt": (138, 106, 64, 255),
    "mud_hi": (176, 146, 96, 255),
    # marsh water — still teal; cold depth, pale surface sheen
    "marsh_dp": (20, 40, 48, 255),
    "marsh_dk": (34, 58, 56, 255),
    "marsh": (52, 86, 74, 255),
    "marsh_lt": (80, 118, 94, 255),
    "marsh_hi": (116, 152, 116, 255),
    # reeds
    "reed_dk": (96, 108, 50, 255),
    "reed": (140, 150, 72, 255),
    "reed_lt": (184, 190, 98, 255),
    "bone": (216, 208, 184, 255),
    "void": OUTLINE,
    # ember — rust depth to white heat
    "ember_dp": (120, 42, 26, 255),
    "ember_dk": (168, 64, 24, 255),
    "ember": (232, 120, 40, 255),
    "ember_lt": (248, 200, 88, 255),
    "ember_hi": (255, 240, 182, 255),
    "fl_white": (244, 244, 240, 255),
    "fl_yellow": (236, 201, 60, 255),
}

# Edge-mask bit convention shared by every marching-squares set + the canopy.
N, E, S, W = 1, 2, 4, 8

# Minimal 12-variant sets (spec sanctions 13-variant minimal sets; the four
# realized masks in the shipped maps are a subset of these).
MINIMAL_MASKS = (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 15)


def minimal_slot(mask):
    """Slot index inside a MINIMAL set for an arbitrary edge mask —
    deterministic fallback drops bits until the mask is available."""
    m = mask
    while m not in MINIMAL_MASKS:
        m &= m - 1  # clear lowest set bit
    return MINIMAL_MASKS.index(m)


# ---------------------------------------------------------------------------
# Helpers (kept module-local so the tileset is self-contained).


def new_img(w=16, h=16, bg=(0, 0, 0, 0)):
    return Image.new("RGBA", (w, h), bg)


def dither(px, x0, y0, x1, y1, color, level, ox=0, oy=0, only=None):
    for y in range(max(0, y0), min(15, y1) + 1):
        for x in range(max(0, x0), min(15, x1) + 1):
            if BAYER4[(y + oy) & 3][(x + ox) & 3] < level:
                if only is None or px[x, y] == only:
                    px[x, y] = color


def tile_base(color):
    t = new_img()
    ImageDraw.Draw(t).rectangle([0, 0, 15, 15], fill=color)
    return t


# ---------------------------------------------------------------------------
# Base terrains (evolved from the M6 tiles — same palette discipline).


def grass_tile(base, lt, dk, salt, n_blades=6, dp=None, hi=None):
    """Even, non-banding meadow texture (no per-tile bottom shade — a 16px
    horizontal stripe would tile into visible banding on open fields).
    M11: individual two-tone blades (dark stem, lit tip), cool deep-shadow
    specks (dp) and sparse warm sun catches (hi)."""
    dp = dp or dk
    hi = hi or lt
    t = tile_base(base)
    px = t.load()
    dither(px, 0, 0, 15, 15, lt, 3, ox=salt, oy=salt * 2)
    dither(px, 0, 0, 15, 15, dk, 2, ox=salt + 2, oy=salt + 1)
    # cool deep-shadow specks pooling between clumps
    for k in range(4):
        x = (k * 7 + salt * 5 + 3) % 15
        y = (k * 11 + salt * 3 + 6) % 15
        px[x, y] = dp
    # individual blades: dark stem, curved lit tip, warm glint on alternates
    for k in range(n_blades):
        x = (k * 5 + salt * 3) % 14 + 1
        y = (k * 7 + salt * 5) % 12 + 2
        px[x, y] = dk
        px[x, min(15, y + 1)] = dp
        px[x, y - 1] = lt
        bend = 1 if k % 2 else -1
        if 0 <= x + bend <= 15 and y >= 2:
            px[x + bend, y - 2] = hi if k % 2 else lt
        px[min(15, x + 1), min(15, y + 2)] = dk
    return t


def t_grass_a():
    return grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 0, dp=T["grass_dp"], hi=T["grass_hi"])


def t_grass_b():
    return grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 4, n_blades=5, dp=T["grass_dp"], hi=T["grass_hi"])


def t_dark_grass():
    return grass_tile(T["grass_dk"], T["grass"], T["canopy_dk"], 5, n_blades=5, dp=T["canopy_dp"], hi=T["grass_lt"])


def t_grass_c():
    """Feathered dark meadow patch on grass — used for ISOLATED dark-grass
    cells inside grass-base rooms, where the full dark tile reads as an
    abrupt hole. Edges dither into plain grass on all sides."""
    t = grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 1, n_blades=4)
    px = t.load()
    # dense core, feathered rim (never touches the tile border at full level)
    dither(px, 4, 4, 11, 11, T["grass_dk"], 12, ox=1)
    dither(px, 2, 2, 13, 13, T["grass_dk"], 7, ox=3)
    dither(px, 0, 0, 15, 15, T["grass_dk"], 3, oy=2)
    dither(px, 5, 5, 10, 10, T["canopy_dk"], 4, ox=2, only=T["grass_dk"])
    return t


def t_mud():
    t = tile_base(T["mud"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["mud_lt"], 2, oy=1)
    dither(px, 0, 0, 15, 15, T["mud_dk"], 4, ox=2)
    # wet puddle dips: cool-maroon shadow, wet specular glint on the rim
    d.ellipse([2, 8, 6, 10], fill=T["mud_dk"])
    px[3, 10] = T["mud_dp"]
    px[5, 10] = T["mud_dp"]
    d.ellipse([10, 3, 13, 5], fill=T["mud_dk"])
    px[11, 5] = T["mud_dp"]
    px[3, 9] = T["marsh_lt"]
    px[4, 8] = T["mud_hi"]  # wet glint catching the light
    px[11, 4] = T["mud_lt"]
    px[12, 3] = T["mud_hi"]
    d.line([(3, 2), (6, 2)], fill=T["mud_lt"])
    px[4, 2] = T["mud_hi"]
    d.line([(11, 13), (14, 13)], fill=T["mud_lt"])
    d.line([(6, 13), (8, 15)], fill=T["mud_dk"])
    px[7, 13] = T["mud_dp"]
    px[7, 14] = T["void"]
    px[8, 14] = T["void"]
    px[1, 6] = T["mud_dp"]
    px[14, 9] = T["mud_dp"]
    return t


def t_ruin_floor():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["stone_dk"], 3, ox=1)
    dither(px, 0, 0, 15, 6, T["stone_lt"], 2, oy=2)  # sun-warmed upper slabs
    d.line([(0, 7), (15, 7)], fill=T["stone_dk"])
    dither(px, 0, 7, 15, 7, T["stone_dp"], 6, only=T["stone_dk"])  # seam depth
    for x in (5, 11):
        d.line([(x, 0), (x, 7)], fill=T["stone_dk"])
        px[x, 5] = T["stone_dp"]
    for x in (2, 8, 13):
        d.line([(x, 8), (x, 15)], fill=T["stone_dk"])
        px[x, 12] = T["stone_dp"]
    for (bx, by) in ((0, 0), (6, 0), (12, 0), (0, 8), (3, 8), (9, 8)):
        d.line([(bx, by), (bx + 1, by)], fill=T["stone_lt"])
        px[bx, by] = T["stone_hi"]  # chipped corner catches warm light
    # crack with cool depth shading along its underside
    d.line([(3, 2), (4, 4)], fill=T["stone_dk"])
    d.line([(4, 4), (3, 6)], fill=T["stone_dk"])
    px[4, 4] = T["void"]
    px[4, 5] = T["stone_dp"]
    px[4, 2] = T["stone_lt"]
    dither(px, 0, 12, 15, 15, T["stone_dk"], 4, ox=2, only=T["stone"])
    # moss creeping out of the seams
    px[6, 6] = T["grass_dk"]
    px[7, 6] = T["grass_dp"]
    px[12, 9] = T["grass_dk"]
    px[12, 10] = T["grass_dp"]
    px[3, 13] = T["grass_dk"]
    px[13, 9] = T["grass"]
    px[10, 14] = T["grass_dk"]
    return t


def t_path_full():
    t = tile_base(T["sand"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 5, T["sand_lt"], 4)
    dither(px, 0, 0, 15, 2, T["sand_hi"], 3, ox=1)  # warm sun on the crown
    dither(px, 0, 10, 15, 15, T["sand_dk"], 4, ox=1)
    d.line([(2, 8), (5, 8)], fill=T["sand_dk"])
    d.line([(9, 8), (12, 8)], fill=T["sand_dk"])
    dither(px, 2, 9, 12, 9, T["sand_dk"], 6, only=T["sand"])
    # embedded pebbles: mud body, cool shadow, warm sun glint
    for (x, y) in ((3, 4), (10, 6), (13, 12), (5, 12)):
        px[x, y] = T["mud"]
        px[x + 1, y] = T["mud_dk"]
        px[x, y - 1] = T["sand_hi"]
        px[max(0, x - 1), y] = T["mud_lt"]
        px[min(15, x + 1), min(15, y + 1)] = T["sand_dk"]
    px[7, 3] = T["sand_hi"]
    px[8, 13] = T["sand_dk"]
    return t


def t_water_full(phase=0):
    """Animated pair tile: base pixels identical across phases, only crest
    highlights + sparkles drift (tile-anim overlay blends seamlessly).
    M11: true depth gradient — pale warm sheen at the top reading down into
    cold navy depths."""
    t = tile_base(T["water"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 5, T["water_lt"], 3)
    dither(px, 0, 0, 15, 2, T["water_hi"], 2, ox=2)  # surface sheen
    dither(px, 0, 6, 15, 9, T["water_dk"], 3, ox=1)
    dither(px, 0, 8, 15, 15, T["water_dk"], 6, ox=2)
    dither(px, 0, 11, 15, 15, T["water_dp"], 5, ox=3, only=T["water_dk"])
    dither(px, 0, 13, 15, 15, T["water_dk"], 10, ox=1)
    dither(px, 0, 14, 15, 15, T["water_dp"], 9, ox=3, only=T["water_dk"])
    px[5, 12] = T["water_dp"]  # sunken stone hint in the deep
    px[6, 12] = T["water_dp"]
    px[6, 11] = T["water_dk"]
    s = phase * 2
    d.line([(1 + s, 3), (5 + s, 3)], fill=T["water_lt"])
    px[2 + s, 3] = T["water_hi"]  # crest catch-light
    d.line([(8 + s, 3), (min(15, 11 + s), 3)], fill=T["water_lt"])
    d.line([(4 - s, 9), (7 - s, 9)], fill=T["water_lt"])
    px[5 - s, 9] = T["water_hi"]
    d.line([(11 - s, 9), (14 - s, 9)], fill=T["water_lt"])
    px[2 + s * 2, 2] = T["fl_white"]
    px[9 - s * 3, 8] = T["fl_white"]
    px[13 - s, 13] = T["water_lt"] if phase else T["water_dk"]  # deep glimmer
    return t


def t_marsh_full(phase=0):
    """Open still water (the reed tile carries the vegetation — pools ringed
    by reeds should read as water, not more reeds). Ripples drift and a
    surface glint blinks on the alternate frame."""
    t = tile_base(T["marsh"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 4, T["marsh_lt"], 2)
    dither(px, 0, 0, 15, 1, T["marsh_hi"], 2, ox=1)  # pale surface sheen
    dither(px, 0, 6, 15, 15, T["marsh_dk"], 5, ox=1)
    dither(px, 0, 10, 15, 15, T["marsh_dp"], 4, ox=2, only=T["marsh_dk"])
    dither(px, 0, 12, 15, 15, T["marsh_dk"], 9, ox=3)
    dither(px, 0, 14, 15, 15, T["marsh_dp"], 8, ox=2, only=T["marsh_dk"])
    s = phase * 2
    d.line([(2 + s, 4), (6 + s, 4)], fill=T["marsh_lt"])
    px[3 + s, 4] = T["marsh_hi"]
    d.line([(9 - s, 10), (13 - s, 10)], fill=T["marsh_lt"])
    d.line([(5 + s, 13), (8 + s, 13)], fill=T["marsh_dk"])
    px[11 - s, 2] = T["marsh_hi"]
    px[4 + s, 8] = T["marsh_lt"] if phase else T["marsh_dk"]
    # a single water-lily pad + surface glint
    d.rectangle([12, 5, 14, 6], fill=T["reed_dk"])
    px[12, 5] = T["reed"]
    px[13, 5] = T["reed_lt"]
    px[13, 7] = T["marsh_dp"]  # pad's shadow on the water
    px[2, 12] = T["marsh_lt"] if phase else T["marsh"]
    return t


def t_ember_glow(phase=0):
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["void"], 6, ox=1)
    dither(px, 0, 0, 15, 15, T["stone_dp"], 3, ox=3, oy=1, only=T["stone_dk"])
    d.line([(0, 3), (4, 3)], fill=T["void"])
    d.line([(11, 12), (15, 12)], fill=T["void"])
    hot, cool = (T["ember_lt"], T["ember"]) if phase == 0 else (T["ember"], T["ember_lt"])
    # molten crack web: rust depth at the ends, heat pooling at the joints
    d.line([(1, 10), (5, 8)], fill=T["ember"])
    px[1, 10] = T["ember_dp"]
    d.line([(5, 8), (8, 9)], fill=T["ember"])
    d.line([(8, 9), (11, 6)], fill=T["ember"])
    d.line([(11, 6), (14, 7)], fill=T["ember_dk"] if phase == 0 else T["ember"])
    px[14, 7] = T["ember_dp"]
    d.line([(5, 8), (6, 12)], fill=T["ember_dk"])
    px[6, 12] = T["ember_dp"]
    d.line([(11, 6), (12, 3)], fill=T["ember_dk"])
    px[12, 3] = T["ember_dp"]
    px[8, 9] = hot
    px[8, 8] = T["ember_hi"] if phase == 0 else T["ember_lt"]  # white-hot heart
    px[11, 6] = cool if phase else hot
    px[5, 8] = hot if phase else T["ember"]
    dither(px, 2, 6, 13, 11, T["ember_dk"], 2 + phase, only=T["stone_dk"])
    dither(px, 5, 7, 11, 10, T["ember_dp"], 3, ox=phase, only=T["stone_dk"])  # heat haze
    px[4, 4 - phase] = T["ember_lt"]
    px[13, 13 - phase] = T["ember"]
    px[2, 13] = T["ember_dp"] if phase else T["ember_dk"]  # dying coal
    return t


# ---------------------------------------------------------------------------
# Decor tiles (walkable; drawn on the base terrain they sit in).


def t_sign(base_fn):
    t = base_fn()
    d = ImageDraw.Draw(t)
    px = t.load()
    d.line([(5, 15), (10, 15)], fill=T["grass_dk"])
    d.rectangle([7, 8, 8, 15], fill=T["trunk"])
    d.line([(7, 8), (7, 14)], fill=T["trunk_lt"])
    d.rectangle([2, 1, 13, 8], fill=T["trunk"])
    px[3, 1] = T["trunk_lt"]
    px[6, 1] = T["trunk_lt"]
    px[10, 8] = T["mud_dk"]
    px[4, 8] = T["mud_dk"]
    d.rectangle([3, 2, 12, 7], fill=T["sand"])
    dither(px, 3, 2, 12, 7, T["sand_lt"], 3)
    dither(px, 3, 6, 12, 7, T["sand_dk"], 3, ox=1, only=T["sand"])
    d.line([(4, 3), (10, 3)], fill=T["mud_dk"])
    d.line([(4, 5), (11, 5)], fill=T["mud_dk"])
    px[2, 1] = T["ember"]
    px[13, 1] = T["ember"]
    return t


def t_ruin_door():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    d.line([(0, 0), (15, 0)], fill=T["stone"])
    for x0 in (0, 13):
        d.rectangle([x0, 0, x0 + 2, 15], fill=T["stone_dk"])
        d.line([(x0, 1), (x0, 15)], fill=T["stone"])
        px[x0 + 1, 5] = T["void"]
        px[x0 + 1, 10] = T["void"]
    d.rectangle([6, 0, 9, 2], fill=T["stone"])
    px[6, 2] = T["stone_lt"]
    d.rectangle([3, 3, 12, 15], fill=T["void"])
    px[3, 3] = T["stone_dk"]
    px[12, 3] = T["stone_dk"]
    d.line([(8, 6), (8, 9)], fill=T["ember_dk"])
    d.line([(8, 10), (8, 13)], fill=T["ember"])
    d.line([(8, 14), (8, 15)], fill=T["ember_lt"])
    px[7, 15] = T["ember"]
    px[9, 15] = T["ember"]
    dither(px, 5, 13, 11, 15, T["ember_dk"], 3, only=T["void"])
    dither(px, 6, 9, 10, 12, T["ember_dk"], 2, ox=1, only=T["void"])
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
        px[x, y + 2] = T["grass_dk"]

    flower(3, 4, T["fl_white"], T["fl_yellow"])
    flower(11, 3, T["fl_yellow"], T["mud"])
    flower(7, 10, T["fl_white"], T["fl_yellow"])
    px[13, 12] = T["fl_yellow"]
    px[1, 11] = T["fl_white"]
    return t


def t_reed():
    t = tile_base(T["marsh"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["marsh_dk"], 4, ox=1)
    dither(px, 0, 12, 15, 15, T["marsh_dk"], 9)
    d.line([(1, 13), (3, 13)], fill=T["marsh_lt"])
    d.line([(8, 14), (10, 14)], fill=T["marsh_lt"])
    for (x, top, head) in ((2, 5, 0), (6, 2, 1), (10, 5, 1), (13, 8, 0)):
        d.line([(x, top), (x, 15)], fill=T["reed"])
        px[x, top + 1] = T["reed_lt"]  # lit upper stalk
        px[x + 1, min(15, top + 4)] = T["reed_dk"]
        px[x + 1, min(15, top + 8)] = T["reed_dk"]
        px[x - 1, top + 1] = T["reed_dk"]
        px[x, 15] = T["reed_dk"]
        if x + 1 <= 15:
            px[x + 1, 14] = T["void"]
        if head:
            d.rectangle([x, top, x, top + 2], fill=T["trunk"])
            px[x, top - 1] = T["reed_dk"]
            px[x, top] = T["trunk_hi"]  # seed head catches the light
        else:
            px[x, top] = T["reed_lt"]
    return t


def t_rubble():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["void"], 4, ox=2)
    dither(px, 0, 0, 15, 15, T["stone"], 2, ox=1, oy=2)
    d.polygon([(2, 9), (6, 8), (7, 12), (3, 13)], fill=T["stone"])
    px[3, 9] = T["stone_lt"]
    px[4, 9] = T["stone_hi"]
    px[5, 11] = T["stone_dp"]
    d.polygon([(10, 3), (13, 4), (12, 7), (9, 6)], fill=T["stone"])
    px[11, 4] = T["stone_hi"]
    px[11, 6] = T["stone_dp"]
    d.line([(3, 13), (7, 12)], fill=T["void"])
    d.line([(9, 6), (12, 7)], fill=T["void"])
    d.line([(4, 3), (7, 4)], fill=T["bone"])
    px[3, 3] = T["bone"]
    px[4, 2] = T["bone"]
    px[8, 4] = T["bone"]
    px[8, 5] = T["bone"]
    px[5, 5] = T["void"]
    px[6, 5] = T["void"]
    d.arc([10, 10, 15, 15], 180, 300, fill=T["bone"])
    px[13, 13] = T["stone"]
    px[11, 14] = T["void"]
    px[1, 6] = T["bone"]
    px[1, 7] = T["void"]
    return t


def _boulder(t, salt=0):
    """Low irregular rock (flat base, faceted crown) with contact shadow."""
    d = ImageDraw.Draw(t)
    px = t.load()
    ox = salt % 2
    d.ellipse([2 + ox, 12, 13 + ox, 15], fill=T["void"])  # contact shadow
    d.polygon(
        [(3 + ox, 13), (2 + ox, 10), (4 + ox, 7), (8 + ox, 6), (12 + ox, 8), (13 + ox, 11), (11 + ox, 13)],
        fill=T["stone"],
        outline=OUTLINE,
    )
    # facets: lit NW planes (warm), shaded SE base (cool purple)
    d.polygon([(4 + ox, 8), (8 + ox, 7), (7 + ox, 10), (4 + ox, 10)], fill=T["stone_lt"])
    px[5 + ox, 8] = T["stone_hi"]  # sunlit facet crown
    px[6 + ox, 7] = T["stone_hi"]
    d.line([(3 + ox, 12), (11 + ox, 12)], fill=T["stone_dk"])
    dither(px, 3 + ox, 12, 11 + ox, 12, T["stone_dp"], 8, only=T["stone_dk"])
    d.line([(8 + ox, 11), (12 + ox, 10)], fill=T["stone_dk"])
    px[9 + ox, 8] = T["stone_lt"]
    px[6 + ox, 11] = T["stone_dp"]
    px[10 + ox, 13] = T["stone_dp"]
    d.line([(9 + ox, 9), (10 + ox, 10)], fill=T["stone_dk"])  # hairline crack
    px[3 + ox, 9] = T["grass_dk"]  # moss toe
    px[4 + ox, 11] = T["grass_dp"]
    return t


def t_rock_grass():
    return _boulder(grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 2, n_blades=3))


def t_rock_dark():
    return _boulder(grass_tile(T["grass_dk"], T["grass"], T["canopy_dk"], 3, n_blades=3), salt=1)


def t_stump():
    t = grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 6, n_blades=3)
    d = ImageDraw.Draw(t)
    px = t.load()
    d.ellipse([3, 12, 12, 15], fill=T["void"])  # contact shadow
    d.rectangle([4, 7, 11, 13], fill=T["trunk"], outline=OUTLINE)
    d.line([(4, 8), (4, 12)], fill=T["trunk_lt"])
    px[4, 9] = T["trunk_hi"]
    for gy in (8, 10, 12):  # bark striations on the stump side
        px[9, gy] = T["trunk_dk"]
    d.ellipse([3, 4, 12, 9], fill=T["trunk_lt"], outline=OUTLINE)
    d.ellipse([5, 5, 10, 8], outline=T["trunk"])
    px[5, 5] = T["trunk_hi"]  # cut face catches the sun
    px[6, 4] = T["trunk_hi"]
    px[7, 6] = T["mud_dk"]  # ring core
    px[8, 6] = T["trunk"]
    px[12, 10] = T["trunk_dk"]  # bark split
    px[6, 14] = T["mud_dk"]
    return t


def t_bones_dark():
    t = grass_tile(T["grass_dk"], T["grass"], T["canopy_dk"], 8, n_blades=3)
    d = ImageDraw.Draw(t)
    px = t.load()
    d.line([(3, 5), (8, 7)], fill=T["bone"])  # femur
    px[2, 4] = T["bone"]
    px[3, 4] = T["bone"]
    px[8, 8] = T["bone"]
    px[9, 7] = T["bone"]
    d.line([(4, 6), (7, 8)], fill=T["void"])  # its shadow
    d.arc([9, 10, 14, 15], 180, 320, fill=T["bone"])  # rib arc
    px[10, 13] = T["void"]
    px[4, 12] = T["bone"]  # loose joint
    px[4, 13] = T["void"]
    return t


def t_pebbles_ruin():
    t = t_ruin_floor()
    px = t.load()
    d = ImageDraw.Draw(t)
    for (x, y) in ((3, 3), (9, 5), (12, 12), (5, 10), (7, 14)):
        px[x, y] = T["stone_lt"]
        px[x + 1, y] = T["stone_dk"]
        px[x, y + 1] = T["void"]
    d.line([(10, 2), (12, 4)], fill=T["stone_dk"])  # extra crack
    px[11, 2] = T["void"]
    return t


# ---------------------------------------------------------------------------
# Marching-squares transitions. The fringe profile is period-16 with equal
# endpoints, so adjacent tiles of the same set always line up.

PROF = (3, 3, 4, 4, 4, 3, 2, 2, 3, 3, 4, 4, 3, 2, 2, 3)


def _fringe_mask(mask):
    """16x16 bools: True where the neighbouring BASE terrain shows."""
    m = [[False] * 16 for _ in range(16)]
    for i in range(16):
        if mask & N:
            for y in range(PROF[i]):
                m[y][i] = True
        if mask & S:
            for y in range(16 - PROF[(i + 8) % 16], 16):
                m[y][i] = True
        if mask & W:
            for x in range(PROF[(i + 4) % 16]):
                m[i][x] = True
        if mask & E:
            for x in range(16 - PROF[(i + 12) % 16], 16):
                m[i][x] = True
    corners = (
        (N | W, lambda x, y: x + y <= 6),
        (N | E, lambda x, y: (15 - x) + y <= 6),
        (S | W, lambda x, y: x + (15 - y) <= 6),
        (S | E, lambda x, y: (15 - x) + (15 - y) <= 6),
    )
    for bits, hit in corners:
        if mask & bits == bits:
            for y in range(16):
                for x in range(16):
                    if hit(x, y):
                        m[y][x] = True
    return m


def _rings(fr):
    """(ring1, ring2): overlay pixels 1 and 2 steps from the fringe."""
    ring1 = set()
    for y in range(16):
        for x in range(16):
            if fr[y][x]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < 16 and 0 <= ny < 16 and fr[ny][nx]:
                    ring1.add((x, y))
                    break
    ring2 = set()
    for y in range(16):
        for x in range(16):
            if fr[y][x] or (x, y) in ring1:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) in ring1:
                    ring2.add((x, y))
                    break
    return ring1, ring2


def transition(over, base, mask, style):
    """Composite `base` into `over` along the masked edges with a wavy
    boundary. style: 'path' | 'water' | 'marsh' | 'mud' | 'ruin'."""
    t = over.copy()
    if mask == 0:
        return t
    px = t.load()
    bp = base.load()
    fr = _fringe_mask(mask)
    for y in range(16):
        for x in range(16):
            if fr[y][x]:
                px[x, y] = bp[x, y]
    ring1, ring2 = _rings(fr)
    if style == "water":
        for (x, y) in ring1:
            px[x, y] = T["water_lt"]  # lapping edge
        for (x, y) in ring2:
            if BAYER4[y & 3][x & 3] < 5:
                px[x, y] = T["water_lt"]
        # bank shadow on the grass side of the waterline
        for y in range(16):
            for x in range(16):
                if fr[y][x] and any((x + dx, y + dy) in ring1 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    if BAYER4[y & 3][x & 3] < 11:
                        px[x, y] = T["grass_dk"]
    elif style == "marsh":
        for (x, y) in ring1:
            px[x, y] = T["marsh_dk"]
        for y in range(16):
            for x in range(16):
                if fr[y][x] and any((x + dx, y + dy) in ring1 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    if BAYER4[y & 3][x & 3] < 9:
                        px[x, y] = T["mud_dk"]
    elif style == "mud":
        for (x, y) in ring1:
            if BAYER4[y & 3][x & 3] < 10:
                px[x, y] = T["mud_dk"]
        for (x, y) in ring2:
            if BAYER4[y & 3][x & 3] < 4:
                px[x, y] = T["mud_dk"]
    elif style == "ruin":
        for (x, y) in ring1:
            if (x + y) % 3 != 2:
                px[x, y] = T["stone_dk"]  # broken slab rim
        for (x, y) in ring2:
            if BAYER4[y & 3][x & 3] < 3:
                px[x, y] = T["grass_dk"]  # moss creeping in
    else:  # path — soft dithered blend
        for (x, y) in ring1:
            if BAYER4[y & 3][x & 3] < 9:
                px[x, y] = T["sand_dk"]
        for (x, y) in ring2:
            if BAYER4[y & 3][x & 3] < 3:
                px[x, y] = T["sand_dk"]
    return t


# ---------------------------------------------------------------------------
# Tree family: seamless canopy carpet (period-16 wrap) with scallop-cut edge
# variants, hang fringes for 1-tile overhang, and trunk ground tiles.

# scallop depths, period 16, equal endpoints (adjacent tiles line up)
SCAL = (2, 3, 4, 5, 5, 4, 3, 2, 2, 3, 4, 5, 4, 3, 2, 2)
SDEEP = (5, 6, 7, 8, 8, 7, 6, 5, 5, 6, 7, 8, 7, 6, 5, 5)  # S cut: trunk reveal
HANG = (5, 6, 7, 7, 6, 5, 4, 4, 5, 6, 7, 7, 6, 5, 4, 5)  # hang lobe depth

_LOBES = ((4, 4, 6), (12, 11, 6))  # cx, cy, r — two crowns per tile


def _canopy_carpet():
    """Fully opaque, torus-tiling canopy mass: two treetop crowns per tile,
    each with a lit NW cap and a deep SE crevice — reads as clumped
    treetops when tiled, not noise."""
    t = tile_base(T["canopy_dk"])
    d = ImageDraw.Draw(t)
    px = t.load()
    offs = [(ox, oy) for ox in (-16, 0, 16) for oy in (-16, 0, 16)]
    # cool blue depth pooling between the crowns
    dither(px, 0, 0, 15, 15, T["canopy_dp"], 4, ox=2, oy=1, only=T["canopy_dk"])
    for (cx, cy, r) in _LOBES:
        for ox, oy in offs:
            d.ellipse([cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r], fill=T["canopy"])
    for (cx, cy, r) in _LOBES:
        for ox, oy in offs:
            x0, y0 = cx + ox, cy + oy
            # deep crevice hugging the SE rim of each crown
            d.arc([x0 - r, y0 - r, x0 + r, y0 + r], 15, 125, fill=T["canopy_dk"])
            d.arc([x0 - r + 1, y0 - r + 1, x0 + r + 1, y0 + r + 1], 25, 115, fill=OUTLINE)
            # lit NW cap, warm sun crown on top
            d.ellipse([x0 - r + 1, y0 - r + 1, x0 + 1, y0 + 1], fill=T["canopy_lt"])
            d.ellipse([x0 - r + 2, y0 - r + 2, x0 - r // 2, y0 - r // 2], fill=T["canopy_hi"])
            px[(x0 - r + 2) % 16, (y0 - r + 2) % 16] = T["grass_hi"]  # sun glint
            # leaf notches on the lit cap
            px[(x0 - r + 2) % 16, (y0 + 1) % 16] = T["canopy"]
            px[(x0 + 1) % 16, (y0 - r + 2) % 16] = T["canopy"]
    dither(px, 0, 0, 15, 15, T["canopy_lt"], 2, ox=1, oy=3, only=T["canopy"])
    return t


def _edge_pass(t):
    """OUTLINE the canopy where it meets transparency, shade just inside."""
    px = t.load()
    marks = []
    for y in range(16):
        for x in range(16):
            if px[x, y][3] == 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < 16 and 0 <= ny < 16 and px[nx, ny][3] == 0:
                    marks.append((x, y))
                    break
    for (x, y) in marks:
        px[x, y] = OUTLINE
    return t


def t_canopy(mask):
    t = _canopy_carpet()
    if mask == 0:
        return t
    px = t.load()
    clear = (0, 0, 0, 0)
    for i in range(16):
        if mask & N:
            for y in range(SCAL[i]):
                px[i, y] = clear
        if mask & S:
            for y in range(16 - SDEEP[(i + 8) % 16], 16):
                px[i, y] = clear
        if mask & W:
            for x in range(SCAL[(i + 4) % 16]):
                px[x, i] = clear
        if mask & E:
            for x in range(16 - SCAL[(i + 12) % 16], 16):
                px[x, i] = clear
    if mask & (N | W) == (N | W):
        for y in range(16):
            for x in range(16):
                if x + y <= 6:
                    px[x, y] = clear
    if mask & (N | E) == (N | E):
        for y in range(16):
            for x in range(16):
                if (15 - x) + y <= 6:
                    px[x, y] = clear
    if mask & (S | W) == (S | W):
        for y in range(16):
            for x in range(16):
                if x + (15 - y) <= 8:
                    px[x, y] = clear
    if mask & (S | E) == (S | E):
        for y in range(16):
            for x in range(16):
                if (15 - x) + (15 - y) <= 8:
                    px[x, y] = clear
    return _edge_pass(t)


def t_hang_s():
    """Tree to the SOUTH: canopy lobes overhang along this tile's bottom."""
    t = new_img()
    px = t.load()
    car = _canopy_carpet().load()
    for x in range(16):
        for y in range(16 - HANG[x], 16):
            px[x, y] = car[x, y]
    # detached leaf tufts above the fringe
    for (x, y) in ((3, 16 - HANG[3] - 2), (10, 16 - HANG[10] - 2), (14, 16 - HANG[14] - 3)):
        if 0 <= y:
            px[x, y] = T["canopy"]
    return _edge_pass(t)


def t_hang_w():
    """Tree to the WEST: lobes along this tile's left edge."""
    t = new_img()
    px = t.load()
    car = _canopy_carpet().load()
    for y in range(16):
        for x in range(HANG[(y + 4) % 16]):
            px[x, y] = car[x, y]
    for (x, y) in ((HANG[6] + 1, 2), (HANG[13] + 1, 9), (HANG[2] + 2, 14)):
        if x < 16:
            px[x, y] = T["canopy"]
    return _edge_pass(t)


def t_hang_e():
    """Tree to the EAST: lobes along this tile's right edge."""
    t = new_img()
    px = t.load()
    car = _canopy_carpet().load()
    for y in range(16):
        for x in range(16 - HANG[(y + 9) % 16], 16):
            px[x, y] = car[x, y]
    for (x, y) in ((15 - HANG[1] - 1, 3), (15 - HANG[8] - 1, 8), (15 - HANG[12] - 2, 13)):
        if x >= 0:
            px[x, y] = T["canopy"]
    return _edge_pass(t)


def _trunk(base_fn):
    """Ground tile under a tree: shaded base, trunk column with root flare.
    Top rows read as under-canopy darkness (they peek through canopy cuts)."""
    t = base_fn()
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 5, T["canopy_dk"], 12)
    dither(px, 0, 4, 15, 8, T["canopy_dk"], 6, ox=1)
    dither(px, 0, 0, 15, 3, T["void"], 6, ox=2)
    # trunk with lit west edge — runs the full tile so the canopy's deep
    # south cut always lands on bark, never on a grass gap
    d.rectangle([5, 0, 10, 15], fill=T["trunk"])
    d.line([(5, 0), (5, 15)], fill=T["trunk_lt"])
    d.line([(6, 0), (6, 14)], fill=T["trunk_lt"])
    px[6, 5] = T["trunk_hi"]  # warm catch-light flecks on the lit edge
    px[6, 10] = T["trunk_hi"]
    px[5, 7] = T["trunk_hi"]
    d.line([(10, 0), (10, 15)], fill=T["trunk_dk"])
    d.line([(4, 0), (4, 15)], fill=OUTLINE)
    d.line([(11, 0), (11, 15)], fill=OUTLINE)
    # bark striations: broken vertical grain lines down the shaded flank
    for gy in range(1, 15, 2):
        px[8, gy] = T["trunk_dk"]
    for gy in range(2, 15, 3):
        px[9, gy] = T["trunk_dk"]
        px[7, min(15, gy + 1)] = T["mud_dk"]
    # canopy darkness pooling on the upper bark
    dither(px, 5, 0, 10, 3, T["void"], 8, ox=1)
    # root flare
    d.polygon([(2, 15), (5, 11), (5, 15)], fill=T["trunk"])
    d.polygon([(13, 15), (10, 11), (10, 15)], fill=T["trunk"])
    px[3, 14] = T["trunk_lt"]
    px[4, 13] = T["trunk_hi"]
    px[12, 14] = T["trunk_dk"]
    px[2, 15] = OUTLINE
    px[13, 15] = OUTLINE
    # bark knots + moss
    px[8, 7] = T["mud_dk"]
    px[8, 8] = T["trunk_dk"]
    px[7, 11] = T["mud_dk"]
    px[9, 13] = T["grass_dk"]
    px[9, 12] = T["grass_dp"]
    px[6, 9] = T["trunk_lt"]
    # root contact shadow
    dither(px, 1, 15, 14, 15, T["void"], 8, ox=1)
    return t


def t_trunk_grass():
    return _trunk(lambda: grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 3, n_blades=3))


def t_trunk_dark():
    return _trunk(lambda: grass_tile(T["grass_dk"], T["grass"], T["canopy_dk"], 7, n_blades=3))


# ---------------------------------------------------------------------------
# Walls: FACE tiles (ground, collide — lit cap edge, shaded body, contact
# shadow) + TOP tiles (overhead caps, prop-free) + cap-lip strips.


def t_wall_face():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    # lit cap edge, warm sun on the crown
    d.rectangle([0, 0, 15, 1], fill=T["stone_lt"])
    dither(px, 0, 0, 15, 0, T["stone_hi"], 6, ox=1)
    dither(px, 0, 1, 15, 1, T["stone"], 5, ox=1)
    # three brick courses with deep mortar (must read at 1x)
    for row in range(3):
        y0 = 2 + row * 4
        d.line([(0, y0 + 3), (15, y0 + 3)], fill=T["void"])
        joints = (5, 11) if row % 2 == 0 else (2, 8, 14)
        for jx in joints:
            d.line([(jx, y0), (jx, y0 + 2)], fill=T["void"])
            if jx + 1 <= 15:
                px[jx + 1, y0 + 1] = T["stone_dp"]  # cool bounce in the joint
        prev = -1
        for jx in list(joints) + [16]:
            if jx - prev > 1:
                d.line([(prev + 1, y0), (jx - 1, y0)], fill=T["stone_lt"])
                px[prev + 1, y0] = T["stone_hi"]  # per-brick sun catch
            prev = jx
        dither(px, 0, y0 + 1, 15, y0 + 2, T["stone_dk"], 3 + row * 2, oy=row)
        dither(px, 0, y0 + 2, 15, y0 + 2, T["stone_dp"], 2 + row * 2, ox=row, only=T["stone_dk"])
    # base contact shadow (cool purple, not plain dark)
    d.rectangle([0, 14, 15, 15], fill=T["stone_dp"])
    dither(px, 0, 14, 15, 15, T["void"], 8, ox=1)
    d.line([(9, 6), (10, 7)], fill=T["stone_dk"])  # crack
    px[10, 8] = T["stone_dp"]
    px[3, 7] = T["grass_dk"]  # moss
    px[3, 8] = T["grass_dp"]
    px[12, 11] = T["grass_dk"]
    return t


def t_wall_top():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["stone_lt"], 6, ox=1)
    dither(px, 0, 0, 15, 15, T["stone_hi"], 2, ox=3, oy=1, only=T["stone_lt"])  # sun-bleached
    # walkway slabs seen from above
    d.line([(0, 5), (15, 5)], fill=T["stone_dk"])
    d.line([(0, 11), (15, 11)], fill=T["stone_dk"])
    for x in (4, 12):
        d.line([(x, 0), (x, 5)], fill=T["stone_dk"])
    for x in (8,):
        d.line([(x, 6), (x, 11)], fill=T["stone_dk"])
    for x in (3, 10):
        d.line([(x, 12), (x, 15)], fill=T["stone_dk"])
    # side rims: lit W, shaded E (cool)
    d.line([(0, 0), (0, 15)], fill=T["stone_hi"])
    d.line([(15, 0), (15, 15)], fill=T["stone_dp"])
    px[6, 3] = T["stone_dk"]  # chip
    px[7, 4] = T["stone_dp"]
    px[13, 8] = T["stone_hi"]
    px[2, 13] = T["stone_dp"]  # weather pit
    return t


def t_gate_face():
    """Gate pillar face flanking the road gap — jamb stones + ember lantern."""
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    d.rectangle([0, 0, 15, 1], fill=T["stone_lt"])
    dither(px, 0, 0, 15, 0, T["stone_hi"], 5, ox=2)
    dither(px, 0, 1, 15, 1, T["stone"], 5, ox=1)
    # heavy quoin blocks, alternating widths
    for row in range(3):
        y0 = 2 + row * 4
        d.line([(0, y0 + 3), (15, y0 + 3)], fill=T["void"])
        jx = 7 if row % 2 == 0 else 10
        d.line([(jx, y0), (jx, y0 + 2)], fill=T["void"])
        if jx + 1 <= 15:
            px[jx + 1, y0 + 1] = T["stone_dp"]
        d.line([(0, y0), (jx - 1, y0)], fill=T["stone_lt"])
        d.line([(jx + 1, y0), (15, y0)], fill=T["stone_lt"])
        px[1, y0] = T["stone_hi"]
        dither(px, 0, y0 + 1, 15, y0 + 2, T["stone_dk"], 4 + row, oy=row)
        dither(px, 0, y0 + 2, 15, y0 + 2, T["stone_dp"], 3 + row, ox=1, only=T["stone_dk"])
    # timber lintel remnant across the cap, warm-lit grain
    d.rectangle([1, 0, 14, 0], fill=T["trunk_lt"])
    px[3, 0] = T["trunk_hi"]
    px[9, 0] = T["trunk_hi"]
    px[12, 0] = T["trunk_dk"]
    # ember lantern bracket with warm spill on the stone
    px[12, 5] = T["trunk"]
    px[12, 6] = T["ember"]
    px[12, 7] = T["ember_lt"]
    px[12, 8] = T["ember_hi"]  # hottest sliver under the flame
    px[11, 7] = T["ember_dk"]
    px[13, 7] = T["ember_dp"]  # rust on the bracket arm
    d.rectangle([0, 14, 15, 15], fill=T["stone_dp"])
    dither(px, 0, 14, 15, 15, T["void"], 8, ox=1)
    return t


def t_ruin_face():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    # lit cap edge, weathered — warm sun catches on the surviving crown
    d.rectangle([0, 0, 15, 1], fill=T["stone_lt"])
    px[1, 0] = T["stone_hi"]
    px[8, 0] = T["stone_hi"]
    px[6, 1] = T["stone"]
    px[13, 0] = T["stone"]
    px[3, 1] = T["stone"]
    # two courses of heavy 6px blocks, deep void mortar
    for row in range(2):
        y0 = 2 + row * 6
        d.line([(0, y0 + 5), (15, y0 + 5)], fill=T["void"])
        dither(px, 0, y0 + 4, 15, y0 + 4, T["stone_dp"], 5, ox=row, only=T["stone"])
        d.line([(0, y0), (15, y0)], fill=T["stone_lt"])  # per-block lit top
        dither(px, 0, y0 + 3, 15, y0 + 4, T["stone_dk"], 7, oy=row)
        joints = (8,) if row == 0 else (4, 12)
        for jx in joints:
            d.line([(jx, y0), (jx, y0 + 4)], fill=T["void"])
            px[jx, y0] = T["void"]  # break the lit line at the joint
            if jx < 15:
                d.line([(jx + 1, y0 + 1), (jx + 1, y0 + 2)], fill=T["stone_lt"])
    d.line([(11, 4), (12, 7)], fill=T["void"])  # crack through the top course
    d.line([(12, 7), (11, 9)], fill=T["void"])
    px[12, 5] = T["stone_dp"]  # cool depth beside the crack
    px[2, 3] = T["stone_hi"]
    px[10, 9] = T["stone_dk"]
    px[5, 9] = T["grass_dk"]  # moss in the mortar
    px[6, 9] = T["grass_dk"]
    px[6, 10] = T["grass_dp"]
    px[14, 12] = T["grass_dk"]
    # base contact shadow (cool)
    d.rectangle([0, 14, 15, 15], fill=T["stone_dp"])
    dither(px, 0, 14, 15, 15, T["void"], 9, ox=1)
    px[3, 15] = T["grass_dk"]
    px[12, 15] = T["grass_dk"]
    return t


def t_ruin_top():
    """Sunlit broken wall crown — clearly LIGHTER than the ruin floor so a
    wall strip pops out of the courtyard it borders."""
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["stone_lt"], 8, ox=2)
    dither(px, 0, 0, 15, 15, T["stone_hi"], 3, ox=1, oy=2, only=T["stone_lt"])  # bleached crown
    dither(px, 0, 0, 15, 15, T["stone_dk"], 2, oy=1)
    # broken slab outlines
    d.line([(0, 6), (9, 6)], fill=T["stone_dk"])
    d.line([(9, 6), (12, 9)], fill=T["stone_dk"])
    d.line([(12, 9), (15, 9)], fill=T["stone_dk"])
    d.line([(5, 0), (5, 6)], fill=T["stone_dk"])
    d.line([(10, 10), (10, 15)], fill=T["stone_dk"])
    px[6, 5] = T["stone_dp"]  # cool pockets along the seams
    px[10, 12] = T["stone_dp"]
    # rubble chunks + overgrowth on the broken crown
    px[3, 3] = T["stone_hi"]
    px[12, 4] = T["stone_lt"]
    px[13, 5] = T["void"]
    px[7, 12] = T["stone_lt"]
    px[8, 5] = T["void"]
    px[2, 11] = T["grass_dk"]
    px[3, 11] = T["grass_dk"]
    px[3, 12] = T["grass_dp"]
    px[13, 13] = T["grass_dk"]
    # crisp side rims: lit W, deep E (wall strips read as raised slabs)
    d.line([(0, 0), (0, 15)], fill=T["stone_hi"])
    d.line([(15, 0), (15, 15)], fill=T["void"])
    d.line([(14, 0), (14, 15)], fill=T["stone_dp"])
    return t


def t_cliff_face():
    t = tile_base(T["stone_dk"])
    px = t.load()
    d = ImageDraw.Draw(t)
    # grass clinging to the cliff lip
    d.rectangle([0, 0, 15, 0], fill=T["grass_dk"])
    for x in (2, 7, 12):
        px[x, 0] = T["grass"]
        px[x, 1] = T["grass_dk"]
    # strata bands with cool depth between them
    for y0, col in ((2, T["stone"]), (6, T["stone_dk"]), (9, T["stone"]), (13, T["stone_dk"])):
        d.line([(0, y0), (15, y0)], fill=col)
    dither(px, 0, 2, 15, 7, T["stone"], 5, ox=1)
    dither(px, 0, 4, 15, 7, T["stone_dp"], 3, ox=2, only=T["stone_dk"])
    dither(px, 0, 8, 15, 13, T["void"], 4, oy=1)
    dither(px, 0, 10, 15, 13, T["stone_dp"], 4, ox=1, only=T["stone_dk"])
    # vertical cracks
    d.line([(4, 3), (4, 8)], fill=T["void"])
    d.line([(11, 6), (11, 12)], fill=T["void"])
    d.line([(5, 3), (5, 4)], fill=T["stone_lt"])
    px[3, 4] = T["stone_dp"]
    px[12, 8] = T["stone_dp"]
    px[8, 3] = T["stone_lt"]  # ledge glint
    d.rectangle([0, 14, 15, 15], fill=T["void"])
    dither(px, 0, 14, 15, 14, T["stone_dp"], 6)
    return t


def t_cliff_top():
    t = tile_base(T["stone"])
    px = t.load()
    d = ImageDraw.Draw(t)
    dither(px, 0, 0, 15, 15, T["stone_lt"], 5, ox=3)
    dither(px, 0, 0, 15, 15, T["stone_hi"], 2, ox=1, oy=3, only=T["stone_lt"])
    dither(px, 0, 0, 15, 15, T["stone_dk"], 2, oy=1)
    d.line([(2, 3), (7, 5)], fill=T["stone_dk"])  # fissures
    d.line([(9, 10), (14, 12)], fill=T["stone_dk"])
    px[8, 5] = T["void"]
    px[7, 6] = T["stone_dp"]
    px[13, 12] = T["void"]
    px[12, 13] = T["stone_dp"]
    px[3, 12] = T["grass_dk"]  # scrub tuft
    px[4, 12] = T["grass_dk"]
    px[4, 13] = T["grass_dp"]
    px[4, 11] = T["grass"]
    px[11, 3] = T["stone_hi"]  # sun-caught chip
    return t


def _lip(face_img):
    """Overhead strip: just the face's lit cap edge (rows 0-4, faded), so
    the hero's feet tuck behind a one-row wall when walking north of it."""
    t = new_img()
    px = t.load()
    fp = face_img.load()
    for y in range(5):
        for x in range(16):
            if y < 3 or BAYER4[y & 3][x & 3] < (8 if y == 3 else 3):
                px[x, y] = fp[x, y]
    return t


def t_lip_wall():
    return _lip(t_wall_face())


def t_lip_ruin():
    return _lip(t_ruin_face())


# ---------------------------------------------------------------------------
# Shadow-edge base variants: the cell south of a wall/tree keeps its terrain
# but carries a soft dithered shadow band along its top (baked shadows).


def _shadowed(base_img, shade, deep=None):
    t = base_img.copy()
    px = t.load()
    levels = (11, 8, 5, 2)
    for y, lv in enumerate(levels):
        for x in range(16):
            if BAYER4[y & 3][x & 3] < lv:
                px[x, y] = shade
    if deep is not None:
        for x in range(16):
            if BAYER4[0][x & 3] < 5:
                px[x, 0] = deep
    return t


def t_shadow_grass():
    # hue-shifted shadow: the band pulls cool teal, never plain dark green
    return _shadowed(t_grass_a(), T["grass_dk"], T["grass_dp"])


def t_shadow_dark():
    return _shadowed(t_dark_grass(), T["canopy_dp"], T["void"])


def t_shadow_mud():
    return _shadowed(t_mud(), T["mud_dp"], T["void"])


def t_shadow_ruin():
    return _shadowed(t_ruin_floor(), T["stone_dp"], T["void"])


def t_shadow_path():
    return _shadowed(t_path_full(), T["sand_dk"], T["mud_dp"])


# ---------------------------------------------------------------------------
# Layout assembly.

# Symbolic ids (single source of truth — gen_maps.py imports these).
GRASS_A, GRASS_B, DARK, EMBER = 0, 1, 2, 3
SIGN_G, SIGN_D, SIGN_R, DOOR = 4, 5, 6, 7
FLOWER, REED, RUBBLE = 8, 9, 10
ROCK_G, STUMP_G, BONES_D, ROCK_D, PEBBLES_R = 11, 12, 13, 14, 15
PATH0, WATER0, MUD0, CANOPY0 = 16, 32, 48, 64
MARSH0 = 80
TRUNK_G, TRUNK_D, HANG_S, HANG_W = 92, 93, 94, 95
RUIN0 = 96
HANG_E, SH_GRASS, SH_DARK, SH_MUD = 108, 109, 110, 111
WALL_FACE, WALL_TOP, GATE_FACE = 112, 113, 114
RUIN_FACE, RUIN_TOP, CLIFF_FACE, CLIFF_TOP = 115, 116, 117, 118
LIP_WALL, LIP_RUIN, SH_RUIN, SH_PATH = 119, 120, 121, 122
GRASS_C = 123  # feathered dark patch (isolated dark cells in grass rooms)


def path_id(mask):
    return PATH0 + mask


def water_id(mask):
    return WATER0 + mask


def mud_id(mask):
    return MUD0 + mask


def canopy_id(mask):
    return CANOPY0 + mask


def marsh_id(mask):
    return MARSH0 + minimal_slot(mask)


def ruin_id(mask):
    return RUIN0 + minimal_slot(mask)


def build_tiles():
    """id -> RGBA tile image for every non-empty slot."""
    tiles = {
        GRASS_A: t_grass_a(),
        GRASS_B: t_grass_b(),
        GRASS_C: t_grass_c(),
        DARK: t_dark_grass(),
        EMBER: t_ember_glow(0),
        SIGN_G: t_sign(lambda: grass_tile(T["grass"], T["grass_lt"], T["grass_dk"], 7, n_blades=3)),
        SIGN_D: t_sign(lambda: grass_tile(T["grass_dk"], T["grass"], T["canopy_dk"], 9, n_blades=3)),
        SIGN_R: t_sign(t_ruin_floor),
        DOOR: t_ruin_door(),
        FLOWER: t_flower(),
        REED: t_reed(),
        RUBBLE: t_rubble(),
        ROCK_G: t_rock_grass(),
        STUMP_G: t_stump(),
        BONES_D: t_bones_dark(),
        ROCK_D: t_rock_dark(),
        PEBBLES_R: t_pebbles_ruin(),
        TRUNK_G: t_trunk_grass(),
        TRUNK_D: t_trunk_dark(),
        HANG_S: t_hang_s(),
        HANG_W: t_hang_w(),
        HANG_E: t_hang_e(),
        SH_GRASS: t_shadow_grass(),
        SH_DARK: t_shadow_dark(),
        SH_MUD: t_shadow_mud(),
        SH_RUIN: t_shadow_ruin(),
        SH_PATH: t_shadow_path(),
        WALL_FACE: t_wall_face(),
        WALL_TOP: t_wall_top(),
        GATE_FACE: t_gate_face(),
        RUIN_FACE: t_ruin_face(),
        RUIN_TOP: t_ruin_top(),
        CLIFF_FACE: t_cliff_face(),
        CLIFF_TOP: t_cliff_top(),
        LIP_WALL: t_lip_wall(),
        LIP_RUIN: t_lip_ruin(),
    }
    grass = t_grass_a()
    mud = t_mud()
    dark = t_dark_grass()
    path = t_path_full()
    water = t_water_full(0)
    marsh = t_marsh_full(0)
    ruinf = t_ruin_floor()
    for mask in range(16):
        tiles[PATH0 + mask] = transition(path, grass, mask, "path")
        tiles[WATER0 + mask] = transition(water, grass, mask, "water")
        tiles[MUD0 + mask] = transition(mud, dark, mask, "mud")
        tiles[CANOPY0 + mask] = t_canopy(mask)
    for slot, mask in enumerate(MINIMAL_MASKS):
        tiles[MARSH0 + slot] = transition(marsh, mud, mask, "marsh")
        tiles[RUIN0 + slot] = transition(ruinf, dark, mask, "ruin")
    return tiles


def build_sheet():
    img = new_img(SHEET_W, SHEET_H)
    for tid, tile in build_tiles().items():
        img.paste(tile, ((tid % COLUMNS) * 16, (tid // COLUMNS) * 16))
    return img


# ---------------------------------------------------------------------------
# Tile properties — THE engine contract. collide: bool on solids; anim:
# string on every tile whose cell gets a shimmer overlay. The overlay pair's
# frame 0 is pixel-identical to the base tile, so only the full interior
# water/marsh tiles (and the ember tile) carry anim.


def build_props():
    props = {}
    for mask in range(16):
        props[WATER0 + mask] = {"collide": True}
    for slot in range(len(MINIMAL_MASKS)):
        props[MARSH0 + slot] = {"collide": True}
    for tid in (TRUNK_G, TRUNK_D, WALL_FACE, GATE_FACE, RUIN_FACE, CLIFF_FACE):
        props[tid] = {"collide": True}
    props[WATER0]["anim"] = "water"
    props[MARSH0]["anim"] = "marshwater"
    props[EMBER] = {"anim": "ember"}
    return props


def collide_ids():
    return {tid for tid, p in build_props().items() if p.get("collide")}


def anim_ids():
    return {tid: p["anim"] for tid, p in build_props().items() if "anim" in p}
