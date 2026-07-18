"""Deterministic parallax battle backdrops — Assets lane (M11 "Modern 2D").

Each biome ships as a PARALLAX PAIR plus two shared overlay strips:

  backdrops/<biome>-far.png   256x144  complete scene — painterly quantized
      sky gradient (multi-stop LUT, Bayer-blended), celestial glow, far/mid
      silhouette layers with rim-lit edges, ground band + enemy platform.
      The legacy `backdrop.<biome>` manifest key ALIASES this file, so the
      engine can move to layered rendering without a landing race.
  backdrops/<biome>-near.png  256x64   near parallax band on transparency
      (top rows fully clear): close silhouettes hugging the frame edges +
      a foreground fringe along the bottom. Horizontally SEAMLESS
      (period-256 arithmetic), so the engine may drift/tile it +-4px.
  fx-shafts.png               256x144  soft diagonal god-ray streaks on
      transparency — screen-blend-ready (quantized warm-white alphas),
      x-seamless for slow drift.
  fx-fog.png                  256x64   soft fog band, transparent top,
      alpha-quantized pale cyan, x-seamless.

Budgets (GDD row 11 / ART_BIBLE §2): <= 96 unique colors per backdrop
file; overlays are alpha-quantized far under the cap. Modern-pixel
signatures throughout: hue-shifted shadows (cool blue/purple depths, warm
lights), painterly multi-step gradients, silhouette rim light. No
randomness — every placement is arithmetic, so re-runs are byte-identical.

Battle scene contract unchanged: horizon ~y=96, enemies stand on the
platform ellipse centered (128, 122).
"""

from PIL import Image, ImageDraw

W, H = 256, 144
NEAR_H = 64
HORIZON = 96
PLAT = (128, 122, 92, 15)  # cx, cy, rx, ry

BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _new(w=W, h=H, bg=(0, 0, 0, 255)):
    return Image.new("RGBA", (w, h), bg)


def _lerp(a, b, t):
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
        255,
    )


def _lut(stops, n):
    """n-color LUT interpolated along evenly spaced gradient stops."""
    out = []
    for i in range(n):
        f = i / (n - 1) * (len(stops) - 1)
        z = min(len(stops) - 2, int(f))
        out.append(_lerp(stops[z], stops[z + 1], f - z))
    return out


def _grad(px, stops, y0, y1, levels=14, x0=0, x1=W - 1):
    """Painterly vertical gradient: quantized LUT with Bayer blending
    between adjacent levels — smooth at 1x, still crisp pixel art."""
    lut = _lut(stops, levels)
    span = y1 - y0
    for y in range(y0, y1):
        f = (y - y0) / span * (levels - 1)
        z = min(levels - 2, int(f))
        lvl = int((f - z) * 16)
        row = BAYER4[y & 3]
        for x in range(x0, x1 + 1):
            px[x, y] = lut[z + 1] if row[x & 3] < lvl else lut[z]


def _glow(px, cx, cy, r, lut, h=H, squash=1.0):
    """Radial glow: quantized rings, Bayer-dithered between levels; the
    outermost ring dithers onto the existing sky instead of replacing it."""
    n = len(lut)
    for y in range(max(0, cy - r), min(h, cy + r + 1)):
        for x in range(max(0, int(cx - r / squash)), min(W, int(cx + r / squash) + 1)):
            dd = ((x - cx) * squash) ** 2 + (y - cy) ** 2
            if dd >= r * r:
                continue
            f = (dd ** 0.5) / r * n
            z = int(f)
            t = int((f - z) * 16)
            if z >= n - 1:
                if BAYER4[y & 3][x & 3] < 16 - t:  # fade the last ring out
                    px[x, y] = lut[n - 1]
            else:
                px[x, y] = lut[z + 1] if BAYER4[y & 3][x & 3] < t else lut[z]


def _tri(x, period, amp):
    """Integer triangle wave, period must divide 256 for x-seamlessness."""
    p = x % period
    half = period // 2
    return (p if p < half else period - p) * amp // half


