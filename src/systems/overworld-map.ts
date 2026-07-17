import Phaser from 'phaser';

/**
 * Builds the Overworld's walkable space from the Tiled map (§4 integration
 * contract: map key 'map.room2', embedded tileset 'overworld', image key
 * 'tiles.overworld', object layer 'objects' with 'spawn' point, encounter
 * rects carrying `encounterId`, sign objects carrying `dialogueId`, and tile
 * property collide=true → setCollisionByProperty). Falls back to a synthetic
 * placeholder room when the map asset has not landed yet (placeholder-first,
 * §6 — the engine lane is never blocked on World-lane assets).
 */

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

export interface OverworldMapData {
    widthPx: number;
    heightPx: number;
    spawn: { x: number; y: number };
    /** Tile layers with collide=true tiles (physics colliders for the hero). */
    collisionLayers: Phaser.Tilemaps.TilemapLayer[];
    encounters: EncounterZone[];
    signs: SignZone[];
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

export function buildOverworldMap(scene: Phaser.Scene): OverworldMapData {
    if (scene.cache.tilemap.exists('map.room2') && scene.textures.exists('tiles.overworld')) {
        return buildFromTilemap(scene);
    }
    return buildFallback(scene);
}

function buildFromTilemap(scene: Phaser.Scene): OverworldMapData {
    const map = scene.make.tilemap({ key: 'map.room2' });
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

    const objects = map.getObjectLayer('objects');
    for (const obj of objects?.objects ?? []) {
        const encounterId = getProp(obj, 'encounterId');
        const dialogueId = getProp(obj, 'dialogueId');
        if (obj.name === 'spawn') {
            spawn = { x: obj.x ?? spawn.x, y: obj.y ?? spawn.y };
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
        signs
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
        signs: [{ dialogueId: 'sign-gate', rect: new Phaser.Geom.Rectangle(96, 48, 16, 16) }]
    };
}
