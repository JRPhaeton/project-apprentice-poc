"""Deterministic battle backdrops — Assets lane (M6 "The Stolen Emberheart").

Four 256x144 layered scenes (forest / marsh / ruin / lair), each <= 16
colors: Bayer-dithered vertical sky gradient, 2-3 silhouette layers, and a
ground band with an elliptical platform where enemies stand (battle scene
centers enemies ~y=100, so the horizon sits ~y=96 and the platform ellipse
is centered on (128, 122)). Self-authored, CC0; no randomness — all detail
placement is arithmetic, so re-runs are byte-identical.
"""

from PIL import Image, ImageDraw

W, H = 256, 144
HORIZON = 96
PLAT = (128, 122, 92, 15)  # cx, cy, rx, ry

BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _new():
    return Image.new("RGBA", (W, H), (0, 0, 0, 255))


def _sky(px, ramp, y0=0, y1=HORIZON):
    """Dithered vertical gradient: ramp[0] at y0 blending to ramp[-1] at y1."""
    zones = len(ramp) - 1
    span = (y1 - y0) / zones
    for y in range(y0, y1):
        z = min(zones - 1, int((y - y0) / span))
        t = ((y - y0) - z * span) / span
        lo, hi = ramp[z], ramp[z + 1]
        lvl = int(t * 16)
        for x in range(W):
            px[x, y] = hi if BAYER4[y & 3][x & 3] < lvl else lo
    return px


def _ground(d, px, base, dark, plat, plat_lt, rim):
    d.rectangle([0, HORIZON, W - 1, H - 1], fill=base)
    for y in range(HORIZON, H):
        lvl = int((y - HORIZON) / (H - HORIZON) * 10)
        for x in range(W):
            if BAYER4[y & 3][(x + 2) & 3] < lvl:
                px[x, y] = dark
    cx, cy, rx, ry = PLAT
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=rim)
    d.ellipse([cx - rx + 2, cy - ry + 1, cx + rx - 2, cy + ry - 2], fill=plat)
    # dithered sheen across the platform's upper half
    for y in range(cy - ry + 1, cy):
        for x in range(cx - rx + 4, cx + rx - 4):
            dd = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if dd < 0.55 and BAYER4[y & 3][x & 3] < 6:
                px[x, y] = plat_lt


