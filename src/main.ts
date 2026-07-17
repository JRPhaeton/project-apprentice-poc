import Phaser from 'phaser';

import { Boot } from './scenes/Boot';

// Rendering config per §3 of docs/PLAN.md: fixed 256×224 internal resolution
// (SNES NTSC visible area), nearest-neighbor scaling, letterboxed FIT.
new Phaser.Game({
    type: Phaser.AUTO,
    width: 256,
    height: 224,
    parent: 'game-container',
    backgroundColor: '#000000',
    pixelArt: true,
    roundPixels: true,
    scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH
    },
    scene: [Boot]
});
