import Phaser from 'phaser';

import { bootGame } from '../systems/bootstrap';
import { queueUiAssets } from '../systems/ui';

export class Boot extends Phaser.Scene {
    constructor() {
        super('Boot');
    }

    preload(): void {
        // §3/§4 of docs/PLAN.md: Vite's `base` only rewrites URLs Vite itself
        // processes, not Phaser's runtime string loader paths. Anchoring the
        // loader to BASE_URL makes leading-slash-free keys resolve on both
        // localhost and the GitHub Pages subpath.
        this.load.setBaseURL(import.meta.env.BASE_URL);
        // M6: bitmap font + window chrome load HERE (tiny) so both the normal
        // flow and ?scene=battle debug jumps render with them; missing files
        // degrade to the previous monospace/rect path inside the UI kit.
        queueUiAssets(this.load);
    }

    create(): void {
        // Content parse (zod, dev only) + registry seed + debug hooks (§4).
        const { reg, jump } = bootGame(this);
        if (jump) {
            // ?scene=battle&enemy=<id>: straight into that battle from boot.
            reg.set('battleRequest', jump);
            this.scene.launch('UIOverlay');
            this.scene.start('Battle');
            return;
        }
        this.scene.start('Preload');
    }
}
