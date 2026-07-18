import Phaser from 'phaser';

import type { ArtManifest } from '../core/contracts/data';
import { bloom, bloomSpike } from './grade';
import { dur, isTurbo } from './pacing';

/**
 * M6 battle/scene presentation FX (workstream 1): generated overlay textures
 * (slash arc, sparkle, ember dot), the battle-entry shutter transition, hit
 * shake, phase/victory camera flashes, and the room→backdrop mapping. All
 * durations route through dur() so ?turbo=1 collapses everything to instant
 * and the T speed toggle scales them. No asset dependencies — every texture
 * here is graphics-generated, so this never blocks on the Art lane.
 */

const SLASH_KEY = 'fx.slash';
const SPARK_KEY = 'fx.spark';
const EMBER_KEY = 'fx.ember';

/** Backdrop art key for the room a battle started from; boss always → lair. */
const ROOM_BACKDROP: Record<string, string> = {
    'room1-gate': 'backdrop.forest',
    'room2-forest': 'backdrop.forest',
    'room3-marsh': 'backdrop.marsh',
    'room4-ruin': 'backdrop.ruin'
};

export function backdropKeyFor(room: string | null | undefined, boss: boolean): string {
    if (boss) {
        return 'backdrop.lair';
    }
    // Debug jumps with no meaningful room resolve to the START_ROOM default,
    // which maps to forest — the specified fallback.
    return ROOM_BACKDROP[room ?? ''] ?? 'backdrop.forest';
}

/** Battle biome for a room ('backdrop.<biome>' key tail); boss → lair. */
export function biomeFor(room: string | null | undefined, boss: boolean): string {
    return backdropKeyFor(room, boss).replace('backdrop.', '');
}

export interface BackdropSpec {
    biome: string;
    /** M11 parallax far layer ('backdrop.<biome>.far'), else the M6 single key. */
    farKey: string;
    /** Near parallax band, when the manifest ships one. */
    nearKey: string | null;
    /** Biome atmosphere sheet to load (god-rays / fog), when manifest-known. */
    overlayKey: string | null;
}

/**
 * M11 parallax-pair resolution (Assets-lane convention): prefer the new
 * 'backdrop.<biome>.far'/'.near' manifest keys; the old single
 * 'backdrop.<biome>' stays as the far-layer alias until they land.
 */
export function backdropSpecFor(
    art: ArtManifest,
    room: string | null | undefined,
    boss: boolean
): BackdropSpec {
    const biome = biomeFor(room, boss);
    const farKey = art[`backdrop.${biome}.far`] ? `backdrop.${biome}.far` : `backdrop.${biome}`;
    const nearKey = art[`backdrop.${biome}.near`] ? `backdrop.${biome}.near` : null;
    const overlayKey =
        biome === 'forest' && art['fx.shafts']
            ? 'fx.shafts'
            : biome === 'marsh' && art['fx.fog']
              ? 'fx.fog'
              : null;
    return { biome, farKey, nearKey, overlayKey };
}

/**
 * M11 battle stage: parallax backdrop pair (far drifts ±1px over 8s, near
 * band ±4px over 6s) + the biome atmosphere overlay (forest god-rays at
 * screen blend, marsh fog band, ruin/lair warm ember pulse). Missing
 * textures skip cleanly; turbo → static placement (no hot looping tweens);
 * scene-hosted tweens freeze under pause. Returns the far image (bloom-spike
 * target for the entry transition), or null when no backdrop art exists.
 */
export function addBattleBackdrop(
    scene: Phaser.Scene,
    spec: BackdropSpec
): Phaser.GameObjects.Image | null {
    let far: Phaser.GameObjects.Image | null = null;
    if (scene.textures.exists(spec.farKey)) {
        far = scene.add.image(128, 72, spec.farKey).setDepth(1).setScale(1.02);
        if (!isTurbo()) {
            scene.tweens.add({
                targets: far,
                x: { from: 127, to: 129 },
                duration: Math.max(1, dur(4000)), // half-cycle; yoyo → 8s loop
                yoyo: true,
                repeat: -1,
                ease: 'Sine.easeInOut'
            });
        }
    }
    if (spec.nearKey && scene.textures.exists(spec.nearKey)) {
        // Bottom band of the 144px backdrop area, slightly overscanned so the
        // ±4px drift never exposes an edge seam.
        const near = scene.add.image(128, 112, spec.nearKey).setDepth(1).setScale(1.05, 1);
        if (!isTurbo()) {
            scene.tweens.add({
                targets: near,
                x: { from: 124, to: 132 },
                duration: Math.max(1, dur(3000)), // half-cycle; yoyo → 6s loop
                yoyo: true,
                repeat: -1,
                ease: 'Sine.easeInOut'
            });
        }
    }
    addBattleAtmosphere(scene, spec);
    return far;
}

