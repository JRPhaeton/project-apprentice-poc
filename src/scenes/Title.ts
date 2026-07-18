import Phaser from 'phaser';

import type { SaveBlob } from '../core/contracts/data';
import { stopMusic } from '../systems/audio';
import { MenuList } from '../systems/battle-menu';
import { freshHero } from '../systems/content';
import { markReady, markScene } from '../systems/hooks';
import { getInputBus } from '../systems/input-bus';
import { START_ROOM } from '../systems/overworld-map';
import { getRegistry, type GameRegistry } from '../systems/registry';
import { loadSave } from '../systems/storage';
import { addPanel, addUiText } from '../systems/ui';

/**
 * Title screen: final title + PRESS ENTER; minimal CONTINUE / NEW GAME menu
 * when a valid save exists (parse never throws — discard-on-mismatch, §4).
 * M6: NEW GAME routes through the Intro taunt scene before room1-gate;
 * CONTINUE (and debug jumps, which never reach Title) bypass it entirely.
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

        addUiText(this, 128, 60, 'TRIAL OF THE\nAPPRENTICE', {
            size: 16,
            color: 0xe0e0e0,
            align: 'center',
            lineSpacing: 2
        }).setOrigin(0.5);
        addUiText(this, 128, 92, 'the stolen emberheart', { color: 0x606080 }).setOrigin(0.5);
        // M7: touch devices read TAP TO START (tap anywhere = Enter below).
        const promptText = this.sys.game.device.input.touch ? 'TAP TO START' : 'PRESS ENTER';
        const prompt = addUiText(this, 128, 112, promptText, { color: 0xffff80 }).setOrigin(0.5);
        this.tweens.add({ targets: prompt, alpha: 0.25, yoyo: true, repeat: -1, duration: 600 });

        // §8 QoL / M6 controls clarity: full control set in a chrome panel.
        addPanel(this, 4, 166, 248, 52);
        addUiText(
            this,
            128,
            192,
            'ARROWS/WASD MOVE\nENTER/Z CONFIRM  X/ESC CANCEL\nP PAUSE  T SPEED',
            { color: 0xb0b0c8, align: 'center', lineSpacing: 4 }
        ).setOrigin(0.5);

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
        // M7: tap/click anywhere = Enter (menu row taps land on the MenuList
        // zones first; the isOpen() guard above keeps this a no-op then).
        this.input.on(Phaser.Input.Events.POINTER_UP, onEnter);
        const bus = getInputBus(this.game);
        bus.on('confirm', onEnter);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-ENTER', onEnter);
            kb?.off('keydown-Z', onEnter);
            this.input.off(Phaser.Input.Events.POINTER_UP, onEnter);
            bus.off('confirm', onEnter);
            this.menu?.destroy();
            this.menu = null;
        });

        // E2E readiness hook (§10): Title is interactive from here on.
        markReady();
    }

    private openMenu(): void {
        this.menu ??= new MenuList(this, 92, 124, 72);
        this.menu.open({
            items: [
                { label: 'CONTINUE', value: 'continue', enabled: true },
                { label: 'NEW GAME', value: 'new', enabled: true }
            ],
            onChoose: (value) => this.startGame(value === 'continue' ? this.save : null)
        });
    }

    /**
     * Reset the run state (fresh or from save), then enter the world. NEW
     * GAME plays the Intro taunt first (Intro launches the UIOverlay when it
     * hands off to the Overworld); CONTINUE goes straight to the saved room.
     */
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
        if (save) {
            this.scene.launch('UIOverlay');
            this.scene.start('Overworld');
        } else {
            this.scene.start('Intro');
        }
    }
}
