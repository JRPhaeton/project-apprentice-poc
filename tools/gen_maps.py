#!/usr/bin/env python3
"""M8 topology-preserving map compositor — Assets lane.

Parses the four shipped Tiled maps (public/assets/maps/*.json), derives each
cell's terrain class from the CURRENT gids (v1 tileset semantics), and
re-emits every map against tileset v2 (tools/tileset_v2.py — 256x128):

  * 'ground' tile layer: base terrains, marching-squares transitions
    (path<->grass, water<->grass, mud<->dark-grass, marsh<->mud, ruin-floor
    edge), trunk/face tiles where a tree/wall sits above a walkable cell to
    its south, shadow-edge variants south of walls/trees, deterministic
    decor scatter seeded per room name.
  * 'overhead' tile layer (renders above the hero, never collides): canopy
    tiles over tree masses with scalloped edges, 1-tile canopy hang fringes
    onto adjacent walkable cells (never over object-covered cells), wall/
    ruin-wall cap-tops over interior wall cells, cap-lip strips over faces.
  * 'objects' layer: pre-M10 objects passed through VERBATIM and IN ORDER,
    then the M10 ADDITIVE extras (tools/room_extras.py literal table:
    treasure chests + the gate Keeper npc) appended at the tail. Extras
    already present on disk (matched by name) are stripped first, so
    re-running remains a byte-stable fixed point.
  * embedded tileset decl: columns 16, tilecount 128, imageheight 128, image
    path unchanged; per-tile properties collide:bool / anim:string from
    tileset_v2.build_props() — the engine scans properties, never indices.

HARD SELF-CHECKS (generation fails on violation; M10-amended policy):
  (a) the new collide-cell set — cells whose GROUND gid has collide:true —
      EXACTLY equals the v1 collide set per room, and the overhead layer
      contains no collide-property tile at all;
  (b) all pre-M10 objects present verbatim IN ORDER as the layer prefix;
      the room_extras appended at the tail with fresh ids (all greater
      than every pre-M10 id, sequential); every cell covered by an extra
      is walkable (non-collide ground gid) and overlaps no pre-M10
      object rect;
  (c) every gid is in [0..128], 0 allowed only on the overhead layer;
  (d) both tile layers are exactly width*height (896) entries.

Deterministic: decor/variant choice hashes room name + cell coords (sha256),
so re-running reproduces every map byte-for-byte.

Run from anywhere:  python3 tools/gen_maps.py
Optional:           python3 tools/gen_maps.py --preview OUTDIR
    also renders ground+overhead composites (2x) for eyeballing.
"""

import copy
import hashlib
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import room_extras  # noqa: E402  (M10 additive extras table)
import tileset_v2 as tv  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPS = os.path.join(ROOT, "public", "assets", "maps")

# v1 tileset semantics (gid = index + 1)
V1_CLASS = {
    1: "grass", 2: "path", 3: "tree", 4: "water", 5: "wall", 6: "sign",
    7: "flower", 8: "dark", 9: "mud", 10: "marsh", 11: "reed", 12: "rfloor",
    13: "rwall", 14: "door", 15: "rubble", 16: "ember",
}
V1_COLLIDE_GIDS = {3, 4, 5, 10, 13}


def _v2_class_table():
    """v2 tile id -> terrain class, so re-running the compositor on already-
    composited maps is a byte-stable fixed point (scattered decor reverses to
    its base class and the seeded hash re-places it identically)."""
    table = {}
    for tid in (tv.GRASS_A, tv.GRASS_B, tv.SH_GRASS, tv.ROCK_G, tv.STUMP_G):
        table[tid] = "grass"
    table[tv.GRASS_C] = "dark"
    for tid in (tv.DARK, tv.SH_DARK, tv.BONES_D, tv.ROCK_D):
        table[tid] = "dark"
    for mask in range(16):
        table[tv.PATH0 + mask] = "path"
        table[tv.WATER0 + mask] = "water"
        table[tv.MUD0 + mask] = "mud"
    for slot in range(len(tv.MINIMAL_MASKS)):
        table[tv.MARSH0 + slot] = "marsh"
        table[tv.RUIN0 + slot] = "rfloor"
    table[tv.SH_PATH] = "path"
    table[tv.SH_MUD] = "mud"
    table[tv.SH_RUIN] = "rfloor"
    table[tv.PEBBLES_R] = "rfloor"
    table[tv.TRUNK_G] = table[tv.TRUNK_D] = "tree"
    table[tv.WALL_FACE] = table[tv.GATE_FACE] = "wall"
    table[tv.RUIN_FACE] = "rwall"
    table[tv.SIGN_G] = table[tv.SIGN_D] = table[tv.SIGN_R] = "sign"
    table[tv.FLOWER] = "flower"
    table[tv.REED] = "reed"
    table[tv.RUBBLE] = "rubble"
    table[tv.DOOR] = "door"
    table[tv.EMBER] = "ember"
    return table