/** Biome overlay strip on the battle stage (depth 4: over enemies, under UI). */
function addBattleAtmosphere(scene: Phaser.Scene, spec: BackdropSpec): void {
    if (spec.biome === 'forest' && scene.textures.exists('fx.shafts')) {
        const shafts = scene.add
            .image(128, 72, 'fx.shafts')
            .setDepth(4)
            .setAlpha(0.16)
            .setBlendMode(Phaser.BlendModes.SCREEN);
        if (!isTurbo()) {
            scene.tweens.add({
                targets: shafts,
                alpha: 0.09,
                duration: Math.max(1, dur(3000)),
                yoyo: true,
                repeat: -1,
                ease: 'Sine.easeInOut'
            });
        }
    } else if (spec.biome === 'marsh' && scene.textures.exists('fx.fog')) {
        const fog = scene.add.image(128, 120, 'fx.fog').setDepth(4).setAlpha(0.3).setScale(1.1, 1);
        if (!isTurbo()) {
            scene.tweens.add({
                targets: fog,
                x: { from: 120, to: 136 },
                duration: Math.max(1, dur(4500)),
                yoyo: true,
                repeat: -1,
                ease: 'Sine.easeInOut'
            });
        }
    } else if (spec.biome === 'ruin' || spec.biome === 'lair') {
        const pulse = scene.add
            .rectangle(128, 72, 256, 144, 0xff5a20, 1)
            .setDepth(4)
            .setAlpha(isTurbo() ? 0.08 : 0.05)
            .setBlendMode(Phaser.BlendModes.SCREEN);
        if (!isTurbo()) {
            scene.tweens.add({
                targets: pulse,
                alpha: 0.12,
                duration: Math.max(1, dur(2000)), // half-cycle; yoyo → 4s pulse
                yoyo: true,
                repeat: -1,
                ease: 'Sine.easeInOut'
            });
        }
    }
}

/** Generate the tiny FX textures once (the texture manager is game-global). */
export function ensureFxTextures(scene: Phaser.Scene): void {
    if (!scene.textures.exists(SPARK_KEY)) {
        const g = scene.add.graphics();
        g.fillStyle(0xffffff, 1);
        g.fillCircle(2, 2, 2);
        g.generateTexture(SPARK_KEY, 4, 4);
        g.destroy();
    }
    if (!scene.textures.exists(EMBER_KEY)) {
        const g = scene.add.graphics();
        g.fillStyle(0xffffff, 1);
        g.fillRect(1, 0, 1, 3);
        g.fillRect(0, 1, 3, 1);
        g.generateTexture(EMBER_KEY, 3, 3);
        g.destroy();
    }
    if (!scene.textures.exists(SLASH_KEY)) {
        const g = scene.add.graphics();
        g.lineStyle(3, 0xffffff, 1);
        g.beginPath();
        g.arc(24, 24, 19, Phaser.Math.DegToRad(-115), Phaser.Math.DegToRad(35));
        g.strokePath();
        g.lineStyle(1, 0xffffff, 0.7);
        g.beginPath();
        g.arc(24, 24, 14, Phaser.Math.DegToRad(-100), Phaser.Math.DegToRad(20));
        g.strokePath();
        g.generateTexture(SLASH_KEY, 48, 48);
        g.destroy();
    }
}

/**
 * Battle-entry transition: quick fade-in + horizontal shutter bars sliding
 * off alternately left/right (~500ms at 1x; instant under turbo). M11: plus
 * a camera zoom breath (1.0→1.03→1.0 over 400ms), a white flash, and a brief
 * bloom spike on the backdrop — all skipped under turbo (instant, no zoom).
 */
export function playBattleEntry(
    scene: Phaser.Scene,
    backdrop?: Phaser.GameObjects.GameObject | null
): void {
    const cam = scene.cameras.main;
    cam.fadeIn(Math.max(1, dur(200)), 0, 0, 0);
    if (!isTurbo() && dur(400) > 0) {
        cam.flash(Math.max(1, dur(180)), 255, 255, 255);
        scene.tweens.add({
            targets: cam,
            zoom: 1.03,
            duration: Math.max(1, dur(200)),
            yoyo: true,
            ease: 'Sine.easeInOut',
            onComplete: () => cam.setZoom(1)
        });
        if (backdrop) {
            bloomSpike(scene, backdrop, { color: 0xffffff, strength: 3, ms: 400 });
        }
    }
    const BAR_H = 28; // 224 / 8 bars
    for (let i = 0; i < 8; i++) {
        const bar = scene.add
            .rectangle(128, i * BAR_H + BAR_H / 2, 256, BAR_H, 0x000000)
            .setDepth(400)
            .setScrollFactor(0);
        scene.tweens.add({
            targets: bar,
            x: i % 2 === 0 ? -128 : 384,
            duration: Math.max(1, dur(400)),
            delay: dur(i * 15),
            ease: 'Cubic.easeIn',
            onComplete: () => bar.destroy()
        });
    }
}

