import Phaser from 'phaser';

import { stopMusic } from '../systems/audio';
import { markScene } from '../systems/hooks';
import { getRegistry } from '../systems/registry';

/** Post-BOSS victory screen (encounters.json boss:true). */
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
        this.add
            .text(128, 72, 'THE TRIAL IS COMPLETE', {
                fontFamily: 'monospace',
                fontSize: '10px',
                color: '#ffe080'
            })
            .setOrigin(0.5);
        this.add
            .text(
                128,
                108,
                [
                    `${hero.name} - LV ${hero.level}  XP ${hero.xp}`,
                    `HP ${hero.stats.hp}/${hero.stats.maxHp}  MP ${hero.stats.mp}/${hero.stats.maxMp}`,
                    `BATTLES WON ${stats.battlesWon}`
                ].join('\n'),
                {
                    fontFamily: 'monospace',
                    fontSize: '8px',
                    color: '#c0c0d0',
                    align: 'center',
                    lineSpacing: 4
                }
            )
            .setOrigin(0.5);
        this.add
            .text(128, 160, 'PRESS ENTER', { fontFamily: 'monospace', fontSize: '8px', color: '#808080' })
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
