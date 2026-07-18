"""Deterministic 8x8 pixel bitmap font — Assets lane (M6).

Self-authored micro-font, CC0 (assets/CREDITS.md). Full printable ASCII
32-126 on a 5x7 dot-matrix core (cap height 7, baseline row 7, descenders
in row 7), hand-tuned for legibility at 1x: B/8, O/0 and I/1/l are all
structurally distinct. Glyphs are centered in fixed 8x8 cells laid out
16 per row -> a 128x48 sheet (divisible by 16, so CI's source-asset-lint
grid check passes untouched).

Exports:
  build_font_png()  -> PIL RGBA image, white #FFFFFF glyphs on transparency
  build_fnt_xml()   -> BMFont XML text Phaser's load.bitmapFont accepts
  validate_fnt(xml_text, png_size) -> list of error strings (empty = valid)

No randomness anywhere; re-runs are byte-identical.
"""

CELL = 8
COLS = 16
FIRST, LAST = 32, 126
ROWS = ((LAST - FIRST + 1) + COLS - 1) // COLS  # 6
SHEET_W, SHEET_H = COLS * CELL, ROWS * CELL  # 128 x 48
LINE_HEIGHT = 9
BASE = 7
WHITE = (255, 255, 255, 255)

# Each glyph: up to 8 row-strings ('X' = pixel), row i = cell row i.
# Baseline sits under row 6; row 7 is the descender row (g j p q y , ; _).
G = {
    " ": [],
    "!": ["..X", "..X", "..X", "..X", "..X", "", "..X"],
    '"': [".X.X", ".X.X"],
    "#": ["", ".X.X.", "XXXXX", ".X.X.", "XXXXX", ".X.X."],
    "$": ["..X..", ".XXXX", "X.X..", ".XXX.", "..X.X", "XXXX.", "..X.."],
    "%": ["XX...", "XX..X", "...X.", "..X..", ".X...", "X..XX", "...XX"],
    "&": [".XX..", "X..X.", "X..X.", ".XX..", "X.X.X", "X..X.", ".XX.X"],
    "'": [".X", ".X"],
    "(": [".X", "X.", "X.", "X.", "X.", "X.", ".X"],
    ")": ["X.", ".X", ".X", ".X", ".X", ".X", "X."],
    "*": ["", "..X..", "X.X.X", ".XXX.", "X.X.X", "..X.."],
    "+": ["", "..X..", "..X..", "XXXXX", "..X..", "..X.."],
    ",": ["", "", "", "", "", "", ".X", "X."],
    "-": ["", "", "", "XXXXX"],
    ".": ["", "", "", "", "", "", "X"],
    "/": ["....X", "...X.", "...X.", "..X..", ".X...", ".X...", "X...."],
    "0": [".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."],
    "1": ["..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", "XXXXX"],
    "2": [".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"],
    "3": ["XXXX.", "....X", "....X", ".XXX.", "....X", "....X", "XXXX."],
    "4": ["...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."],
    "5": ["XXXXX", "X....", "X....", "XXXX.", "....X", "....X", "XXXX."],
    "6": [".XXX.", "X....", "X....", "XXXX.", "X...X", "X...X", ".XXX."],
    "7": ["XXXXX", "....X", "...X.", "..X..", "..X..", "..X..", "..X.."],
    "8": [".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."],
    "9": [".XXX.", "X...X", "X...X", ".XXXX", "....X", "....X", ".XXX."],
    ":": ["", "", "", "X", "", "", "X"],
    ";": ["", "", "", ".X", "", "", ".X", "X."],
    "<": ["...X", "..X.", ".X..", "X...", ".X..", "..X.", "...X"],
    "=": ["", "", "XXXXX", "", "XXXXX"],
    ">": ["X...", ".X..", "..X.", "...X", "..X.", ".X..", "X..."],
    "?": [".XXX.", "X...X", "....X", "...X.", "..X..", "", "..X.."],
    "@": [".XXX.", "X...X", "X.XXX", "X.X.X", "X.XXX", "X....", ".XXXX"],
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "B": ["XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."],
    "C": [".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."],
    "D": ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],
    "E": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"],
    "F": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."],
    "G": [".XXX.", "X...X", "X....", "X.XXX", "X...X", "X...X", ".XXXX"],
    "H": ["X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "I": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "XXXXX"],
    "J": ["..XXX", "...X.", "...X.", "...X.", "...X.", "X..X.", ".XX.."],
    "K": ["X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"],
    "L": ["X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"],
    "M": ["X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"],
    "N": ["X...X", "XX..X", "X.X.X", "X.X.X", "X..XX", "X...X", "X...X"],
    "O": [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "P": ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
    "Q": [".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"],
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
    "S": [".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
    "V": ["X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."],
    "W": ["X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"],
    "X": ["X...X", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "X...X"],
    "Y": ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
    "Z": ["XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"],
    "[": ["XX", "X.", "X.", "X.", "X.", "X.", "XX"],
    "\\": ["X....", ".X...", ".X...", "..X..", "...X.", "...X.", "....X"],
    "]": ["XX", ".X", ".X", ".X", ".X", ".X", "XX"],
    "^": ["..X..", ".X.X.", "X...X"],
    "_": ["", "", "", "", "", "", "", "XXXXX"],
    "`": ["X.", ".X"],
    "a": ["", "", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX"],
    "b": ["X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX."],
    "c": ["", "", ".XXX.", "X....", "X....", "X....", ".XXX."],
    "d": ["....X", "....X", ".XXXX", "X...X", "X...X", "X...X", ".XXXX"],
    "e": ["", "", ".XXX.", "X...X", "XXXXX", "X....", ".XXX."],
    "f": ["..XX", ".X..", "XXXX", ".X..", ".X..", ".X..", ".X.."],
    "g": ["", "", ".XXX.", "X...X", "X...X", ".XXXX", "....X", ".XXX."],
    "h": ["X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "X...X"],
    "i": ["", ".X.", "", "XX.", ".X.", ".X.", "XXX"],
    "j": ["", "..X", "", "..X", "..X", "..X", "..X", "XX."],
    "k": ["X....", "X....", "X..X.", "X.X..", "XX...", "X.X..", "X..X."],
    "l": ["X..", "X..", "X..", "X..", "X..", "X..", ".XX"],
    "m": ["", "", "XX.X.", "X.X.X", "X.X.X", "X.X.X", "X.X.X"],
    "n": ["", "", "XXXX.", "X...X", "X...X", "X...X", "X...X"],
    "o": ["", "", ".XXX.", "X...X", "X...X", "X...X", ".XXX."],
    "p": ["", "", "XXXX.", "X...X", "X...X", "XXXX.", "X....", "X...."],
    "q": ["", "", ".XXXX", "X...X", "X...X", ".XXXX", "....X", "....X"],
    "r": ["", "", "X.XX.", "XX..X", "X....", "X....", "X...."],
    "s": ["", "", ".XXXX", "X....", ".XXX.", "....X", "XXXX."],
    "t": [".X..", ".X..", "XXXX", ".X..", ".X..", ".X..", "..XX"],
    "u": ["", "", "X...X", "X...X", "X...X", "X...X", ".XXXX"],
    "v": ["", "", "X...X", "X...X", "X...X", ".X.X.", "..X.."],
    "w": ["", "", "X...X", "X.X.X", "X.X.X", "X.X.X", ".X.X."],
    "x": ["", "", "X...X", ".X.X.", "..X..", ".X.X.", "X...X"],
    "y": ["", "", "X...X", "X...X", "X...X", ".XXXX", "....X", ".XXX."],
    "z": ["", "", "XXXXX", "...X.", "..X..", ".X...", "XXXXX"],
    "{": [".XX", ".X.", ".X.", "X..", ".X.", ".X.", ".XX"],
    "|": [".X", ".X", ".X", ".X", ".X", ".X", ".X"],
    "}": ["XX.", ".X.", ".X.", "..X", ".X.", ".X.", "XX."],
    "~": ["", "", "", ".XX.X", "X.XX."],
}


def _cell(code):
    i = code - FIRST
    return (i % COLS) * CELL, (i // COLS) * CELL


def build_font_png():
    from PIL import Image

    img = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))
    px = img.load()
    for code in range(FIRST, LAST + 1):
        ch = chr(code)
        rows = G[ch]
        gw = max((len(r) for r in rows), default=0)
        ox, oy = _cell(code)
        ox += (CELL - gw) // 2  # center the glyph in its fixed cell
        for gy, row in enumerate(rows):
            for gx, c in enumerate(row):
                if c == "X":
                    px[ox + gx, oy + gy] = WHITE
    return img


def build_fnt_xml():
    chars = []
    for code in range(FIRST, LAST + 1):
        x, y = _cell(code)
        chars.append(
            f'    <char id="{code}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'xoffset="0" yoffset="0" xadvance="{CELL}" page="0" chnl="15"/>'
        )
    n = LAST - FIRST + 1
    return (
        '<?xml version="1.0"?>\n'
        "<font>\n"
        '  <info face="EmberSpark" size="8" bold="0" italic="0" charset="" unicode="1" '
        'stretchH="100" smooth="0" aa="1" padding="0,0,0,0" spacing="0,0" outline="0"/>\n'
        f'  <common lineHeight="{LINE_HEIGHT}" base="{BASE}" scaleW="{SHEET_W}" '
        f'scaleH="{SHEET_H}" pages="1" packed="0"/>\n'
        "  <pages>\n"
        '    <page id="0" file="font.png"/>\n'
        "  </pages>\n"
        f'  <chars count="{n}">\n' + "\n".join(chars) + "\n  </chars>\n</font>\n"
    )


def validate_fnt(xml_text, png_size):
    """Return a list of problems (empty list = the .fnt is valid)."""
    import xml.etree.ElementTree as ET

    errs = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:  # pragma: no cover - deterministic output
        return [f"font.fnt: XML parse error: {e}"]
    if root.tag != "font":
        errs.append(f"font.fnt: root tag {root.tag!r}, expected 'font'")
    common = root.find("common")
    if common is None:
        errs.append("font.fnt: missing <common>")
    else:
        if common.get("lineHeight") != str(LINE_HEIGHT):
            errs.append(f"font.fnt: lineHeight {common.get('lineHeight')} != {LINE_HEIGHT}")
        if common.get("base") != str(BASE):
            errs.append(f"font.fnt: base {common.get('base')} != {BASE}")
    page = root.find("pages/page")
    if page is None or page.get("file") != "font.png":
        errs.append("font.fnt: <page> missing or file != 'font.png'")
    w, h = png_size
    seen = {}
    for c in root.findall("chars/char"):
        cid = int(c.get("id"))
        seen[cid] = True
        x, y = int(c.get("x")), int(c.get("y"))
        cw, chh = int(c.get("width")), int(c.get("height"))
        if not (0 <= x and x + cw <= w and 0 <= y and y + chh <= h):
            errs.append(f"font.fnt: char {cid} rect {x},{y},{cw},{chh} out of {w}x{h}")
        for attr in ("xoffset", "yoffset", "xadvance"):
            if c.get(attr) is None:
                errs.append(f"font.fnt: char {cid} missing {attr}")
    for code in range(FIRST, LAST + 1):
        if code not in seen:
            errs.append(f"font.fnt: missing char id {code} ({chr(code)!r})")
    return errs


def _self_test():
    for ch, rows in G.items():
        assert 32 <= ord(ch) <= 126, f"non-printable glyph key {ch!r}"
        assert len(rows) <= 8, f"{ch!r}: {len(rows)} rows > 8"
        for r in rows:
            assert len(r) <= CELL, f"{ch!r}: row wider than {CELL}"
            assert set(r) <= {".", "X"}, f"{ch!r}: bad row chars {r!r}"
    assert len(G) == LAST - FIRST + 1, f"glyph count {len(G)} != 95"


_self_test()