def _ground(d, px, stops, plat, plat_lt, plat_hi, rim, levels=8):
    """Ground band with a depth gradient + the rim-lit enemy platform."""
    _grad(px, stops, HORIZON, H, levels=levels)
    cx, cy, rx, ry = PLAT
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=rim)
    d.ellipse([cx - rx + 2, cy - ry + 1, cx + rx - 2, cy + ry - 2], fill=plat)
    for y in range(cy - ry + 1, cy + 2):
        for x in range(cx - rx + 4, cx + rx - 4):
            dd = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if dd < 0.62 and BAYER4[y & 3][x & 3] < 7:
                px[x, y] = plat_lt
            elif dd < 0.3 and BAYER4[y & 3][(x + 2) & 3] < 5:
                px[x, y] = plat_hi
    # rim catch-light along the platform's upper-left arc
    for x in range(cx - rx + 6, cx - 8, 3):
        yy = cy - ry + 1 + (x - (cx - rx)) % 2
        px[x, yy] = plat_hi


def _conifer(d, x, base_y, h, w, color):
    for k in range(3):
        ty = base_y - h + k * (h // 4)
        hw = w * (k + 2) // 5
        d.polygon(
            [(x, ty), (x - hw, base_y - (2 - k) * (h // 5)), (x + hw, base_y - (2 - k) * (h // 5))],
            fill=color,
        )
    d.rectangle([x - 1, base_y - h // 5, x + 1, base_y], fill=color)


def _roundtree(d, x, base_y, r, color):
    d.rectangle([x - 1, base_y - r, x + 1, base_y], fill=color)
    d.ellipse([x - r, base_y - 2 * r - 2, x + r, base_y - r + 2], fill=color)
    d.ellipse([x - r + 2, base_y - 2 * r - 6, x + r - 4, base_y - r - 4], fill=color)


def _rim_edge(px, color, side=-1, w=W, h=H, on_alpha=True):
    """1px rim light on silhouette edges facing the light (side=-1 left)."""
    hits = []
    for y in range(h):
        for x in range(1, w - 1):
            c = px[x, y]
            n = px[x + side, y]
            if c[3] == 255 and (n[3] == 0 if on_alpha else n != c):
                hits.append((x, y))
    for (x, y) in hits:
        if BAYER4[y & 3][x & 3] < 11:
            px[x, y] = color
    return hits


# ---------------------------------------------------------------------------
# FOREST — golden dusk light breaking through a deep green wood.


def forest_far():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    _grad(px, [
        (22, 26, 56, 255),    # cool indigo zenith
        (28, 56, 72, 255),    # dusk teal
        (44, 96, 82, 255),    # sea green
        (108, 138, 78, 255),  # warm moss gold
        (196, 178, 108, 255), # pale gold at the treeline
    ], 0, HORIZON, levels=16)
    # first dusk stars in the indigo zenith
    for k, (sx, sy) in enumerate(((58, 7), (150, 12), (204, 5), (120, 3))):
        px[sx, sy] = (150, 160, 190, 255) if k % 2 else (190, 198, 218, 255)
    # low sun burning through the haze
    _glow(px, 86, 82, 34, [
        (248, 234, 168, 255), (236, 208, 128, 255),
        (210, 180, 106, 255), (168, 152, 92, 255),
    ])
    # far canopy line: soft misted bumps
    far = (52, 88, 84, 255)
    for k in range(16):
        x = k * 17 + (k * 7) % 11
        r = 7 + (k * 5) % 5
        d.ellipse([x - r, 82 - r - (k * 3) % 6, x + r, 96], fill=far)
    d.rectangle([0, 88, W - 1, HORIZON - 1], fill=far)
    # mid conifers, cool blue-green with a sunlit left rim
    mid = (30, 56, 58, 255)
    mid_rim = (86, 118, 88, 255)
    for k in range(9):
        x = 14 + k * 30 + (k * 13) % 9
        hgt = 34 + (k * 11) % 14
        _conifer(d, x, HORIZON, hgt, 9 + (k * 3) % 4, mid)
        d.line([(x - 1, HORIZON - hgt + 4), (x - 5, HORIZON - hgt // 3)], fill=mid_rim)
    # near-far heavy silhouettes hugging the frame edges
    near = (12, 26, 32, 255)
    for x, r in ((6, 16), (30, 12), (226, 13), (250, 17)):
        _roundtree(d, x, HORIZON + 2, r, near)
    _conifer(d, 18, HORIZON + 2, 52, 13, near)
    _conifer(d, 240, HORIZON + 2, 56, 14, near)
    # canopy overhang framing the top corners, warm speckles sunward
    for cxx, r in ((-6, 30), (18, 20), (238, 22), (262, 32)):
        d.ellipse([cxx - r, -r - 8, cxx + r, r - 14], fill=near)
    for k in range(9):
        lx = (k * 31 + 5) % 250
        if 40 < lx < 216:
            continue
        px[lx, 16 + (k * 7) % 8] = near
    for k in range(5):
        sx = 30 + k * 9
        sy = 6 + (k * 5) % 10
        if px[sx, sy] == near:
            px[sx, sy] = (150, 150, 96, 255)  # sun through the leaves
    _ground(d, px, [
        (66, 100, 58, 255), (44, 72, 48, 255), (26, 44, 42, 255),
    ], (52, 88, 52, 255), (74, 112, 62, 255), (104, 140, 76, 255), (16, 28, 26, 255))
    # grass flicks + tiny dew catches on the ground band
    for k in range(14):
        x = (k * 19 + 7) % 250 + 3
        y = 100 + (k * 13) % 38
        if abs(x - 128) > 96 or abs(y - 122) > 16:
            px[x, y] = (20, 36, 34, 255)
            px[x, y - 1] = (74, 112, 62, 255)
            if k % 3 == 0:
                px[x + 1, y - 2] = (150, 170, 96, 255)
    return img


def forest_near():
    img = _new(W, NEAR_H, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    px = img.load()
    trunk = (8, 20, 24, 255)
    moss = (34, 62, 48, 255)
    leaf = (16, 36, 36, 255)
    # heavy underbrush mounds at both frame edges (tops stay below the
    # transparent seam rows so the band melts into the far layer)
    d.polygon([(0, 63), (0, 16), (10, 12), (20, 22), (26, 40), (30, 63)], fill=trunk)
    d.polygon([(255, 63), (255, 18), (246, 13), (236, 24), (230, 44), (226, 63)], fill=trunk)
    # bark grain: faint interior striations so the mounds aren't flat cutouts
    bark = (14, 30, 33, 255)
    for gy in range(18, 62, 4):
        px[6 + (gy // 4) % 3, gy] = bark
        px[246 + (gy // 4) % 3, gy] = bark
    # root flares
    d.polygon([(6, 63), (14, 44), (26, 63)], fill=trunk)
    d.polygon([(230, 63), (242, 46), (250, 63)], fill=trunk)
    # leaning sapling silhouettes rising out of the mounds
    d.line([(14, 14), (22, 34)], fill=trunk, width=2)
    d.ellipse([8, 10, 24, 20], fill=leaf)
    d.line([(242, 16), (232, 36)], fill=trunk, width=2)
    d.ellipse([232, 12, 248, 22], fill=leaf)
    # fern cluster at the left root
    for k in range(4):
        fx = 24 + k * 4
        d.line([(fx, 62), (fx + 2, 50 + (k * 3) % 6)], fill=leaf)
    # foreground grass fringe along the bottom edge (x-seamless profile)
    for x in range(W):
        hgt = 3 + _tri(x, 32, 4) + _tri(x + 9, 64, 3)
        for y in range(NEAR_H - hgt, NEAR_H):
            px[x, y] = leaf if (x + y) % 5 else trunk
        if x % 7 == 3:  # taller blade pairs
            for y in range(NEAR_H - hgt - 4, NEAR_H - hgt):
                px[x, y] = leaf
    # mossy rim light where trunks face the scene's warm center
    _rim_edge(px, moss, side=1, h=NEAR_H)
    _rim_edge(px, moss, side=-1, h=NEAR_H)
    return img


# ---------------------------------------------------------------------------
# MARSH — drowned pale morning, fog on still water.


def marsh_far():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    _grad(px, [
        (38, 46, 68, 255),    # grey indigo
        (52, 80, 90, 255),
        (88, 126, 118, 255),
        (142, 168, 138, 255), # pale sage horizon
    ], 0, HORIZON, levels=14)
    # diffuse cold sun behind the murk
    _glow(px, 176, 34, 26, [
        (214, 224, 198, 255), (178, 196, 168, 255), (140, 166, 140, 255),
    ])
    # drifting fog bands (x-seamless triangle drift)
    fog_lt = (150, 178, 166, 255)
    fog = (104, 138, 128, 255)
    for band, (y0, hgt, lvl) in enumerate(((50, 5, 7), (64, 4, 10), (76, 6, 6), (87, 4, 9))):
        for y in range(y0, y0 + hgt):
            for x in range(W):
                if BAYER4[(y + band) & 3][(x + band * 2) & 3] < lvl:
                    px[x, y] = fog_lt if band % 2 else fog
    # far reed line: irregular clumps
    reed_far = (54, 82, 80, 255)
    for k in range(42):
        if k % 5 == 2 or k % 11 == 7:
            continue
        x = (k * 6 + (k * 13) % 7) % 256
        top = 78 + (k * 7) % 13
        d.line([(x, top), (x, HORIZON)], fill=reed_far)
        if k % 3 == 0:
            d.rectangle([x, top, x, top + 2], fill=reed_far)
        if k % 4 == 1:
            px[min(255, x + 1), top] = reed_far
    # wisp-glows hanging in the fog (lights that are not stars)
    for gx, gy, r in ((58, 62, 8), (132, 48, 6), (198, 70, 8), (98, 82, 6)):
        _glow(px, gx, gy, r, [
            (196, 232, 210, 255), (150, 196, 178, 255), (110, 152, 140, 255),
        ])
    # near reeds: clumps at both frame edges, cool with pale lit tips
    reed_near = (22, 36, 40, 255)
    tip = (86, 118, 104, 255)
    for k in range(14):
        side = 0 if k < 7 else 1
        bx = (8 + k * 6) if side == 0 else (208 + (k - 7) * 7)
        top = 58 + (k * 9) % 22
        d.line([(bx, top), (bx + (k % 3) - 1, HORIZON + 4)], fill=reed_near, width=2)
        d.rectangle([bx - 1, top, bx + 1, top + 4], fill=reed_near)
        px[bx, top] = tip
    _ground(d, px, [
        (64, 96, 96, 255), (38, 62, 66, 255), (20, 36, 44, 255),
    ], (58, 74, 50, 255), (78, 96, 60, 255), (108, 126, 74, 255), (16, 28, 32, 255))
    # still-water ripples + sky reflections around the islet
    for k, (rx0, ry) in enumerate(((10, 106), (150, 103), (30, 136), (180, 139), (90, 140))):
        d.line([(rx0, ry), (rx0 + 24 + (k * 5) % 10, ry)], fill=(96, 130, 124, 255))
        px[rx0 + 6 + k, ry - 1] = (142, 168, 150, 255)
    return img


def marsh_near():
    img = _new(W, NEAR_H, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    px = img.load()
    reed = (10, 22, 26, 255)
    reed_lt = (38, 66, 62, 255)
    water = (18, 34, 40, 255)
    # reed thickets at both edges (tips crest below the transparent seam)
    for k in range(9):
        bx = 2 + k * 4
        top = 10 + (k * 7) % 14
        d.line([(bx, NEAR_H), (bx + (k % 3) - 1, top)], fill=reed, width=2)
        d.rectangle([bx - 1, top, bx, top + 4], fill=reed)
    for k in range(9):
        bx = 222 + k * 4
        top = 12 + (k * 11) % 16
        d.line([(bx, NEAR_H), (bx + (k % 3) - 1, top)], fill=reed, width=2)
        d.rectangle([bx - 1, top, bx, top + 3], fill=reed)
    # a bent reed arcing into frame
    d.arc([18, 10, 70, 48], 200, 300, fill=reed)
    d.arc([190, 14, 240, 52], 240, 340, fill=reed)
    # waterline fringe: dark still water with pale gleam streaks (seamless)
    for x in range(W):
        hgt = 4 + _tri(x, 64, 3) + _tri(x + 21, 32, 2)
        for y in range(NEAR_H - hgt, NEAR_H):
            px[x, y] = water
    for k in range(8):
        gx = (k * 37 + 11) % 240
        gy = NEAR_H - 3 - (k % 3)
        d.line([(gx, gy), (gx + 8 + (k * 3) % 6, gy)], fill=(60, 96, 96, 255))
        px[gx + 2, gy] = (110, 150, 140, 255)
    # sparse short reeds poking through the front water
    for k in range(6):
        bx = 48 + k * 32
        d.line([(bx, NEAR_H), (bx, NEAR_H - 9 - (k * 5) % 5)], fill=reed)
        px[bx, NEAR_H - 10 - (k * 5) % 5] = reed_lt
    _rim_edge(px, reed_lt, side=-1, h=NEAR_H)
    return img


# ---------------------------------------------------------------------------
# RUIN — cold moonlit night over broken stone.


def ruin_far():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    _grad(px, [
        (10, 12, 30, 255),
        (24, 30, 54, 255),
        (44, 54, 84, 255),
        (74, 88, 112, 255),  # horizon glow
    ], 0, HORIZON, levels=14)
    # stars (upper sky only, away from the moon)
    for k in range(12):
        sx = (k * 47 + 13) % 250
        sy = (k * 23 + 5) % 40
        if abs(sx - 202) > 34 or sy > 34:
            px[sx, sy] = (168, 178, 208, 255) if k % 3 else (210, 216, 236, 255)
    # cold moon: layered halo glow behind a crisp disc
    _glow(px, 202, 26, 24, [
        (150, 160, 190, 255), (112, 124, 158, 255),
        (76, 88, 122, 255), (44, 54, 86, 255),
    ])
    d.ellipse([193, 17, 211, 35], fill=(226, 230, 240, 255))
    d.arc([193, 17, 211, 35], 30, 200, fill=(196, 202, 224, 255))  # limb shading
    d.ellipse([197, 21, 202, 26], fill=(196, 202, 224, 255))  # maria
    d.ellipse([204, 28, 207, 31], fill=(174, 182, 208, 255))
    px[206, 22] = (196, 202, 224, 255)
    # far broken wall: crenellated skyline, moonlit caps
    farwall = (32, 38, 60, 255)
    cap = (88, 100, 128, 255)
    top = 62
    d.rectangle([0, top, W - 1, HORIZON - 1], fill=farwall)
    for k in range(16):
        x = k * 16
        if k % 3 != 1:
            ty = top - 6 - (k * 5) % 7
            d.rectangle([x, ty, x + 9, top], fill=farwall)
            d.line([(x, ty), (x + 9, ty)], fill=cap)
    d.line([(0, top), (149, top)], fill=cap)
    # breach: collapsed wall stretch, rubble slope spilling down
    d.polygon(
        [(150, HORIZON), (150, top + 2), (158, 74), (166, top + 6), (176, 80),
         (186, top + 4), (196, 76), (196, HORIZON)],
        fill=(16, 18, 36, 255),
    )
    d.polygon([(154, HORIZON), (172, 88), (192, HORIZON)], fill=(26, 30, 48, 255))
    # mid layer: broken fluted columns, moonlit on the right (moon side)
    col = (48, 56, 82, 255)
    col_lt = (110, 120, 148, 255)
    col_dk = (24, 28, 46, 255)
    for k, (x, hgt, broke) in enumerate(((22, 58, 10), (66, 44, 22), (120, 66, 4), (176, 38, 26), (228, 54, 14))):
        w2 = 7
        topy = HORIZON - hgt
        d.rectangle([x - w2, topy, x + w2, HORIZON], fill=col)
        d.line([(x - w2, topy), (x - w2, HORIZON)], fill=col_dk)
        d.line([(x + w2, topy), (x + w2, HORIZON)], fill=col_lt)
        for fx in (x - 3, x + 1):
            d.line([(fx, topy + 2), (fx, HORIZON)], fill=col_dk)
        d.polygon(
            [(x - w2, topy), (x - w2 + 4, topy - 5 - broke % 5), (x, topy - 2),
             (x + w2 - 3, topy - 6), (x + w2, topy)],
            fill=col,
        )
        px[x + w2 - 3, topy - 5] = col_lt  # moon catch on the break
        if k % 2 == 0:
            d.rectangle([x - w2 - 2, topy + 4, x + w2 + 2, topy + 7], fill=col_lt)
            d.line([(x - w2 - 2, topy + 7), (x + w2 + 2, topy + 7)], fill=col_dk)
    _ground(d, px, [
        (58, 64, 92, 255), (40, 44, 68, 255), (22, 26, 44, 255),
    ], (62, 68, 94, 255), (82, 90, 114, 255), (108, 116, 138, 255), (18, 22, 38, 255))
    # flagstone seams + cracks across the platform floor
    for (x0, y0, x1, y1) in ((60, 128, 90, 126), (150, 118, 186, 121), (108, 134, 140, 133)):
        d.line([(x0, y0), (x1, y1)], fill=(30, 34, 52, 255))
    d.line([(128, 112), (140, 118)], fill=(20, 24, 40, 255))
    d.line([(140, 118), (134, 126)], fill=(20, 24, 40, 255))
    # fallen column drum, half sunk, moonlit crown
    d.ellipse([28, 116, 58, 128], fill=col_dk)
    d.ellipse([28, 114, 58, 126], fill=col)
    d.arc([28, 114, 58, 126], 200, 340, fill=col_lt)
    return img


def ruin_near():
    img = _new(W, NEAR_H, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    px = img.load()
    stone = (12, 14, 32, 255)
    lit = (54, 62, 92, 255)
    # broken column stump at the left edge, jagged crown below the seam
    d.polygon([(0, 63), (0, 14), (6, 10), (12, 16), (17, 11), (20, 18), (20, 63)], fill=stone)
    d.polygon([(20, 20), (30, 24), (24, 34), (20, 30)], fill=stone)
    for fx in (6, 12, 18):
        d.line([(fx, 20), (fx, 60)], fill=(20, 24, 44, 255))
    # toppled block pile at the right edge
    d.polygon([(255, 16), (236, 26), (240, 42), (255, 38)], fill=stone)
    d.polygon([(255, 36), (228, 48), (232, 63), (255, 63)], fill=stone)
    d.line([(236, 26), (240, 42)], fill=lit)
    # rubble fringe along the bottom (x-seamless)
    for x in range(W):
        hgt = 2 + _tri(x, 64, 4) + _tri(x + 13, 32, 2)
        for y in range(NEAR_H - hgt, NEAR_H):
            px[x, y] = stone
    # scattered flagstone shards catching moonlight
    for k in range(7):
        gx = (k * 41 + 9) % 236 + 4
        gy = NEAR_H - 4 - (k * 3) % 5
        d.line([(gx, gy), (gx + 4, gy)], fill=(30, 34, 58, 255))
        px[gx + 1, gy - 1] = lit
    _rim_edge(px, lit, side=1, h=NEAR_H)
    return img


# ---------------------------------------------------------------------------
# LAIR — the Emberheart's cavern: black rock over rising heat.


def lair_far():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    _grad(px, [
        (5, 4, 10, 255), (12, 8, 18, 255), (24, 13, 24, 255),
    ], 0, 64, levels=8)
    _grad(px, [
        (24, 13, 24, 255), (56, 24, 20, 255), (108, 46, 22, 255), (150, 66, 24, 255),
    ], 64, HORIZON, levels=12)
    # stalactites: rock mass distinct from the ceiling gloom, warm underlight
    rock = (26, 14, 22, 255)
    rock_lit = (62, 28, 22, 255)
    for k in range(11):
        x = 4 + k * 24 + (k * 7) % 10
        ln = 14 + (k * 13) % 22
        w2 = 4 + (k * 3) % 3
        d.polygon([(x - w2, 0), (x + w2, 0), (x, ln)], fill=rock)
        d.line([(x - w2 + 1, 0), (x - 1, ln - 4)], fill=(14, 8, 16, 255))  # cool core shadow
        d.line([(x + w2 - 1, 1), (x, ln - 1)], fill=rock_lit)
        px[x, ln - 1] = (110, 50, 26, 255)  # heat catch at the tip
    # back-wall rock teeth rising into the glow, two interleaved depths
    for k in range(9):
        x = k * 30 + (k * 11) % 14
        hgt = 20 + (k * 9) % 16
        d.polygon([(x - 12, HORIZON), (x + 2, HORIZON - hgt), (x + 16, HORIZON)], fill=rock)
        d.line([(x + 2, HORIZON - hgt), (x + 9, HORIZON - hgt // 2)], fill=(60, 26, 22, 255))
    for k in range(8):
        x = 15 + k * 32 + (k * 7) % 11
        hgt = 9 + (k * 5) % 8
        d.polygon([(x - 7, HORIZON), (x, HORIZON - hgt), (x + 8, HORIZON)], fill=(30, 16, 22, 255))
    # ember rain: drifting sparks with short tails
    ember = (216, 110, 36, 255)
    ember_lt = (246, 184, 76, 255)
    ember_wh = (255, 236, 190, 255)
    for k in range(38):
        x = (k * 53 + 17) % 254 + 1
        y = (k * 89 + 29) % 116 + 6
        px[x, y] = (ember, ember_lt, ember_wh)[k % 3]
        px[x, y - 1] = ember if k % 3 else (120, 52, 24, 255)
        if k % 4 == 0:
            px[x, y - 2] = (86, 36, 22, 255)
    _ground(d, px, [
        (156, 70, 26, 255), (96, 40, 22, 255), (44, 20, 20, 255),
    ], (52, 24, 22, 255), (78, 34, 22, 255), (120, 54, 26, 255), (196, 96, 32, 255))
    # molten cracks webbing out from under the platform
    cx, cy = 128, 122
    for (x0, y0, x1, y1) in (
        (cx - 88, cy + 2, cx - 108, cy + 10), (cx + 86, cy - 2, cx + 110, cy + 4),
        (cx - 40, cy + 14, cx - 60, cy + 20), (cx + 44, cy + 13, cx + 70, cy + 19),
        (cx - 10, cy + 15, cx + 4, cy + 21),
    ):
        d.line([(x0, y0), (x1, y1)], fill=ember)
        px[max(0, min(255, x1)), max(0, min(143, y1))] = ember_lt
        px[max(0, min(255, x0)), max(0, min(143, y0))] = (255, 220, 150, 255)
    # heat shimmer just above the horizon
    for y in range(HORIZON - 8, HORIZON):
        for x in range(W):
            if BAYER4[y & 3][(x + 1) & 3] < (y - (HORIZON - 10)):
                r, g, b, a = px[x, y]
                if r > 90 and g < 80:
                    px[x, y] = (178, 84, 28, 255)
    return img


def lair_near():
    img = _new(W, NEAR_H, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    px = img.load()
    rock = (10, 6, 12, 255)
    under = (110, 46, 22, 255)
    hot = (226, 130, 44, 255)
    # stalagmite clusters at both edges (tips below the transparent seam)
    for k, (x, hgt, w2) in enumerate(((6, 50, 10), (20, 34, 7), (244, 52, 11), (230, 30, 6))):
        d.polygon([(x - w2, NEAR_H), (x, NEAR_H - hgt), (x + w2, NEAR_H)], fill=rock)
        d.line([(x, NEAR_H - hgt + 2), (x + w2 - 2, NEAR_H - 4)], fill=under)
        px[x, NEAR_H - hgt] = under
    # low rock teeth along the bottom (x-seamless profile)
    for x in range(W):
        hgt = 3 + _tri(x, 32, 5) + _tri(x + 11, 64, 3)
        for y in range(NEAR_H - hgt, NEAR_H):
            px[x, y] = rock
    # molten glow seeping between the front teeth
    for k in range(9):
        gx = (k * 29 + 13) % 250
        gy = NEAR_H - 2 - _tri(gx, 32, 2)
        px[gx, gy] = hot
        px[min(255, gx + 1), gy] = under
        if k % 3 == 0:
            px[gx, gy - 1] = (255, 210, 130, 255)
    # rising spark motes just above the fringe
    for k in range(7):
        sx = (k * 37 + 19) % 250
        sy = NEAR_H - 16 - (k * 11) % 18
        px[sx, sy] = (hot if k % 2 else (255, 210, 130, 255))
    _rim_edge(px, under, side=1, h=NEAR_H)
    return img


# ---------------------------------------------------------------------------
# Overlay strips — screen-blend-ready, alpha-quantized, x-seamless.

SHAFT_CORE = (255, 246, 220)
SHAFT_SOFT = (255, 224, 164)
FOG_HI = (214, 232, 236)
FOG_LO = (168, 196, 210)


def fx_shafts():
    """Diagonal god-ray streaks: bands live in sheared space u = x - y//2 so
    the rays lean down-right; u wraps mod 256, keeping the strip x-seamless
    for slow drift. Intensity fades with depth, dissolves at the ray edges,
    and is quantized to a small set of (hue, alpha) pairs so the overlay
    stays screen-blend-soft and far under the color cap."""
    img = _new(W, H, (0, 0, 0, 0))
    px = img.load()
    # (center u, half-width, strength 0..16) — u positions are arithmetic
    bands = ((12, 15, 16), (60, 8, 10), (105, 20, 14), (168, 10, 11), (214, 16, 13))
    for y in range(H):
        fade = max(0, 120 - y) / 120.0  # rays dissolve toward the ground
        row = BAYER4[y & 3]
        for x in range(W):
            u = (x - y // 2) % 256
            best = 0.0
            core = False
            for (u0, w, s) in bands:
                du = abs(u - u0)
                du = min(du, 256 - du)
                if du >= w:
                    continue
                edge = 1.0 - du / w
                v = s * edge * fade
                if v > best:
                    best = v
                    core = edge > 0.62
            # lengthwise shimmer: soft breaks along the ray (x-seamless)
            best *= 0.72 + 0.28 * (_tri(u * 3 + y, 64, 8) / 8.0)
            lvl = int(best)
            if lvl <= 0:
                continue
            if row[x & 3] < (best - lvl) * 16:
                lvl += 1  # dither the fractional level
            alpha = min(13, lvl) * 12  # <= 156: always soft
            c = SHAFT_CORE if core else SHAFT_SOFT
            px[x, y] = (c[0], c[1], c[2], alpha)
    return img


def fx_fog():
    """Soft fog band: transparent top, wavy density that thickens toward the
    lower third then thins at the very bottom — reads as a floating layer.
    Two hues (lit crown, cool body) x quantized alphas; x-seamless."""
    img = _new(W, NEAR_H, (0, 0, 0, 0))
    px = img.load()
    for x in range(W):
        # per-column wavy onset (period-256 arithmetic => seamless)
        onset = 10 + _tri(x, 64, 8) + _tri(x + 23, 32, 4)
        row_max = 44 + _tri(x + 9, 128, 6)
        for y in range(NEAR_H):
            if y < onset:
                continue
            if y <= row_max:
                dens = (y - onset) / max(1, row_max - onset)  # 0..1 build
            else:
                dens = max(0.0, 1.0 - (y - row_max) / 22.0)  # settle out
            # horizontal puff modulation
            dens *= 0.62 + 0.38 * (_tri(x * 2 + y * 3, 64, 8) / 8.0)
            lvl = int(dens * 11)
            if lvl <= 0:
                continue
            if BAYER4[y & 3][x & 3] < (dens * 11 - lvl) * 16:
                lvl += 1
            alpha = min(11, lvl) * 13  # <= 143: always translucent
            c = FOG_HI if y < onset + 6 else FOG_LO
            px[x, y] = (c[0], c[1], c[2], alpha)
    return img


FAR = {"forest": forest_far, "marsh": marsh_far, "ruin": ruin_far, "lair": lair_far}
NEAR = {"forest": forest_near, "marsh": marsh_near, "ruin": ruin_near, "lair": lair_near}
OVERLAYS = {"fx-shafts": fx_shafts, "fx-fog": fx_fog}
