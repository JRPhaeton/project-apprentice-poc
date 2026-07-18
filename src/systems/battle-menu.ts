import Phaser from 'phaser';

import { playSfx } from './audio';
import { getInputBus, type DirState } from './input-bus';
import { isPaused } from './pause';
import { addPanel, addUiText, type UiPanel, type UiText } from './ui';

/**
 * Keyboard-driven menu list for the Battle scene: arrows + Enter/Z confirm,
 * X/Esc cancel, disabled entries greyed and unselectable. The cursor resets
 * to the FIRST entry on every open() — QA's E2E relies on bare Enter meaning
 * ATTACK at the start of every hero turn. All handlers are dead while the
 * game is paused (§8); cursor moves blip sfx.menu (§6 SFX mapping). M6:
 * chrome panel + bitmap rows via the UI kit (rect/monospace fallback). M7:
 * input-bus subscriptions (touch d-pad/A/B) alongside the keys, plus direct
 * row tap targets — a single tap moves the cursor there AND confirms
 * (standard mobile JRPG; disabled rows ignore taps).
 */

export interface MenuItem {
    label: string;
    value: string;
    enabled: boolean;
}

export interface MenuOpenOpts {
    items: MenuItem[];
    onChoose: (value: string) => void;
    onCancel?: () => void;
}

const ROW_H = 10;
const PAD = 4;

export class MenuList {
    private readonly scene: Phaser.Scene;
    private readonly x: number;
    private readonly y: number;
    private readonly width: number;
    private bg: UiPanel | null = null;
    private rows: UiText[] = [];
    private zones: Phaser.GameObjects.Zone[] = [];
    private cursor: UiText | null = null;
    private items: MenuItem[] = [];
    private index = 0;
    private opts: MenuOpenOpts | null = null;

    constructor(scene: Phaser.Scene, x: number, y: number, width: number) {
        this.scene = scene;
        this.x = x;
        this.y = y;
        this.width = width;
    }

    isOpen(): boolean {
        return this.opts !== null;
    }

    open(opts: MenuOpenOpts): void {
        this.close();
        this.opts = opts;
        this.items = opts.items;
        this.index = 0;

        const h = this.items.length * ROW_H + PAD * 2;
        this.bg = addPanel(this.scene, this.x, this.y, this.width, h);
        this.bg.setDepth(50).setScrollFactor(0);
        this.rows = this.items.map((item, i) =>
            addUiText(this.scene, this.x + PAD + 8, this.y + PAD + i * ROW_H, item.label, {
                color: item.enabled ? 0xe0e0e0 : 0x606060
            })
                .setDepth(51)
                .setScrollFactor(0)
        );
        this.cursor = addUiText(this.scene, this.x + PAD, this.y + PAD, '>', { color: 0xffff80 })
            .setDepth(51)
            .setScrollFactor(0);
        // M7 direct tap: one hit zone per row; tap = move cursor there +
        // confirm in a single touch. M9: on touch devices the strip spans the
        // FULL canvas width — a 72px-wide row is an unhittable ~20px target
        // on a phone, and full-width row strips are the mobile-JRPG standard.
        const touch = this.scene.sys.game.device.input.touch;
        const zoneX = touch ? 0 : this.x;
        const zoneW = touch ? this.scene.scale.width : this.width;
        this.zones = this.items.map((item, i) => {
            const zone = this.scene.add
                .zone(zoneX, this.y + PAD + i * ROW_H - 1, zoneW, ROW_H)
                .setOrigin(0, 0)
                .setDepth(52)
                .setScrollFactor(0)
                .setInteractive({ useHandCursor: item.enabled });
            zone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_UP, () => this.tapRow(i));
            return zone;
        });
        this.moveCursor(0);
        this.bindKeys();
    }

    close(): void {
        this.unbindKeys();
        this.bg?.destroy();
        this.bg = null;
        this.cursor?.destroy();
        this.cursor = null;
        for (const row of this.rows) {
            row.destroy();
        }
        this.rows = [];
        for (const zone of this.zones) {
            zone.destroy();
        }
        this.zones = [];
        this.opts = null;
    }

    destroy(): void {
        this.close();
    }

    private readonly onUp = (): void => {
        if (!isPaused()) {
            this.moveCursor(-1);
        }
    };
    private readonly onDown = (): void => {
        if (!isPaused()) {
            this.moveCursor(1);
        }
    };
    private readonly onConfirm = (): void => {
        if (!this.opts || isPaused()) {
            return;
        }
        const item = this.items[this.index];
        if (!item?.enabled) {
            return;
        }
        const choose = this.opts.onChoose;
        this.close();
        choose(item.value);
    };
    private readonly onCancel = (): void => {
        if (!this.opts?.onCancel || isPaused()) {
            return;
        }
        const cancel = this.opts.onCancel;
        this.close();
        cancel();
    };

    /** M7 touch d-pad: a held-direction CHANGE to up/down moves the cursor. */
    private readonly onDir = (dir: DirState): void => {
        if (dir.y === -1) {
            this.onUp();
        } else if (dir.y === 1) {
            this.onDown();
        }
    };

    /** M7 direct tap on a row: cursor moves there and the entry confirms. */
    private tapRow(index: number): void {
        if (!this.opts || isPaused() || !this.items[index]?.enabled) {
            return;
        }
        this.index = index;
        this.moveCursor(0); // snap the cursor to the tapped row (no blip)
        this.onConfirm();
    }

    private bindKeys(): void {
        const bus = getInputBus(this.scene.game);
        bus.on('dir', this.onDir);
        bus.on('confirm', this.onConfirm);
        bus.on('cancel', this.onCancel);
        const kb = this.scene.input.keyboard;
        if (!kb) {
            return;
        }
        kb.on('keydown-UP', this.onUp);
        kb.on('keydown-DOWN', this.onDown);
        kb.on('keydown-ENTER', this.onConfirm);
        kb.on('keydown-Z', this.onConfirm);
        kb.on('keydown-X', this.onCancel);
        kb.on('keydown-ESC', this.onCancel);
    }

    private unbindKeys(): void {
        const bus = getInputBus(this.scene.game);
        bus.off('dir', this.onDir);
        bus.off('confirm', this.onConfirm);
        bus.off('cancel', this.onCancel);
        const kb = this.scene.input.keyboard;
        if (!kb) {
            return;
        }
        kb.off('keydown-UP', this.onUp);
        kb.off('keydown-DOWN', this.onDown);
        kb.off('keydown-ENTER', this.onConfirm);
        kb.off('keydown-Z', this.onConfirm);
        kb.off('keydown-X', this.onCancel);
        kb.off('keydown-ESC', this.onCancel);
    }

    private moveCursor(delta: number): void {
        if (this.items.length === 0 || !this.cursor) {
            return;
        }
        this.index = (this.index + delta + this.items.length) % this.items.length;
        this.cursor.setY(this.y + PAD + this.index * ROW_H);
        if (delta !== 0) {
            playSfx(this.scene, 'sfx.menu'); // cursor MOVE only, not open()
        }
    }
}
