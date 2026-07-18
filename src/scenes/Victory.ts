import Phaser from 'phaser';

import { registerAnims } from '../systems/anims';
import { stopMusic } from '../systems/audio';
import { playEmberBurst } from '../systems/fx';
import { markScene } from '../systems/hooks';
import { dur, isTurbo } from '../systems/pacing';
import { getRegistry } from '../systems/registry';
import { addUiText, type UiText } from '../systems/ui';

/**
 * Post-BOSS victory screen (encounters.json boss:true). M6 Emberheart
 * epilogue: Aden relights the Emberheart — plus the run stats. M10 relight
 * beat: before the text, ~2s of the Emberheart sprite (fx.emberheart,
 * 'burn' anim, ×2) igniting on a dark screen — ember burst outward, warm
 * tint sweeping the cold navy background — then the epilogue fades in. Any
 * input skips the beat; ?turbo=1 renders the final state instantly (E2E
 * timing unchanged). Missing sprite/anim degrade to the burst + tint sweep
 * alone. sfx.victory already fired in Battle — nothing plays here.
 */

const HEART_KEY = 'fx.emberheart';
const COLD = 0x000010; // pre-relight navy
const WARM = 0x281208; // post-relight ember-lit dark

export class Victory extends Phaser.Scene {
    private beatDone = false;
    private sweepTween: Phaser.Tweens.Tween | null = null;

    constructor() {
        super('Victory');
    }

    create(): void {
        markScene('Victory');
        this.beatDone = false;
        this.scene.stop('UIOverlay');
        stopMusic(this); // §6: Victory stops music (fanfare sfx already fired)
        const reg = getRegistry(this);
        const hero = reg.get('hero');
        const stats = reg.get('stats');

        const bg = this.add.rectangle(128, 112, 256, 224, COLD);

        // Emberheart centerpiece (kept behind the text once it fades in).
        let heart: Phaser.GameObjects.Sprite | null = null;
        if (this.textures.exists(HEART_KEY)) {
            registerAnims(this, reg.get('defs').art, HEART_KEY);
            heart = this.add.sprite(128, 108, HEART_KEY, 0).setScale(2).setDepth(1);
            const burn = `${HEART_KEY}.burn`;
            if (this.anims.exists(burn)) {
                heart.play(burn);
            }
        }

        const texts: UiText[] = [
            addUiText(this, 128, 56, 'THE EMBERHEART BURNS AGAIN', { color: 0xffe080 }).setOrigin(0.5),
            addUiText(
                this,
                128,
                80,
                'The vale is warm. Somewhere,\nthe master smiles.',
                { color: 0xd8c8a0, align: 'center', lineSpacing: 4 }
            ).setOrigin(0.5),
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
            ).setOrigin(0.5),
            addUiText(this, 128, 168, 'PRESS ENTER', { color: 0x808080 }).setOrigin(0.5)
        ];
        for (const t of texts) {
            t.setDepth(2);
        }

        if (isTurbo()) {
            // Instant final state; exit binds synchronously exactly as pre-M10.
            bg.setFillStyle(WARM);
            heart?.setAlpha(0.35);
            this.bindExit();
            return;
        }

        // --- The relight beat (~2s at 1×, dur()-scaled, input-skippable) ---
        for (const t of texts) {
            t.setAlpha(0);
        }
        heart?.setAlpha(0);
        if (heart) {
            this.tweens.add({ targets: heart, alpha: 1, duration: Math.max(1, dur(300)) });
        }
        // Warm tint sweep: cold navy → ember-lit warm across the beat.
        const sweep = { t: 0 };
        this.sweepTween = this.tweens.add({
            targets: sweep,
            t: 1,
            delay: Math.max(1, dur(300)),
            duration: Math.max(1, dur(1300)),
            ease: 'Sine.easeInOut',
            onUpdate: () => {
                const c = Phaser.Display.Color.Interpolate.ColorWithColor(
                    Phaser.Display.Color.ValueToColor(COLD),
                    Phaser.Display.Color.ValueToColor(WARM),
                    100,
                    sweep.t * 100
                );
                bg.setFillStyle(Phaser.Display.Color.GetColor(c.r, c.g, c.b));
            }
        });
        // Ignition: two ember bursts as the warmth takes hold.
        this.time.delayedCall(Math.max(1, dur(350)), () => {
            if (!this.beatDone) {
                playEmberBurst(this, 128, 108);
            }
        });
        this.time.delayedCall(Math.max(1, dur(1000)), () => {
            if (!this.beatDone) {
                playEmberBurst(this, 128, 108);
            }
        });
        this.time.delayedCall(Math.max(1, dur(2000)), () => this.finishBeat(bg, heart, texts));

        // Any input skips the beat (generic keydown fires after the specific
        // keydown-<KEY> events, so nothing leaks into the exit handlers —
        // which bind a tick later anyway).
        const skip = (): void => this.finishBeat(bg, heart, texts);
        this.input.keyboard?.once('keydown', skip);
        this.input.once(Phaser.Input.Events.POINTER_UP, skip);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            this.input.keyboard?.off('keydown', skip);
            this.input.off(Phaser.Input.Events.POINTER_UP, skip);
        });
    }

    /** End of the beat (natural or skipped): warm bg, text in, exits live. */
    private finishBeat(
        bg: Phaser.GameObjects.Rectangle,
        heart: Phaser.GameObjects.Sprite | null,
        texts: UiText[]
    ): void {
        if (this.beatDone) {
            return;
        }
        this.beatDone = true;
        this.sweepTween?.stop(); // its onUpdate must not repaint the warm bg
        this.sweepTween = null;
        bg.setFillStyle(WARM);
        if (heart) {
            this.tweens.killTweensOf(heart);
            // Dim behind the epilogue text, but keep it burning.
            this.tweens.add({ targets: heart, alpha: 0.35, duration: Math.max(1, dur(250)) });
        }
        for (const t of texts) {
            this.tweens.add({ targets: t, alpha: 1, duration: Math.max(1, dur(350)) });
        }
        // Next tick: the press that skipped the beat must not also exit.
        this.time.delayedCall(0, () => this.bindExit());
    }

    private bindExit(): void {
        const kb = this.input.keyboard;
        const toTitle = (): void => {
            this.scene.start('Title');
        };
        kb?.once('keydown-ENTER', toTitle);
        kb?.once('keydown-Z', toTitle);
        // M7 touch: a tap (or click) anywhere advances too.
        this.input.once(Phaser.Input.Events.POINTER_UP, toTitle);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-ENTER', toTitle);
            kb?.off('keydown-Z', toTitle);
            this.input.off(Phaser.Input.Events.POINTER_UP, toTitle);
        });
    }
}
