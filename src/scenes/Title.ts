import Phaser from 'phaser';

import type { SaveBlob } from '../core/contracts/data';
import { stopMusic } from '../systems/audio';
import { MenuList } from '../systems/battle-menu';
import { freshHero } from '../systems/content';
import { markReady, markScene } from '../systems/hooks';
import { START_ROOM } from '../systems/overworld-map';
import { getRegistry, type GameRegistry } from '../systems/registry';
import { loadSave } from '../systems/storage';

/**
 * Title screen: final title + PRESS ENTER; minimal CONTINUE / NEW GAME menu
 * when a valid save exists (parse never throws — discard-on-mismatch, §4).
 * Music routing choice (§6): the Title is SILENT — the overworld theme
 * lazy-loads at first Overworld enter, which also guarantees playback starts
 * after a user input (the Enter press here), sidestepping autoplay locks.
 */
export class Title extends Phaser.Scene {
    private reg!: GameRegistry;
    private save: SaveBlob | null = null;
    private menu: MenuList | null = null;
    private started = false;

    constructor() {
        super('Title');
    }

    create(): void {
        markScene('Title');
        this.reg = getRegistry(this);
        this.started = false;
        this.scene.stop('UIOverlay'); // returning from GameOver/Victory
        stopMusic(this); // Title is silent (routing choice, see class doc)

        this.add
            .text(128, 78, 'TRIAL OF THE APPRENTICE', {
                fontFamily: 'monospace',
                fontSize: '12px',
                color: '#e0e0e0'
            })
            .setOrigin(0.5);
        this.add
            .text(128, 96, 'a saga-inspired trial', { fontFamily: 'monospace', fontSize: '8px', color: '#606080' })
            .setOrigin(0.5);
        const prompt = this.add
            .text(128, 150, 'PRESS ENTER', { fontFamily: 'monospace', fontSize: '8px', color: '#ffff80' })
            .setOrigin(0.5);
        this.tweens.add({ targets: prompt, alpha: 0.25, yoyo: true, repeat: -1, duration: 600 });
        // §8 QoL hints, unobtrusive footer: pause + battle speed toggle.
        this.add
            .text(128, 214, 'P PAUSE   T BATTLE SPEED', {
                fontFamily: 'monospace',
                fontSize: '8px',
                color: '#484860'
            })
            .setOrigin(0.5);

        this.save = loadSave(); // never throws (parseSaveBlob)

        const kb = this.input.keyboard;
        const onEnter = (): void => {
            if (this.started || this.menu?.isOpen()) {
                return;
            }
            if (this.save) {
                this.openMenu();
            } else {
                this.startGame(null);
            }
        };
        kb?.on('keydown-ENTER', onEnter);
        kb?.on('keydown-Z', onEnter);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-ENTER', onEnter);
            kb?.off('keydown-Z', onEnter);
            this.menu?.destroy();
            this.menu = null;
        });

        // E2E readiness hook (§10): Title is interactive from here on.
        markReady();
    }

    private openMenu(): void {
        this.menu ??= new MenuList(this, 92, 160, 72);
        this.menu.open({
            items: [
                { label: 'CONTINUE', value: 'continue', enabled: true },
                { label: 'NEW GAME', value: 'new', enabled: true }
            ],
            onChoose: (value) => this.startGame(value === 'continue' ? this.save : null)
        });
    }

    /** Reset the run state (fresh or from save), then enter the Overworld. */
    private startGame(save: SaveBlob | null): void {
        if (this.started) {
            return;
        }
        this.started = true;
        const defs = this.reg.get('defs');
        this.reg.set('hero', save ? save.hero : freshHero(defs.hero));
        this.reg.set('flags', save ? save.flags : {});
        // NEW GAME starts in room1-gate; CONTINUE restores the saved room
        // (arrival at that room's 'spawn' — overworldReturn stays null).
        this.reg.set('room', save ? save.room : START_ROOM);
        this.reg.set('battleRequest', null);
        this.reg.set('lastBattleResult', null);
        this.reg.set('overworldReturn', null);
        this.reg.set('stats', { battlesWon: 0, xpEarned: 0 });
        this.scene.launch('UIOverlay');
        this.scene.start('Overworld');
    }
}