V2_CLASS = _v2_class_table()
# classes whose cells collide, in BOTH tileset generations
COLLIDE_CLASSES = {"tree", "water", "wall", "marsh", "rwall"}

N, E, S, W = tv.N, tv.E, tv.S, tv.W
DIRS = ((N, 0, -1), (E, 1, 0), (S, 0, 1), (W, -1, 0))

# Per-set "friendly" classes: neighbours that do NOT trigger a fringe.
FRIENDLY = {
    "path": {"path", "wall"},
    "water": {"water"},
    "mud": {"mud"},
    "marsh": {"marsh", "reed"},
    "rfloor": {"rfloor", "rwall", "door", "ember", "rubble", "sign"},
}

# Classes a canopy hang fringe may overhang (walkable, visually open).
HANGABLE = {"grass", "dark", "mud", "path", "rfloor", "flower", "reed", "rubble"}

SHADOW_CASTERS = {"tree", "wall", "rwall"}

ROOMS = {
    "room1-gate": {"base": "grass", "decor": {"grass": (tv.ROCK_G, tv.STUMP_G, tv.FLOWER)}},
    "room2-forest": {"base": "grass", "decor": {"grass": (tv.STUMP_G, tv.FLOWER, tv.ROCK_G)}},
    "room3-marsh": {"base": "dark", "decor": {"dark": (tv.ROCK_D,)}},
    "room4-ruin": {
        "base": "dark",
        "decor": {"dark": (tv.BONES_D, tv.ROCK_D), "rfloor": (tv.PEBBLES_R,)},
    },
}

DECOR_CHANCE = 7  # of 256 (~2.7% of eligible plain cells)
GRASS_B_CHANCE = 68  # of 256 (~27% of plain grass cells use the B variant)

SHADOW_TILE = {"grass": tv.SH_GRASS, "dark": tv.SH_DARK, "mud": tv.SH_MUD}
SIGN_TILE = {"grass": tv.SIGN_G, "dark": tv.SIGN_D, "rfloor": tv.SIGN_R}
TRUNK_TILE = {"grass": tv.TRUNK_G, "dark": tv.TRUNK_D}


def cell_hash(room, x, y, salt=""):
    digest = hashlib.sha256(f"{room}|{salt}|{x}|{y}".encode()).digest()
    return digest[0]


def check(cond, msg):
    if not cond:
        print(f"COMPOSITOR CHECK FAILED: {msg}", file=sys.stderr)
        sys.exit(1)


