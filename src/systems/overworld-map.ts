import Phaser from 'phaser';

/**
 * Builds a room's walkable space from its Tiled map (§4 integration contract:
 * map keys 'map.<room>', embedded tileset 'overworld', image key
 * 'tiles.overworld', object layer 'objects'). Objects, classified by NAME
 * first, then by property:
 *   - 'spawn' point                          → arrival point for fresh entry
 *   - 'exit' rect (targetRoom/targetX/targetY props, tile coords) → room link
 *   - 'bossdoor' rect (encounterId + dialogueId props)            → boss gate
 *   - any rect with encounterId prop         → patrol encounter zone
 *   - any rect with dialogueId prop          → readable sign
 * Tile property collide=true → setCollisionByProperty. Falls back to a
 * synthetic placeholder room when the map asset has not landed yet
 * (placeholder-first, §6 — the engine lane is never blocked on World assets).
 */

/** The four-room stage (§9 M4). Preload fetches all four map JSONs. */
export const ROOM_IDS = ['room1-gate', 'room2-forest', 'room3-marsh', 'room4-ruin'];

export const START_ROOM = 'room1-gate';

export const TILE_SIZE = 16;

export interface EncounterZone {
    encounterId: string;
    rect: Phaser.Geom.Rectangle;
    /** Re-arm latch: only fires on a not-inside → inside transition. */
    armed: boolean;
}

export interface SignZone {
    dialogueId: string;
    rect: Phaser.Geom.Rectangle;
}

export interface ExitZone {
    targetRoom: string;
    /** Arrival TILE coords in the target room (lane convention). */
    targetX: number;
    targetY: number;
    rect: Phaser.Geom.Rectangle;
    /** Re-arm latch, same semantics as EncounterZone. */
    armed: boolean;
}

export interface BossDoorZone {
    encounterId: string;
    dialogueId: string;
    rect: Phaser.Geom.Rectangle;
}

export interface OverworldMapData {
    widthPx: number;
    heightPx: number;
    spawn: { x: number; y: number };
    /** Tile layers with collide=true tiles (physics colliders for the hero). */
    collisionLayers: Phaser.Tilemaps.TilemapLayer[];
    encounters: EncounterZone[];
    signs: SignZone[];
    exits: ExitZone[];
    bossDoors: BossDoorZone[];
}

type TiledObject = Phaser.Types.Tilemaps.TiledObject;

function getProp(obj: TiledObject, name: string): unknown {
    const props = obj.properties as { name: string; value: unknown }[] | undefined;
    if (!Array.isArray(props)) {
        return undefined;
    }
    return props.find((p) => p.name === name)?.value;
}

function objRect(obj: TiledObject): Phaser.Geom.Rectangle {
    const x = obj.x ?? 0;
    const y = obj.y ?? 0;
    const w = obj.width ?? 0;
    const h = obj.height ?? 0;
    // Points get a small interaction rect centered on themselves.
    if (w === 0 && h === 0) {
        return new Phaser.Geom.Rectangle(x - 8, y - 8, 16, 16);
    }
    return new Phaser.Geom.Rectangle(x, y, w, h);
}

export function buildOverworldMap(scene: Phaser.Scene, room: string): OverworldMapData {
    const key = `map.${room}`;
    if (scene.cache.tilemap.exists(key) && scene.textures.exists('tiles.overworld')) {
        return buildFromTilemap(scene, key);
    }
    return buildFallback(scene);
}

function buildFromTilemap(scene: Phaser.Scene, key: string): OverworldMapData {
    const map = scene.make.tilemap({ key });
    // No dimensions passed: Phaser reads them from the embedded tileset, so
    // the Assets lane widening the image (e.g. 128→256 px) needs no code change.
    const tileset = map.addTilesetImage('overworld', 'tiles.overworld');

    const collisionLayers: Phaser.Tilemaps.TilemapLayer[] = [];
    if (tileset) {
        for (const layerData of map.layers) {
            const layer = map.createLayer(layerData.name, tileset, 0, 0);
            if (!layer) {
                continue;
            }
            layer.setCollisionByProperty({ collide: true });
            collisionLayers.push(layer);
        }
    }

    let spawn = { x: map.widthInPixels / 2, y: map.heightInPixels / 2 };
    const encounters: EncounterZone[] = [];
    const signs: SignZone[] = [];
    const exits: ExitZone[] = [];
    const bossDoors: BossDoorZone[] = [];

    const objects = map.getObjectLayer('objects');
    for (const obj of objects?.objects ?? []) {
        const encounterId = getProp(obj, 'encounterId');
        const dialogueId = getProp(obj, 'dialogueId');
        if (obj.name === 'spawn') {
            spawn = { x: obj.x ?? spawn.x, y: obj.y ?? spawn.y };
        } else if (obj.name === 'exit') {
            const targetRoom = getProp(obj, 'targetRoom');
            const targetX = getProp(obj, 'targetX');
            const targetY = getProp(obj, 'targetY');
            if (
                typeof targetRoom === 'string' &&
                typeof targetX === 'number' &&
                typeof targetY === 'number'
            ) {
                exits.push({ targetRoom, targetX, targetY, rect: objRect(obj), armed: false });
            }
        } else if (obj.name === 'bossdoor') {
            // Carries BOTH ids — must classify before the prop-based branches.
            if (typeof encounterId === 'string' && typeof dialogueId === 'string') {
                bossDoors.push({ encounterId, dialogueId, rect: objRect(obj) });
            }
        } else if (typeof encounterId === 'string') {
            encounters.push({ encounterId, rect: objRect(obj), armed: false });
        } else if (typeof dialogueId === 'string') {
            signs.push({ dialogueId, rect: objRect(obj) });
        }
    }

    return {
        widthPx: map.widthInPixels,
        heightPx: map.heightInPixels,
        spawn,
        collisionLayers,
        encounters,
        signs,
        exits,
        bossDoors
    };
}

/** Synthetic placeholder room: walkable field, one spider patrol, one sign. */
function buildFallback(scene: Phaser.Scene): OverworldMapData {
    const w = 512;
    const h = 448;
    scene.add.rectangle(w / 2, h / 2, w, h, 0x1a2e1a);
    scene.add.rectangle(352, 192, 64, 64, 0x4a1a1a).setStrokeStyle(1, 0x804040);
    scene.add.rectangle(104, 56, 16, 16, 0x6a5a2a).setStrokeStyle(1, 0xa09040);

    return {
        widthPx: w,
        heightPx: h,
        spawn: { x: 128, y: 224 },
        collisionLayers: [],
        encounters: [
            { encounterId: 'enc-spider', rect: new Phaser.Geom.Rectangle(320, 160, 64, 64), armed: false }
        ],
        signs: [{ dialogueId: 'sign-gate', rect: new Phaser.Geom.Rectangle(96, 48, 16, 16) }],
        exits: [],
        bossDoors: []
    };
}
