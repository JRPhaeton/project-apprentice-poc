import Phaser from 'phaser';

import { stopMusic } from '../systems/audio';
import { markScene } from '../systems/hooks';
import { addUiText } from '../systems/ui';

export class GameOver extends Phaser.Scene {
    constructor() {
        super('GameOver');
    }

    create(): void {
        markScene('GameOver');
        this.scene.stop('UIOverlay');
        stopMusic(this); // §6: GameOver stops music
        this.add.rectangle(128, 112, 256, 224, 0x000000);
        addUiText(this, 128, 88, 'THE VALE CLAIMS ANOTHER', { color: 0xc04040 }).setOrigin(0.5);
        // M6 Emberheart canon: the Chimera gets the last word.
        addUiText(this, 128, 110, '"The vale grows colder still."', { color: 0x8868b0 }).setOrigin(
            0.5
        );
        addUiText(this, 128, 150, 'PRESS ENTER', { color: 0x808080 }).setOrigin(0.5);

        const kb = this.input.keyboard;
        const toTitle = (): void => {
            this.scene.start('Title');
        };
        kb?.once('keydown-ENTER', toTitle);
        kb?.once('keydown-Z', toTitle);
        // M7 touch: a tap (or click) anywhere advances too.
        this.input.once(Phaser.Input.Events.POINTER_UP, toTitle);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-ENTER', toTitle);
            kb?.off('keydown-Z', toTitle);
            this.input.off(Phaser.Input.Events.POINTER_UP, toTitle);
        });
    }
}