def _conifer(d, x, base_y, h, w, color):
    for k in range(3):
        ty = base_y - h + k * (h // 4)
        hw = w * (k + 2) // 5
        d.polygon([(x, ty), (x - hw, base_y - (2 - k) * (h // 5)), (x + hw, base_y - (2 - k) * (h // 5))], fill=color)
    d.rectangle([x - 1, base_y - h // 5, x + 1, base_y], fill=color)


def _roundtree(d, x, base_y, r, color):
    d.rectangle([x - 1, base_y - r, x + 1, base_y], fill=color)
    d.ellipse([x - r, base_y - 2 * r - 2, x + r, base_y - r + 2], fill=color)
    d.ellipse([x - r + 2, base_y - 2 * r - 6, x + r - 4, base_y - r - 4], fill=color)


def forest():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    sky = [(12, 16, 30, 255), (20, 32, 42, 255), (32, 52, 50, 255), (52, 76, 56, 255), (84, 104, 62, 255)]
    far = (30, 48, 46, 255)
    mid = (20, 34, 34, 255)
    near = (12, 22, 24, 255)
    _sky(px, sky)
    # far tree line: soft canopy bumps on the horizon glow
    for k in range(16):
        x = k * 17 + (k * 7) % 11
        r = 7 + (k * 5) % 5
        d.ellipse([x - r, 84 - r - (k * 3) % 6, x + r, 96], fill=far)
    d.rectangle([0, 90, W - 1, HORIZON - 1], fill=far)
    # mid layer: conifers
    for k in range(9):
        x = 14 + k * 30 + (k * 13) % 9
        h = 34 + (k * 11) % 14
        _conifer(d, x, HORIZON, h, 9 + (k * 3) % 4, mid)
    # near layer: heavy silhouettes hugging the frame edges
    for x, r in ((6, 16), (30, 12), (226, 13), (250, 17)):
        _roundtree(d, x, HORIZON + 2, r, near)
    _conifer(d, 18, HORIZON + 2, 52, 13, near)
    _conifer(d, 240, HORIZON + 2, 56, 14, near)
    # canopy overhang framing the top corners
    for cxx, r in ((-6, 30), (18, 20), (238, 22), (262, 32)):
        d.ellipse([cxx - r, -r - 8, cxx + r, r - 14], fill=near)
    for k in range(9):
        lx = (k * 31 + 5) % 250
        if 40 < lx < 216:
            continue
        px[lx, 16 + (k * 7) % 8] = near  # stray hanging leaves
    _ground(d, px, (26, 42, 32, 255), (18, 30, 24, 255), (38, 58, 38, 255), (50, 74, 46, 255), (14, 24, 20, 255))
    # sparse grass flicks on the ground band
    for k in range(14):
        x = (k * 19 + 7) % 250 + 3
        y = 100 + (k * 13) % 38
        if abs(x - 128) > 96 or abs(y - 122) > 16:
            px[x, y] = (18, 30, 24, 255)
            px[x, y - 1] = (38, 58, 38, 255)
    return img


def marsh():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    sky = [(14, 22, 28, 255), (22, 36, 42, 255), (34, 54, 58, 255), (48, 74, 74, 255)]
    fog_lt = (96, 130, 124, 255)
    fog = (70, 102, 100, 255)
    reed_far = (24, 40, 38, 255)
    reed_near = (16, 26, 26, 255)
    glow_lt = (168, 212, 196, 255)
    glow = (110, 160, 146, 255)
    _sky(px, sky)
    # drifting fog bands (dithered, widths vary)
    for band, (y0, hgt, lvl) in enumerate(((52, 5, 7), (66, 4, 10), (78, 6, 6), (88, 4, 9))):
        for y in range(y0, y0 + hgt):
            for x in range(W):
                if BAYER4[(y + band) & 3][(x + band * 2) & 3] < lvl:
                    px[x, y] = fog_lt if band % 2 else fog
    # far reed line on the horizon: irregular clumps, not an even comb
    for k in range(42):
        if k % 5 == 2 or k % 11 == 7:  # gaps between clumps
            continue
        x = (k * 6 + (k * 13) % 7) % 256
        top = 78 + (k * 7) % 13
        d.line([(x, top), (x, HORIZON)], fill=reed_far)
        if k % 3 == 0:
            d.rectangle([x, top, x, top + 2], fill=reed_far)
        if k % 4 == 1:  # bent tip
            px[min(255, x + 1), top] = reed_far
    # pale wisp-glow spots hanging in the fog (lights that are not stars)
    for k, (gx, gy, r) in enumerate(((58, 62, 3), (132, 48, 2), (198, 70, 3), (98, 82, 2))):
        for y in range(gy - r * 3, gy + r * 3 + 1):
            for x in range(gx - r * 3, gx + r * 3 + 1):
                dd = (x - gx) ** 2 + (y - gy) ** 2
                if dd <= r * r:
                    px[x, y] = glow_lt
                elif dd <= (r * 3) ** 2 and BAYER4[y & 3][x & 3] < 5:
                    px[x, y] = glow
    # near reeds: clumps at both frame edges
    for k in range(14):
        side = 0 if k < 7 else 1
        bx = (8 + k * 6) if side == 0 else (208 + (k - 7) * 7)
        top = 58 + (k * 9) % 22
        d.line([(bx, top), (bx + (k % 3) - 1, HORIZON + 4)], fill=reed_near, width=2)
        d.rectangle([bx - 1, top, bx + 1, top + 4], fill=reed_near)
    _ground(d, px, (20, 34, 36, 255), (14, 24, 26, 255), (44, 58, 44, 255), (60, 78, 54, 255), (14, 24, 26, 255))
    # still-water ripples around the islet platform
    for k, (rx0, ry) in enumerate(((10, 106), (150, 103), (30, 136), (180, 139), (90, 140))):
        d.line([(rx0, ry), (rx0 + 24 + (k * 5) % 10, ry)], fill=(56, 86, 84, 255))
    return img


def ruin():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    sky = [(16, 18, 32, 255), (26, 30, 48, 255), (40, 46, 64, 255), (58, 66, 82, 255)]
    moon = (180, 186, 196, 255)
    halo = (90, 98, 112, 255)
    farwall = (34, 38, 54, 255)
    col = (48, 54, 70, 255)
    col_lt = (66, 72, 88, 255)
    col_dk = (26, 30, 44, 255)
    _sky(px, sky)
    # cold moon with a dithered halo
    mx, my, mr = 202, 26, 9
    for y in range(my - mr * 2, my + mr * 2 + 1):
        for x in range(mx - mr * 2, mx + mr * 2 + 1):
            dd = (x - mx) ** 2 + (y - my) ** 2
            if dd <= mr * mr:
                px[x, y] = moon
            elif dd <= (mr * 2) ** 2 and BAYER4[y & 3][x & 3] < 4:
                px[x, y] = halo
    d.ellipse([mx - 4, my - 3, mx - 1, my], fill=halo)  # crater shading
    px[mx + 3, my + 4] = halo
    # far broken wall: crenellated skyline
    top = 62
    d.rectangle([0, top, W - 1, HORIZON - 1], fill=farwall)
    for k in range(16):
        x = k * 16
        if k % 3 != 1:
            d.rectangle([x, top - 6 - (k * 5) % 7, x + 9, top], fill=farwall)
    # breach: a collapsed stretch of wall, rubble slope spilling to the ground
    d.polygon(
        [(150, HORIZON), (150, top + 2), (158, 74), (166, top + 6), (176, 80), (186, top + 4), (196, 76), (196, HORIZON)],
        fill=(16, 18, 32, 255),
    )
    d.polygon([(154, HORIZON), (172, 88), (192, HORIZON)], fill=col_dk)  # rubble heap
    # mid layer: broken columns on the ground line
    for k, (x, h, broke) in enumerate(((22, 58, 10), (66, 44, 22), (120, 66, 4), (176, 38, 26), (228, 54, 14))):
        w2 = 7
        topy = HORIZON - h
        d.rectangle([x - w2, topy, x + w2, HORIZON], fill=col)
        d.line([(x - w2, topy), (x - w2, HORIZON)], fill=col_lt)
        d.line([(x + w2, topy), (x + w2, HORIZON)], fill=col_dk)
        # flutes
        for fx in (x - 3, x + 1):
            d.line([(fx, topy + 2), (fx, HORIZON)], fill=col_dk)
        # broken jagged top
        d.polygon([(x - w2, topy), (x - w2 + 4, topy - 5 - broke % 5), (x, topy - 2), (x + w2 - 3, topy - 6), (x + w2, topy)], fill=col)
        # capital ledge survives on some
        if k % 2 == 0:
            d.rectangle([x - w2 - 2, topy + 4, x + w2 + 2, topy + 7], fill=col_lt)
            d.line([(x - w2 - 2, topy + 7), (x + w2 + 2, topy + 7)], fill=col_dk)
    _ground(d, px, (42, 46, 60, 255), (30, 34, 46, 255), (58, 62, 76, 255), (74, 80, 94, 255), (22, 26, 38, 255))
    # flagstone seams + cracks across the platform floor
    for k, (x0, y0, x1, y1) in enumerate(((60, 128, 90, 126), (150, 118, 186, 121), (108, 134, 140, 133))):
        d.line([(x0, y0), (x1, y1)], fill=(30, 34, 46, 255))
    d.line([(128, 112), (140, 118)], fill=(22, 26, 38, 255))
    d.line([(140, 118), (134, 126)], fill=(22, 26, 38, 255))
    # fallen column drum, half sunk
    d.ellipse([28, 116, 58, 128], fill=col_dk)
    d.ellipse([28, 114, 58, 126], fill=col)
    d.arc([28, 114, 58, 126], 200, 340, fill=col_lt)
    return img


def lair():
    img = _new()
    d = ImageDraw.Draw(img)
    px = img.load()
    dark = [(8, 6, 12, 255), (14, 10, 18, 255), (22, 14, 22, 255)]
    glow_ramp = [(44, 18, 14, 255), (78, 32, 16, 255), (120, 56, 20, 255)]
    ember = (200, 96, 32, 255)
    ember_lt = (244, 180, 72, 255)
    ember_wh = (255, 236, 190, 255)
    rock = (16, 10, 16, 255)
    rock_lit = (60, 26, 18, 255)
    # cavern gloom, then heat rising from below (inverted gradient into the ground)
    _sky(px, dark, 0, 64)
    _sky(px, [dark[2], glow_ramp[0], glow_ramp[1]], 64, HORIZON)
    # stalactites, underlit on their right edges
    for k in range(11):
        x = 4 + k * 24 + (k * 7) % 10
        ln = 14 + (k * 13) % 22
        w2 = 4 + (k * 3) % 3
        d.polygon([(x - w2, 0), (x + w2, 0), (x, ln)], fill=rock)
        d.line([(x + w2 - 1, 1), (x, ln - 1)], fill=rock_lit)
    # back-wall rock teeth rising into the glow, two interleaved depths
    for k in range(9):
        x = k * 30 + (k * 11) % 14
        h = 20 + (k * 9) % 16
        d.polygon([(x - 12, HORIZON), (x + 2, HORIZON - h), (x + 16, HORIZON)], fill=rock)
    for k in range(8):
        x = 15 + k * 32 + (k * 7) % 11
        h = 9 + (k * 5) % 8
        d.polygon([(x - 7, HORIZON), (x, HORIZON - h), (x + 8, HORIZON)], fill=(22, 14, 22, 255))
    # ember rain: drifting sparks with short tails (arithmetic placement)
    for k in range(38):
        x = (k * 53 + 17) % 254 + 1
        y = (k * 89 + 29) % 116 + 6
        c = (ember, ember_lt, ember_wh)[k % 3]
        px[x, y] = c
        px[x, y - 1] = ember if k % 3 else glow_ramp[1]
        if k % 4 == 0:
            px[x, y - 2] = glow_ramp[1]
    _ground(d, px, glow_ramp[0], (26, 14, 16, 255), (40, 20, 16, 255), glow_ramp[0], (150, 70, 24, 255))
    # molten cracks webbing out from under the platform (the swallowed Emberheart)
    cx, cy = 128, 122
    for k, (x0, y0, x1, y1) in enumerate((
        (cx - 88, cy + 2, cx - 108, cy + 10), (cx + 86, cy - 2, cx + 110, cy + 4),
        (cx - 40, cy + 14, cx - 60, cy + 20), (cx + 44, cy + 13, cx + 70, cy + 19),
        (cx - 10, cy + 15, cx + 4, cy + 21),
    )):
        d.line([(x0, y0), (x1, y1)], fill=ember)
        px[max(0, min(255, x1)), max(0, min(143, y1))] = ember_lt
    # heat shimmer dither just above the horizon
    for y in range(HORIZON - 10, HORIZON):
        for x in range(W):
            if BAYER4[y & 3][(x + 1) & 3] < (y - (HORIZON - 12)):
                px[x, y] = glow_ramp[2] if px[x, y] == glow_ramp[1] else px[x, y]
    return img


BACKDROPS = {"forest": forest, "marsh": marsh, "ruin": ruin, "lair": lair}
