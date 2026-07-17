import Phaser from 'phaser';

import { queueSheet, registerAnims } from '../systems/anims';
import { readDebugOptions } from '../systems/debug';
import { ROOM_IDS } from '../systems/overworld-map';
import { getRegistry } from '../systems/registry';

/**
 * Preload (§2 lazy-load rule of docs/PLAN.md): ONLY Title/Overworld needs —
 * the overworld tileset, all four (tiny) room map JSONs, and the hero
 * overworld sheet (from the art manifest). Battle sheets AND all audio load
 * lazily on first need — no audio here (§2/§6). Maps that have not landed
 * yet 404 harmlessly; the Overworld falls back to a synthetic room.
 */
export class Preload extends Phaser.Scene {
    constructor() {
        super('Preload');
    }

    preload(): void {
        this.load.setBaseURL(import.meta.env.BASE_URL);
        this.add
            .text(128, 112, 'LOADING...', { fontFamily: 'monospace', fontSize: '8px', color: '#808080' })
            .setOrigin(0.5);

        this.load.image('tiles.overworld', 'assets/tilesets/overworld.png');
        for (const room of ROOM_IDS) {
            this.load.tilemapTiledJSON(`map.${room}`, `assets/maps/${room}.json`);
        }
        // Hero sheet path/frames come from the manifest, never hardcoded (§4).
        queueSheet(this.load, getRegistry(this).get('defs').art, 'hero.overworld');
    }

    create(): void {
        registerAnims(this, getRegistry(this).get('defs').art, 'hero.overworld');
        // Debug ?scene=overworld&room=<id> (VITE_ENABLE_DEBUG only): the room
        // was seeded into the registry by bootstrap; skip Title and go there.
        if (readDebugOptions().jumpRoomId) {
            this.scene.launch('UIOverlay');
            this.scene.start('Overworld');
            return;
        }
        this.scene.start('Title');
    }
}