/** 4px impact shake (intensity is a viewport fraction: 0.015 * 256 ≈ 4px). */
export function playHitShake(scene: Phaser.Scene): void {
    scene.cameras.main.shake(Math.max(1, dur(120)), 0.015);
}

/** Slash-arc overlay on physical attacks (generated arc — no asset needed). */
export function playSlash(scene: Phaser.Scene, x: number, y: number): void {
    ensureFxTextures(scene);
    const arc = scene.add
        .image(x, y, SLASH_KEY)
        .setDepth(40)
        .setScrollFactor(0)
        .setTint(0xfff0a0)
        .setRotation(-0.6)
        .setAlpha(0.95);
    scene.tweens.add({
        targets: arc,
        rotation: 0.7,
        scale: 1.2,
        alpha: 0,
        duration: Math.max(1, dur(240)),
        ease: 'Quad.easeOut',
        onComplete: () => arc.destroy()
    });
}

/** Sparkle burst for magic/heals: 8 dots flung outward, fading. M11: every
 *  other dot gets a soft glow (4 transient FX objects, gone in ~380ms). */
export function playSparkles(scene: Phaser.Scene, x: number, y: number, color: number): void {
    ensureFxTextures(scene);
    for (let i = 0; i < 8; i++) {
        const angle = (Math.PI * 2 * i) / 8 + Phaser.Math.FloatBetween(-0.3, 0.3);
        const dist = Phaser.Math.Between(12, 24);
        const dot = scene.add
            .image(x, y, SPARK_KEY)
            .setDepth(40)
            .setScrollFactor(0)
            .setTint(color);
        if (i % 2 === 0) {
            bloom(dot, { color, strength: 2, distance: 4 });
        }
        scene.tweens.add({
            targets: dot,
            x: x + Math.cos(angle) * dist,
            y: y + Math.sin(angle) * dist,
            alpha: 0,
            scale: 0.5,
            duration: Math.max(1, dur(380)),
            ease: 'Quad.easeOut',
            onComplete: () => dot.destroy()
        });
    }
}

/** Boss phase-change screen flash (warm — the cloak burns away). */
export function playPhaseFlash(scene: Phaser.Scene): void {
    scene.cameras.main.flash(Math.max(1, dur(300)), 255, 140, 60);
}

/** Victory screen flash. */
export function playVictoryFlash(scene: Phaser.Scene): void {
    scene.cameras.main.flash(Math.max(1, dur(250)), 255, 255, 200);
}

/**
 * M10 Victory relight: one-shot ember burst — warm dots flung radially
 * outward from (x, y), fading as they fly. Generated textures only.
 */
export function playEmberBurst(scene: Phaser.Scene, x: number, y: number): void {
    ensureFxTextures(scene);
    const tints = [0xffa040, 0xff7020, 0xffc060, 0xffe27a];
    for (let i = 0; i < 16; i++) {
        const angle = (Math.PI * 2 * i) / 16 + Phaser.Math.FloatBetween(-0.2, 0.2);
        const dist = Phaser.Math.Between(28, 72);
        const dot = scene.add
            .image(x, y, EMBER_KEY)
            .setDepth(40)
            .setScrollFactor(0)
            .setTint(tints[i % tints.length]);
        scene.tweens.add({
            targets: dot,
            x: x + Math.cos(angle) * dist,
            y: y + Math.sin(angle) * dist,
            alpha: 0,
            duration: Math.max(1, dur(Phaser.Math.Between(500, 850))),
            ease: 'Quad.easeOut',
            onComplete: () => dot.destroy()
        });
    }
}

/**
 * A drifting ember mote for the Intro: rises and fades on a randomized loop.
 * The alpha hits 0 at the top of each cycle, hiding the repeat snap-back.
 * Returns the mote so callers can bloom a capped few (M11).
 */
export function spawnEmber(scene: Phaser.Scene): Phaser.GameObjects.Image {
    ensureFxTextures(scene);
    const tints = [0xffa040, 0xff7020, 0xffc060, 0xe05010];
    const x = Phaser.Math.Between(4, 252);
    const y = Phaser.Math.Between(96, 236);
    const ember = scene.add
        .image(x, y, EMBER_KEY)
        .setDepth(3)
        .setTint(tints[Phaser.Math.Between(0, tints.length - 1)])
        .setAlpha(0);
    scene.tweens.add({
        targets: ember,
        y: y - Phaser.Math.Between(60, 120),
        x: x + Phaser.Math.Between(-14, 14),
        alpha: { from: Phaser.Math.FloatBetween(0.5, 0.95), to: 0 },
        duration: Phaser.Math.Between(2200, 4800),
        delay: Phaser.Math.Between(0, 1800),
        repeat: -1,
        ease: 'Sine.easeOut'
    });
    return ember;
}
