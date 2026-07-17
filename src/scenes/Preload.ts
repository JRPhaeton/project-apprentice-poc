import Phaser from 'phaser';

import { queueSheet, registerAnims } from '../systems/anims';
import { getRegistry } from '../systems/registry';

/**
 * Preload (§2 lazy-load rule of docs/PLAN.md): ONLY Title/Overworld needs —
 * overworld tileset, the Tiled map, and the hero overworld sheet (from the
 * art manifest). Battle sheets load lazily on first Battle entry.
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
        this.load.tilemapTiledJSON('map.room2', 'assets/maps/room2-forest.json');
        // Hero sheet path/frames come from the manifest, never hardcoded (§4).
        queueSheet(this.load, getRegistry(this).get('defs').art, 'hero.overworld');
    }

    create(): void {
        registerAnims(this, getRegistry(this).get('defs').art, 'hero.overworld');
        this.scene.start('Title');
    }
}
