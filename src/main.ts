import Phaser from 'phaser';

import { Battle } from './scenes/Battle';
import { Boot } from './scenes/Boot';
import { GameOver } from './scenes/GameOver';
import { Overworld } from './scenes/Overworld';
import { Preload } from './scenes/Preload';
import { Title } from './scenes/Title';
import { UIOverlay } from './scenes/UIOverlay';
import { Victory } from './scenes/Victory';

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
    physics: {
        default: 'arcade'
    },
    // Scene graph (§4): Boot → Preload → Title → Overworld ⇄ Battle
    // (+ UIOverlay parallel), GameOver, Victory.
    scene: [Boot, Preload, Title, Overworld, Battle, UIOverlay, GameOver, Victory]
});
