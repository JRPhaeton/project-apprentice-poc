import Phaser from 'phaser';

import { playSfx } from './audio';
import { isPaused } from './pause';

/**
 * Keyboard-driven menu list for the Battle scene: arrows + Enter/Z confirm,
 * X/Esc cancel, disabled entries greyed and unselectable. The cursor resets
 * to the FIRST entry on every open() — QA's E2E relies on bare Enter meaning
 * ATTACK at the start of every hero turn. All handlers are dead while the
 * game is paused (§8); cursor moves blip sfx.menu (§6 SFX mapping).
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
    private bg: Phaser.GameObjects.Rectangle | null = null;
    private rows: Phaser.GameObjects.Text[] = [];
    private cursor: Phaser.GameObjects.Text | null = null;
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
        this.bg = this.scene.add
            .rectangle(this.x, this.y, this.width, h, 0x101020, 0.92)
            .setOrigin(0, 0)
            .setStrokeStyle(1, 0x8080a0)
            .setDepth(50)
            .setScrollFactor(0);
        this.rows = this.items.map((item, i) =>
            this.scene.add
                .text(this.x + PAD + 8, this.y + PAD + i * ROW_H, item.label, {
                    fontFamily: 'monospace',
                    fontSize: '8px',
                    color: item.enabled ? '#e0e0e0' : '#606060'
                })
                .setDepth(51)
                .setScrollFactor(0)
        );
        this.cursor = this.scene.add
            .text(this.x + PAD, this.y + PAD, '>', {
                fontFamily: 'monospace',
                fontSize: '8px',
                color: '#ffff80'
            })
            .setDepth(51)
            .setScrollFactor(0);
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

    private bindKeys(): void {
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
