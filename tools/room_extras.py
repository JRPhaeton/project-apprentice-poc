#!/usr/bin/env python3
"""M10 "The Vale Alive" — additive per-room object extras (Assets lane).

A literal table of NEW objects appended to each map's objects layer by
tools/gen_maps.py, AFTER the preserved pre-M10 objects. The compositor
strips any previously appended extras (matched by name) before re-appending,
so re-running gen_maps.py stays a byte-stable fixed point.

Object shapes (Tiled rects, engine reads name + properties, never ids):
  * chest — 16x16 rect sitting exactly on its tile; string prop `itemId`,
    int prop `qty`. Non-colliding walk-over cell (sign-style interact).
  * npc   — 16x24 rect, FOOT-anchored like the hero sprite: the rect's
    bottom edge is flush with the bottom of tile (tx, ty), so it spans
    cells (tx, ty-1) and (tx, ty) and the engine can render the 16x24
    sprite at the rect position directly. String props `dialogueId`,
    `spriteId`. Non-colliding (sign flow).

Placement discipline (verified by gen_maps.py's amended self-checks):
every covered cell is walkable (non-collide ground) and overlaps no
pre-M10 object rect; cells sit adjacent to but never ON the walk
corridors, so all shipped walk-route E2Es stay valid (a player detours
1-3 tiles to reach each chest).
"""

TILE = 16

# room -> ((name, tile_x, tile_y, {prop: value, ...}), ...) appended in order
EXTRAS = {
    "room1-gate": (
        # tutorial chest in the keeper's corner, 2 tiles east of the path
        ("chest", 18, 20, {"itemId": "herb", "qty": 2}),
        # the gate Keeper, beside the gate opening, west of his sign (19,23)
        ("npc", 18, 23, {"dialogueId": "dlg-npc-keeper-1", "spriteId": "npc.keeper"}),
    ),
    "room2-forest": (
        # glade pocket below the mid corridor, 2 south of the path
        ("chest", 22, 18, {"itemId": "herb", "qty": 1}),
        # under the northern treeline shade, 2 west of the exit walk-up
        ("chest", 24, 2, {"itemId": "manaMoss", "qty": 1}),
    ),
    "room3-marsh": (
        # dry bank beside the east mud lane, 1 east of the corridor
        ("chest", 28, 10, {"itemId": "emberDraught", "qty": 1}),
        # between the west pools, 2 west of the central mud lane
        ("chest", 9, 10, {"itemId": "manaMoss", "qty": 1}),
    ),
    "room4-ruin": (
        # north chamber beside the ember-glow tile (20,7), 2 east of the route
        ("chest", 20, 6, {"itemId": "powerBottle", "qty": 1}),
        # against the SW pillar, 1 north of the entry hall walk line
        ("chest", 13, 12, {"itemId": "emberDraught", "qty": 1}),
    ),
}

# names owned by this table — gen_maps.py strips these before re-appending
EXTRA_NAMES = frozenset(("chest", "npc"))

_PROP_TYPES = {"itemId": "string", "qty": "int", "dialogueId": "string", "spriteId": "string"}
_SIZES = {"chest": (16, 16), "npc": (16, 24)}


def build_extras(room, first_id):
    """Tiled object dicts for `room`, ids assigned sequentially from
    `first_id`. Deterministic: pure function of the literal table."""
    objs = []
    for i, (name, tx, ty, props) in enumerate(EXTRAS.get(room, ())):
        w, h = _SIZES[name]
        objs.append(
            {
                "height": h,
                "id": first_id + i,
                "name": name,
                "properties": [
                    {"name": k, "type": _PROP_TYPES[k], "value": v}
                    for k, v in sorted(props.items())
                ],
                "rotation": 0,
                "type": "",
                "visible": True,
                "width": w,
                "x": tx * TILE,
                # npc rects are foot-anchored: bottom edge flush with the tile
                "y": ty * TILE - (h - TILE),
            }
        )
    return objs
