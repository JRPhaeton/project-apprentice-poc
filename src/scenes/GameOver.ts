import Phaser from 'phaser';

import { markScene } from '../systems/hooks';

export class GameOver extends Phaser.Scene {
    constructor() {
        super('GameOver');
    }

    create(): void {
        markScene('GameOver');
        this.scene.stop('UIOverlay');
        this.add.rectangle(128, 112, 256, 224, 0x000000);
        this.add
            .text(128, 96, 'THE VALE CLAIMS ANOTHER', {
                fontFamily: 'monospace',
                fontSize: '10px',
                color: '#c04040'
            })
            .setOrigin(0.5);
        this.add
            .text(128, 140, 'PRESS ENTER', { fontFamily: 'monospace', fontSize: '8px', color: '#808080' })
            .setOrigin(0.5);

        const kb = this.input.keyboard;
        const toTitle = (): void => {
            this.scene.start('Title');
        };
        kb?.once('keydown-ENTER', toTitle);
        kb?.once('keydown-Z', toTitle);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-ENTER', toTitle);
            kb?.off('keydown-Z', toTitle);
        });
    }
}
