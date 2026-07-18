import Phaser from 'phaser';

import { stopMusic } from '../systems/audio';
import { markScene } from '../systems/hooks';
import { getRegistry } from '../systems/registry';
import { addUiText } from '../systems/ui';

/**
 * Post-BOSS victory screen (encounters.json boss:true). M6 Emberheart
 * epilogue: Aden relights the Emberheart — plus the run stats.
 */
export class Victory extends Phaser.Scene {
    constructor() {
        super('Victory');
    }

    create(): void {
        markScene('Victory');
        this.scene.stop('UIOverlay');
        stopMusic(this); // §6: Victory stops music (fanfare sfx already fired)
        const reg = getRegistry(this);
        const hero = reg.get('hero');
        const stats = reg.get('stats');

        this.add.rectangle(128, 112, 256, 224, 0x000010);
        addUiText(this, 128, 56, 'THE EMBERHEART BURNS AGAIN', { color: 0xffe080 }).setOrigin(0.5);
        addUiText(
            this,
            128,
            80,
            'The vale is warm. Somewhere,\nthe master smiles.',
            { color: 0xd8c8a0, align: 'center', lineSpacing: 4 }
        ).setOrigin(0.5);
        addUiText(
            this,
            128,
            120,
            [
                `${hero.name} - LV ${hero.level}  XP ${hero.xp}`,
                `HP ${hero.stats.hp}/${hero.stats.maxHp}  MP ${hero.stats.mp}/${hero.stats.maxMp}`,
                `BATTLES WON ${stats.battlesWon}`
            ].join('\n'),
            { color: 0xc0c0d0, align: 'center', lineSpacing: 4 }
        ).setOrigin(0.5);
        addUiText(this, 128, 168, 'PRESS ENTER', { color: 0x808080 }).setOrigin(0.5);

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
