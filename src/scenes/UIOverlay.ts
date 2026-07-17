import Phaser from 'phaser';

import { markHp } from '../systems/hooks';
import { dur } from '../systems/pacing';
import { isPaused } from '../systems/pause';
import { savingDisabled } from '../systems/storage';

/**
 * Parallel UI scene (§4 of docs/PLAN.md): HUD (HP/MP + 'saving disabled'
 * notice, §11), the shared bottom dialogue/battle-log box (2-line, advance on
 * Enter/Z, §8 hold-to-fast-forward), and toasts. Runs above Overworld/Battle.
 */
export class UIOverlay extends Phaser.Scene {
    private hudText!: Phaser.GameObjects.Text;
    private boxBg!: Phaser.GameObjects.Rectangle;
    private boxText!: Phaser.GameObjects.Text;
    private moreMarker!: Phaser.GameObjects.Text;
    private keys!: { enter: Phaser.Input.Keyboard.Key; z: Phaser.Input.Keyboard.Key };

    private logLines: string[] = [];
    private boxPinned = false;

    // Dialogue state machine (typewriter + hold-to-fast-forward).
    private pages: string[] = [];
    private pageIndex = 0;
    private shown = 0;
    private charTimer = 0;
    private holdTimer = 0;
    private swallowPress = false;
    private onDialogueDone: (() => void) | null = null;

    constructor() {
        super('UIOverlay');
    }

    create(): void {
        this.hudText = this.add
            .text(4, 3, '', { fontFamily: 'monospace', fontSize: '8px', color: '#e0e0e0' })
            .setDepth(100);
        if (savingDisabled()) {
            this.add
                .text(252, 3, 'SAVING OFF', { fontFamily: 'monospace', fontSize: '8px', color: '#ff8080' })
                .setOrigin(1, 0)
                .setDepth(100);
        }
        this.boxBg = this.add
            .rectangle(2, 178, 252, 44, 0x101020, 0.94)
            .setOrigin(0, 0)
            .setStrokeStyle(1, 0x8080a0)
            .setDepth(100)
            .setVisible(false);
        this.boxText = this.add
            .text(8, 184, '', {
                fontFamily: 'monospace',
                fontSize: '8px',
                color: '#e0e0e0',
                wordWrap: { width: 240 },
                lineSpacing: 2
            })
            .setDepth(101)
            .setVisible(false);
        this.moreMarker = this.add
            .text(246, 212, '▼', { fontFamily: 'monospace', fontSize: '8px', color: '#ffff80' })
            .setOrigin(1, 0)
            .setDepth(101)
            .setVisible(false);
        const kb = this.input.keyboard;
        this.keys = {
            enter: kb!.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER, false),
            z: kb!.addKey(Phaser.Input.Keyboard.KeyCodes.Z, false)
        };
    }

    get dialogueOpen(): boolean {
        return this.onDialogueDone !== null;
    }

    setHeroHud(hp: number, maxHp: number, mp: number, maxMp: number): void {
        this.hudText?.setText(`HP ${hp}/${maxHp}  MP ${mp}/${maxMp}`);
        markHp(hp);
    }

    /** Keep the box visible for the battle log (Battle pins, unpins on exit). */
    pinBox(pinned: boolean): void {
        this.boxPinned = pinned;
        this.logLines = [];
        if (!this.dialogueOpen) {
            this.setBoxVisible(pinned);
            this.boxText.setText('');
        }
    }

    /** Battle log: append a line; the box shows the last two immediately. */
    log(line: string): void {
        this.logLines.push(line);
        if (this.logLines.length > 2) {
            this.logLines = this.logLines.slice(-2);
        }
        if (!this.dialogueOpen) {
            this.setBoxVisible(true);
            this.boxText.setText(this.logLines.join('\n'));
        }
    }

    /** Modal dialogue: one page per source line, typewriter, Enter/Z advances. */
    showDialogue(lines: string[]): Promise<void> {
        return new Promise((resolve) => {
            if (this.onDialogueDone) {
                resolve(); // one dialogue at a time; drop re-entrant calls
                return;
            }
            this.pages = lines.length > 0 ? [...lines] : [''];
            this.pageIndex = 0;
            this.shown = 0;
            this.charTimer = 0;
            this.holdTimer = 0;
            this.swallowPress = true; // ignore the press that opened us
            this.onDialogueDone = resolve;
            this.setBoxVisible(true);
            this.boxText.setText('');
            this.moreMarker.setVisible(false);
        });
    }

    toast(text: string): void {
        const t = this.add
            .text(128, 96, text, { fontFamily: 'monospace', fontSize: '8px', color: '#ffff80' })
            .setOrigin(0.5)
            .setDepth(102);
        this.tweens.add({
            targets: t,
            y: 84,
            alpha: 0,
            delay: Math.max(1, dur(700)),
            duration: Math.max(1, dur(500)),
            onComplete: () => t.destroy()
        });
    }

    update(_time: number, delta: number): void {
        if (isPaused() || !this.onDialogueDone) {
            return; // §8: the typewriter freezes with everything else
        }
        const page = this.pages[this.pageIndex];
        const held = this.keys.enter.isDown || this.keys.z.isDown;
        const pressedEnter = Phaser.Input.Keyboard.JustDown(this.keys.enter);
        const pressedZ = Phaser.Input.Keyboard.JustDown(this.keys.z);
        let justPressed = pressedEnter || pressedZ;
        if (this.swallowPress) {
            // The keypress that opened the dialogue must not also advance it.
            this.swallowPress = false;
            justPressed = false;
        }

        if (this.shown < page.length) {
            // §8 hold-to-fast-forward: holding the key multiplies text speed.
            const msPerChar = dur(28);
            if (msPerChar <= 0 || justPressed) {
                this.shown = page.length;
            } else {
                this.charTimer += delta * (held ? 8 : 1);
                while (this.charTimer >= msPerChar && this.shown < page.length) {
                    this.charTimer -= msPerChar;
                    this.shown += 1;
                }
            }
            this.boxText.setText(page.slice(0, this.shown));
            this.moreMarker.setVisible(this.shown >= page.length);
            return;
        }

        this.moreMarker.setVisible(true);
        // Advance: fresh press always; a held key fast-forwards after a beat.
        this.holdTimer = held ? this.holdTimer + delta : 0;
        if (justPressed || (held && this.holdTimer >= Math.max(1, dur(180)))) {
            this.holdTimer = 0;
            this.pageIndex += 1;
            this.shown = 0;
            this.charTimer = 0;
            if (this.pageIndex >= this.pages.length) {
                const done = this.onDialogueDone;
                this.onDialogueDone = null;
                this.moreMarker.setVisible(false);
                if (this.boxPinned) {
                    this.boxText.setText(this.logLines.join('\n'));
                } else {
                    this.setBoxVisible(false);
                }
                done();
            }
        }
    }

    private setBoxVisible(visible: boolean): void {
        this.boxBg.setVisible(visible);
        this.boxText.setVisible(visible);
        if (!visible) {
            this.moreMarker.setVisible(false);
        }
    }
}
