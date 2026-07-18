import Phaser from 'phaser';

import { queueSheet, registerAnims } from '../systems/anims';
import { ensureAudio, playMusic, stopMusic } from '../systems/audio';
import { ensureFxTextures, spawnEmber } from '../systems/fx';
import { markScene } from '../systems/hooks';
import { dur } from '../systems/pacing';
import { getRegistry } from '../systems/registry';
import { addUiText, moreMarkerChar, type UiText } from '../systems/ui';

/**
 * M6 Intro ("The Stolen Emberheart" canon): NEW GAME → Intro → room1-gate.
 * A black scene with drifting ember motes and the cloaked Chimera looming as
 * a dark-tinted silhouette while it delivers its four-page typewriter taunt.
 * Enter/Z advances a page (or completes the current one); X/Esc skips the
 * whole intro at any point, including mid-load. CONTINUE and debug jumps
 * never enter this scene. Plays the one-shot 'music.sting' (silent-safe like
 * all audio); the sting stops on exit. All pacing routes through dur().
 */

const TAUNT_PAGES = [
    'Little apprentice. Your master burned so briefly.',
    'I swallowed his precious ember - it flickers in my belly still.',
    'The nights are mine now. The wisps sing for me.',
    'Come to the ruin, spark. Bring me your light too.'
];

const BOSS_ART = 'enemy.chimera';

export class Intro extends Phaser.Scene {
    private page = 0;
    private shown = 0;
    private charTimer = 0;
    private built = false;
    private leaving = false;
    /** Ignore advance presses briefly so the Title's Enter can't bleed in. */
    private graceUntil = 0;
    private text: UiText | null = null;
    private marker: UiText | null = null;
    private keys!: {
        enter: Phaser.Input.Keyboard.Key;
        z: Phaser.Input.Keyboard.Key;
        x: Phaser.Input.Keyboard.Key;
        esc: Phaser.Input.Keyboard.Key;
    };

    constructor() {
        super('Intro');
    }

    create(): void {
        markScene('Intro');
        this.page = 0;
        this.shown = 0;
        this.charTimer = 0;
        this.built = false;
        this.leaving = false;
        this.text = null;
        this.marker = null;
        this.graceUntil = this.time.now + dur(250);

        const kb = this.input.keyboard!;
        this.keys = {
            enter: kb.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER, false),
            z: kb.addKey(Phaser.Input.Keyboard.KeyCodes.Z, false),
            x: kb.addKey(Phaser.Input.Keyboard.KeyCodes.X, false),
            esc: kb.addKey(Phaser.Input.Keyboard.KeyCodes.ESC, false)
        };

        // Lazy batch (§2): the boss sheet (for the silhouette) + the sting.
        // Both degrade gracefully — a placeholder silhouette and silence.
        this.load.setBaseURL(import.meta.env.BASE_URL);
        const defs = getRegistry(this).get('defs');
        queueSheet(this.load, defs.art, BOSS_ART);
        ensureAudio(this, ['music.sting']);
        if (this.load.list.size > 0) {
            this.load.once(Phaser.Loader.Events.COMPLETE, () => this.build());
            this.load.start();
        } else {
            this.build();
        }
    }

    private build(): void {
        if (this.leaving) {
            return;
        }
        const defs = getRegistry(this).get('defs');
        ensureFxTextures(this);
        this.add.rectangle(128, 112, 256, 224, 0x000000).setDepth(0);

        // Looming cloaked-Chimera silhouette: the battle sheet's cloaked.idle
        // frames, scaled up and crushed to near-black. Placeholder: a dark mass.
        if (this.textures.exists(BOSS_ART)) {
            registerAnims(this, defs.art, BOSS_ART);
            const silhouette = this.add
                .sprite(128, 92, BOSS_ART, 0)
                .setScale(1.5)
                .setTint(0x241a30)
                .setAlpha(0.95)
                .setDepth(2);
            if (this.anims.exists(`${BOSS_ART}.cloaked.idle`)) {
                silhouette.play(`${BOSS_ART}.cloaked.idle`);
            }
            this.tweens.add({
                targets: silhouette,
                y: 96,
                yoyo: true,
                repeat: -1,
                duration: 2400,
                ease: 'Sine.easeInOut'
            });
        } else {
            this.add.ellipse(128, 96, 110, 132, 0x1a1424, 1).setDepth(2);
        }

        for (let i = 0; i < 26; i++) {
            spawnEmber(this);
        }

        // Dark non-looping sting (§6 silent-safe); stopped again on exit.
        playMusic(this, 'music.sting', { loop: false });

        this.text = addUiText(this, 128, 152, '', {
            wrapWidth: 224,
            align: 'center',
            lineSpacing: 2,
            color: 0xd8c8e8
        })
            .setOrigin(0.5, 0)
            .setDepth(5);
        this.marker = addUiText(this, 128, 198, moreMarkerChar(this), { color: 0xffff80 })
            .setOrigin(0.5)
            .setDepth(5)
            .setVisible(false);
        this.tweens.add({ targets: this.marker, alpha: 0.3, yoyo: true, repeat: -1, duration: 400 });
        addUiText(this, 252, 216, 'X SKIP', { color: 0x484860 }).setOrigin(1, 0.5).setDepth(5);
        this.built = true;
    }

    update(_time: number, delta: number): void {
        if (this.leaving) {
            return;
        }
        // X/Esc skips the WHOLE intro, at any time — even while still loading.
        if (
            Phaser.Input.Keyboard.JustDown(this.keys.x) ||
            Phaser.Input.Keyboard.JustDown(this.keys.esc)
        ) {
            this.exitIntro();
            return;
        }
        if (!this.built || !this.text) {
            return;
        }
        let advance =
            Phaser.Input.Keyboard.JustDown(this.keys.enter) ||
            Phaser.Input.Keyboard.JustDown(this.keys.z);
        if (advance && this.time.now < this.graceUntil) {
            advance = false; // the press that started NEW GAME
        }

        const pageText = TAUNT_PAGES[this.page];
        if (this.shown < pageText.length) {
            // Typewriter, same cadence as the dialogue box (§8).
            const msPerChar = dur(28);
            if (msPerChar <= 0 || advance) {
                this.shown = pageText.length;
            } else {
                this.charTimer += delta;
                while (this.charTimer >= msPerChar && this.shown < pageText.length) {
                    this.charTimer -= msPerChar;
                    this.shown += 1;
                }
            }
            this.text.setText(pageText.slice(0, this.shown));
            this.marker?.setVisible(this.shown >= pageText.length);
            return;
        }

        this.marker?.setVisible(true);
        if (advance) {
            this.page += 1;
            if (this.page >= TAUNT_PAGES.length) {
                this.exitIntro();
                return;
            }
            this.shown = 0;
            this.charTimer = 0;
            this.text.setText('');
            this.marker?.setVisible(false);
        }
    }

    /** Hand off to the Overworld (room1-gate is already in the registry). */
    private exitIntro(): void {
        if (this.leaving) {
            return;
        }
        this.leaving = true;
        stopMusic(this);
        const cam = this.cameras.main;
        cam.fadeOut(Math.max(1, dur(250)), 0, 0, 0);
        cam.once(Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE, () => {
            this.scene.launch('UIOverlay');
            this.scene.start('Overworld');
        });
    }
}
