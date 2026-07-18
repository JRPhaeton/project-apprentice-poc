import Phaser from 'phaser';

import { addUiText, type UiText } from './ui';

/**
 * Pause (§8 QoL allowlist of docs/PLAN.md): P toggles pause in Overworld and
 * Battle. Freezes the host scene's tweens, clock, and physics, the global
 * animation manager, and the parallel UIOverlay's tweens/clock, then shows a
 * PAUSED overlay with the full control set (M6 controls clarity). Scene
 * update() loops and menu key handlers consult isPaused() so gameplay input
 * is dead while frozen; the P key itself stays live because the host scene
 * is never scene.pause()d.
 */

let paused = false;

export function isPaused(): boolean {
    return paused;
}

export class PauseController {
    private readonly scene: Phaser.Scene;
    private scrim: Phaser.GameObjects.Rectangle | null = null;
    private label: UiText | null = null;
    private controls: UiText | null = null;

    constructor(scene: Phaser.Scene) {
        this.scene = scene;
        const kb = scene.input.keyboard;
        const onP = (): void => this.setPaused(!paused);
        kb?.on('keydown-P', onP);
        scene.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-P', onP);
            if (paused) {
                this.setPaused(false); // never leak a frozen global state
            }
        });
    }

    private setPaused(on: boolean): void {
        if (paused === on) {
            return;
        }
        paused = on;
        const s = this.scene;
        const world = s.physics ? s.physics.world : null;
        const ui = s.scene.isActive('UIOverlay') ? s.scene.get('UIOverlay') : null;
        if (on) {
            world?.pause();
            s.tweens.pauseAll();
            s.time.paused = true;
            s.anims.pauseAll(); // global animation manager
            if (ui) {
                ui.tweens.pauseAll();
                ui.time.paused = true;
            }
            this.scrim = s.add
                .rectangle(128, 112, 256, 224, 0x000000, 0.45)
                .setDepth(300)
                .setScrollFactor(0);
            this.label = addUiText(s, 128, 92, 'PAUSED', { size: 16 })
                .setOrigin(0.5)
                .setDepth(301)
                .setScrollFactor(0);
            this.controls = addUiText(
                s,
                128,
                132,
                'ARROWS/WASD MOVE\nENTER/Z CONFIRM  X/ESC CANCEL\nP PAUSE  T SPEED',
                { color: 0xb0b0c8, align: 'center', lineSpacing: 4 }
            )
                .setOrigin(0.5)
                .setDepth(301)
                .setScrollFactor(0);
        } else {
            world?.resume();
            s.tweens.resumeAll();
            s.time.paused = false;
            s.anims.resumeAll();
            if (ui) {
                ui.tweens.resumeAll();
                ui.time.paused = false;
            }
            this.scrim?.destroy();
            this.scrim = null;
            this.label?.destroy();
            this.label = null;
            this.controls?.destroy();
            this.controls = null;
        }
    }
}