def object_cells(objects_layer, width, height):
    """Cells covered by any object (point objects cover their own cell)."""
    cells = set()
    for obj in objects_layer["objects"]:
        x, y = obj["x"], obj["y"]
        w, h = obj.get("width", 0), obj.get("height", 0)
        x0, y0 = int(x // 16), int(y // 16)
        x1 = int((x + max(w - 1, 0)) // 16)
        y1 = int((y + max(h - 1, 0)) // 16)
        for cy in range(max(0, y0), min(height - 1, y1) + 1):
            for cx in range(max(0, x0), min(width - 1, x1) + 1):
                cells.add((cx, cy))
    return cells


def edge_mask(cls_at, x, y, w, h, friendly):
    mask = 0
    for bit, dx, dy in DIRS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and cls_at(nx, ny) not in friendly:
            mask |= bit
    return mask


def compose_room(room, mapobj):
    cfg = ROOMS[room]
    w, h = mapobj["width"], mapobj["height"]
    layers = mapobj["layers"]
    ground_v1 = next(la for la in layers if la.get("name") == "ground")
    objects_layer = next(la for la in layers if la.get("type") == "objectgroup")
    data = ground_v1["data"]
    check(len(data) == w * h, f"{room}: source ground layer length {len(data)}")

    is_v1 = mapobj["tilesets"][0]["tilecount"] == 16
    table = V1_CLASS if is_v1 else V2_CLASS
    try:
        cls = [table[gid if is_v1 else gid - 1] for gid in data]
    except KeyError as exc:
        check(False, f"{room}: unclassifiable ground gid {exc}")
    old_collide_cells = {
        (i % w, i // w) for i, c in enumerate(cls) if c in COLLIDE_CLASSES
    }

    def at(x, y):
        return cls[y * w + x]

    def at_or(x, y, default):
        return cls[y * w + x] if 0 <= x < w and 0 <= y < h else default

    obj_cells = object_cells(objects_layer, w, h)
    old_collide = old_collide_cells

    ground = [0] * (w * h)
    overhead = [0] * (w * h)
    stats = {"transition": 0, "shadow": 0, "decor": 0, "hang": 0, "cap": 0, "anim": 0}

    # ---- pass 1: canopy hang fringes (needed by the canopy-cut pass) ----
    hang = {}
    for y in range(h):
        for x in range(w):
            if at(x, y) not in HANGABLE or (x, y) in obj_cells:
                continue
            if at_or(x, y + 1, "-") == "tree":
                hang[(x, y)] = S  # canopy from the south neighbour
            elif at_or(x - 1, y, "-") == "tree":
                hang[(x, y)] = W
            elif at_or(x + 1, y, "-") == "tree":
                hang[(x, y)] = E

    # ---- pass 2: ground + overhead ----
    for y in range(h):
        for x in range(w):
            i = y * w + x
            c = cls[i]
            shadowed = at_or(x, y - 1, "-") in SHADOW_CASTERS

            if c == "tree":
                ground[i] = TRUNK_TILE[cfg["base"]]
                # canopy cut mask: cut wherever the mass ends and no hang
                # fringe continues it; the south edge always cuts so the
                # trunk row stays visible under the lobes.
                cut = 0
                for bit, dx, dy in DIRS:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < w and 0 <= ny < h) or at(nx, ny) == "tree":
                        continue
                    if bit == S:
                        cut |= bit
                    elif hang.get((nx, ny)) != (S if bit == N else W if bit == E else E):
                        # neighbour continues the canopy only when its hang
                        # points back at this tree cell
                        cut |= bit
                overhead[i] = tv.canopy_id(cut)
            elif c == "wall":
                gate = at_or(x - 1, y, "-") == "path" or at_or(x + 1, y, "-") == "path"
                ground[i] = tv.GATE_FACE if gate else tv.WALL_FACE
                if at_or(x, y + 1, "wall") == "wall":
                    overhead[i] = tv.WALL_TOP  # interior cell: overhead cap
                    stats["cap"] += 1
                else:
                    overhead[i] = tv.LIP_WALL  # face cell: cap-lip only
            elif c == "rwall":
                ground[i] = tv.RUIN_FACE
                if at_or(x, y + 1, "rwall") in ("rwall", "door"):
                    overhead[i] = tv.RUIN_TOP
                    stats["cap"] += 1
                else:
                    overhead[i] = tv.LIP_RUIN
            elif c == "water":
                mask = edge_mask(at, x, y, w, h, FRIENDLY["water"])
                ground[i] = tv.water_id(mask)
                stats["transition"] += mask != 0
                stats["anim"] += mask == 0
            elif c == "marsh":
                mask = edge_mask(at, x, y, w, h, FRIENDLY["marsh"])
                ground[i] = tv.marsh_id(mask)
                stats["transition"] += mask != 0
                stats["anim"] += mask == 0
            elif c == "path":
                mask = edge_mask(at, x, y, w, h, FRIENDLY["path"])
                if mask == 0 and shadowed:
                    ground[i] = tv.SH_PATH
                    stats["shadow"] += 1
                else:
                    ground[i] = tv.path_id(mask)
                    stats["transition"] += mask != 0
            elif c == "mud":
                mask = edge_mask(at, x, y, w, h, FRIENDLY["mud"])
                if mask == 0 and shadowed:
                    ground[i] = tv.SH_MUD
                    stats["shadow"] += 1
                else:
                    ground[i] = tv.mud_id(mask)
                    stats["transition"] += mask != 0
            elif c == "rfloor":
                mask = edge_mask(at, x, y, w, h, FRIENDLY["rfloor"])
                if mask == 0 and shadowed:
                    ground[i] = tv.SH_RUIN
                    stats["shadow"] += 1
                else:
                    ground[i] = tv.ruin_id(mask)
                    stats["transition"] += mask != 0
            elif c == "sign":
                ground[i] = SIGN_TILE["rfloor" if at_or(x, y - 1, "-") in ("rfloor", "rwall", "door") else cfg["base"]]
            elif c == "flower":
                ground[i] = tv.FLOWER
            elif c == "reed":
                ground[i] = tv.REED
            elif c == "rubble":
                ground[i] = tv.RUBBLE
            elif c == "door":
                ground[i] = tv.DOOR
            elif c == "ember":
                ground[i] = tv.EMBER
                stats["anim"] += 1
            else:  # plain grass / dark-grass
                base = "grass" if c == "grass" else "dark"
                # in grass-base rooms an isolated full dark tile reads as a
                # hole — use the feathered grass-C patch (still class 'dark')
                accent = base == "dark" and cfg["base"] == "grass"
                if shadowed:
                    ground[i] = SHADOW_TILE["grass" if accent else base]
                    stats["shadow"] += 1
                elif accent:
                    ground[i] = tv.GRASS_C
                else:
                    table = cfg["decor"].get(base, ())
                    hb = cell_hash(room, x, y, "decor")
                    if table and (x, y) not in obj_cells and hb < DECOR_CHANCE:
                        ground[i] = table[hb % len(table)]
                        stats["decor"] += 1
                    elif base == "grass" and cell_hash(room, x, y, "var") < GRASS_B_CHANCE:
                        ground[i] = tv.GRASS_B
                    else:
                        ground[i] = tv.GRASS_A if base == "grass" else tv.DARK
            # hang fringe on this open cell (never over an object cell)
            if (x, y) in hang and overhead[i] == 0:
                overhead[i] = {S: tv.HANG_S, W: tv.HANG_W, E: tv.HANG_E}[hang[(x, y)]]
                stats["hang"] += 1

    # ids -> gids
    ground = [tid + 1 for tid in ground]
    overhead = [tid + 1 if tid else 0 for tid in overhead]
    return ground, overhead, old_collide, stats


def tileset_decl():
    tiles = []
    for tid in sorted(tv.build_props()):
        props = tv.build_props()[tid]
        plist = []
        if "anim" in props:
            plist.append({"name": "anim", "type": "string", "value": props["anim"]})
        if props.get("collide"):
            plist.append({"name": "collide", "type": "bool", "value": True})
        tiles.append({"id": tid, "properties": plist})
    return {
        "columns": tv.COLUMNS,
        "firstgid": 1,
        "image": "assets/tilesets/overworld.png",
        "imageheight": tv.SHEET_H,
        "imagewidth": tv.SHEET_W,
        "margin": 0,
        "name": "overworld",
        "spacing": 0,
        "tilecount": tv.TILECOUNT,
        "tileheight": 16,
        "tiles": tiles,
        "tilewidth": 16,
    }


def emit_map(room, mapobj, ground, overhead):
    new = copy.deepcopy(mapobj)
    ground_layer = next(la for la in new["layers"] if la.get("name") == "ground")
    objects_layer = next(la for la in new["layers"] if la.get("type") == "objectgroup")
    ground_layer["data"] = ground
    overhead_layer = {
        "data": overhead,
        "height": new["height"],
        "id": 3,
        "name": "overhead",
        "opacity": 1,
        "type": "tilelayer",
        "visible": True,
        "width": new["width"],
        "x": 0,
        "y": 0,
    }
    new["layers"] = [ground_layer, objects_layer, overhead_layer]
    new["nextlayerid"] = 4
    new["tilesets"] = [tileset_decl()]
    return new


def verify_room(room, old, new, old_collide, base_objects, extras):
    w, h = old["width"], old["height"]
    layers = {la["name"]: la for la in new["layers"]}
    ground = layers["ground"]["data"]
    overhead = layers["overhead"]["data"]

    # (d) layer sizes
    check(len(ground) == w * h, f"{room}: ground length {len(ground)} != {w * h}")
    check(len(overhead) == w * h, f"{room}: overhead length {len(overhead)} != {w * h}")

    # (c) gid bounds; 0 only on overhead
    check(all(1 <= g <= tv.TILECOUNT for g in ground), f"{room}: ground gid out of [1..128]")
    check(all(0 <= g <= tv.TILECOUNT for g in overhead), f"{room}: overhead gid out of [0..128]")

    # (a) collide set equality + collide-free overhead
    collide_gids = {tid + 1 for tid in tv.collide_ids()}
    new_collide = {(i % w, i // w) for i, g in enumerate(ground) if g in collide_gids}
    extra = new_collide - old_collide
    missing = old_collide - new_collide
    check(
        not extra and not missing,
        f"{room}: collide mismatch (+{sorted(extra)[:5]} -{sorted(missing)[:5]})",
    )
    check(
        not any(g in collide_gids for g in overhead),
        f"{room}: overhead layer contains collide-property tiles",
    )

    # (b) M10 policy: pre-M10 objects verbatim in order, extras at the tail
    new_objects = next(la for la in new["layers"] if la.get("type") == "objectgroup")["objects"]
    n_base = len(base_objects)
    check(
        new_objects[:n_base] == base_objects,
        f"{room}: pre-M10 objects not preserved verbatim in order",
    )
    check(new_objects[n_base:] == extras, f"{room}: extras not appended at the tail")
    max_base_id = max(o["id"] for o in base_objects)
    extra_ids = [o["id"] for o in extras]
    check(
        extra_ids == list(range(max_base_id + 1, max_base_id + 1 + len(extras))),
        f"{room}: extra ids {extra_ids} not fresh/sequential after {max_base_id}",
    )
    check(
        new["nextobjectid"] == max_base_id + 1 + len(extras),
        f"{room}: nextobjectid {new['nextobjectid']} stale",
    )
    # extras' cells: walkable ground, no overlap with any pre-M10 object rect
    base_cells = object_cells({"objects": base_objects}, w, h)
    for obj in extras:
        for cx, cy in sorted(object_cells({"objects": [obj]}, w, h)):
            gid = ground[cy * w + cx]
            check(
                gid not in collide_gids,
                f"{room}: extra '{obj['name']}' id {obj['id']} on collide cell ({cx},{cy})",
            )
            check(
                (cx, cy) not in base_cells,
                f"{room}: extra '{obj['name']}' id {obj['id']} overlaps a pre-M10 object at ({cx},{cy})",
            )

    # non-layer top-level fields preserved (tilesets/nextlayerid change by
    # design; nextobjectid advances past the appended extras, checked above)
    for key in old:
        if key not in ("layers", "tilesets", "nextlayerid", "nextobjectid"):
            check(old[key] == new[key], f"{room}: top-level '{key}' changed")


def render_preview(room, new, outdir):
    from PIL import Image

    tiles = tv.build_tiles()
    w, h = new["width"], new["height"]
    layers = {la["name"]: la for la in new["layers"]}
    img = Image.new("RGBA", (w * 16, h * 16), (10, 10, 16, 255))
    for name in ("ground", "overhead"):
        for i, gid in enumerate(layers[name]["data"]):
            if gid == 0:
                continue
            img.alpha_composite(tiles[gid - 1], ((i % w) * 16, (i // w) * 16))
    img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
    path = os.path.join(outdir, f"{room}.png")
    img.save(path)
    print(f"  preview {path}")


def main():
    outdir = None
    if "--preview" in sys.argv:
        outdir = sys.argv[sys.argv.index("--preview") + 1]
        os.makedirs(outdir, exist_ok=True)
    for room in ROOMS:
        path = os.path.join(MAPS, f"{room}.json")
        with open(path, encoding="utf-8") as f:
            mapobj = json.load(f)
        # M10: strip any previously appended extras (fixed point), then
        # append this run's extras BEFORE composing, so decor scatter and
        # canopy hangs keep clear of the chest/npc cells too.
        objects_layer = next(la for la in mapobj["layers"] if la.get("type") == "objectgroup")
        base_objects = [
            o for o in objects_layer["objects"] if o["name"] not in room_extras.EXTRA_NAMES
        ]
        extras = room_extras.build_extras(room, max(o["id"] for o in base_objects) + 1)
        objects_layer["objects"] = base_objects + extras
        ground, overhead, old_collide, stats = compose_room(room, mapobj)
        new = emit_map(room, mapobj, ground, overhead)
        new["nextobjectid"] = max(o["id"] for o in base_objects) + 1 + len(extras)
        verify_room(room, mapobj, new, old_collide, base_objects, extras)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(new, f, indent=1, sort_keys=True)
            f.write("\n")
        print(
            f"wrote {os.path.relpath(path, ROOT)}  collide={len(old_collide)} "
            f"objects={len(base_objects)}+{len(extras)} "
            f"transitions={stats['transition']} shadows={stats['shadow']} "
            f"decor={stats['decor']} hangs={stats['hang']} caps={stats['cap']} "
            f"anim-cells={stats['anim']}"
        )
        if outdir:
            render_preview(room, new, outdir)
    print("All compositor self-checks passed.")


if __name__ == "__main__":
    main()
