import Phaser from 'phaser';

import { markHp } from '../systems/hooks';
import { getInputBus, type InputBus } from '../systems/input-bus';
import { dur } from '../systems/pacing';
import { isPaused } from '../systems/pause';
import { savingDisabled } from '../systems/storage';
import { createTouchControls, isTouchDevice } from '../systems/touch';
import { addPanel, addUiText, moreMarkerChar, type UiPanel, type UiText } from '../systems/ui';

/**
 * Parallel UI scene (§4 of docs/PLAN.md): HUD (HP/MP + 'saving disabled'
 * notice, §11) on a chrome backing strip, the shared bottom dialogue/battle-
 * log box (2-line, advance on Enter/Z, §8 hold-to-fast-forward) in a chrome
 * panel, and toasts. Runs above Overworld/Battle. All text renders through
 * the M6 UI kit (bitmap font with monospace fallback). M7: hosts the touch
 * controls (touch devices only) and advances open dialogues on bus 'confirm'
 * (A button) or a tap anywhere on screen — a full-screen tap zone BELOW the
 * touch buttons, interactive only while a dialogue is open, so it never eats
 * d-pad/button presses or taps meant for other scenes.
 */
export class UIOverlay extends Phaser.Scene {
    private hudText!: UiText;
    private boxBg!: UiPanel;
    private boxText!: UiText;
    private moreMarker!: UiText;
    private keys!: { enter: Phaser.Input.Keyboard.Key; z: Phaser.Input.Keyboard.Key };
    private bus!: InputBus;
    private tapZone!: Phaser.GameObjects.Zone;
    private busAdvance = false;

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
        addPanel(this, 0, 0, 256, 16).setDepth(99);
        this.hudText = addUiText(this, 4, 4, '', {}).setDepth(100);
        if (savingDisabled()) {
            addUiText(this, 252, 4, 'SAVING OFF', { color: 0xff8080 })
                .setOrigin(1, 0)
                .setDepth(100);
        }
        this.boxBg = addPanel(this, 2, 178, 252, 44);
        this.boxBg.setDepth(100).setVisible(false);
        this.boxText = addUiText(this, 8, 184, '', { wrapWidth: 240, lineSpacing: 2 })
            .setDepth(101)
            .setVisible(false);
        this.moreMarker = addUiText(this, 246, 212, moreMarkerChar(this), { color: 0xffff80 })
            .setOrigin(1, 0)
            .setDepth(101)
            .setVisible(false);
        const kb = this.input.keyboard;
        this.keys = {
            enter: kb!.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER, false),
            z: kb!.addKey(Phaser.Input.Keyboard.KeyCodes.Z, false)
        };

        // M7: bus 'confirm' (touch A) advances an open dialogue like Enter/Z.
        this.busAdvance = false;
        this.bus = getInputBus(this.game);
        const onBusConfirm = (): void => {
            if (this.dialogueOpen && !isPaused()) {
                this.busAdvance = true;
            }
        };
        this.bus.on('confirm', onBusConfirm);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            this.bus.off('confirm', onBusConfirm);
        });

        // M7 tap-to-advance: full screen, below the touch buttons (topOnly
        // input gives the buttons precedence), enabled only while a dialogue
        // is open. Mouse clicks ride the same path for free.
        this.tapZone = this.add.zone(128, 112, 256, 224).setDepth(150).setInteractive();
        this.tapZone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_UP, () => {
            if (this.dialogueOpen && !isPaused()) {
                this.busAdvance = true;
            }
        });
        this.tapZone.disableInteractive();

        // M7 touch UI (d-pad/A/B/pause/fullscreen) on touch devices only.
        if (isTouchDevice(this)) {
            createTouchControls(this);
        }
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
            this.tapZone.setInteractive(); // M7: tap anywhere advances
        });
    }

    toast(text: string): void {
        const t = addUiText(this, 128, 96, text, { color: 0xffff80, align: 'center' })
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
        const busAdvance = this.busAdvance; // consume even on early return
        this.busAdvance = false;
        if (isPaused() || !this.onDialogueDone) {
            return; // §8: the typewriter freezes with everything else
        }
        const page = this.pages[this.pageIndex];
        // Held touch A fast-forwards exactly like a held Enter/Z (M7).
        const held = this.keys.enter.isDown || this.keys.z.isDown || this.bus.isConfirmHeld();
        const pressedEnter = Phaser.Input.Keyboard.JustDown(this.keys.enter);
        const pressedZ = Phaser.Input.Keyboard.JustDown(this.keys.z);
        let justPressed = pressedEnter || pressedZ || busAdvance;
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
                this.tapZone.disableInteractive(); // M7: stop eating taps
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
