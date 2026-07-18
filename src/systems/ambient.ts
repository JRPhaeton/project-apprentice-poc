import Phaser from 'phaser';

import { dur, isTurbo } from './pacing';

/**
 * M10 ambient particles (plan §3 atmosphere pass). Per-room low-count
 * emitters built from tiny generated textures + plain scene tweens — no
 * particle plugin, no assets:
 *   room1-gate   → 8 dust motes, slow drift, alpha .3
 *   room2-forest → 14 fireflies, warm blink + wander
 *   room3-marsh  → 8 soft fog ellipses, lateral drift, alpha .25
 *   room4-ruin   → 14 rising embers, rise + fade (snap-back hidden at alpha 0)
 *
 * Depth 15: above the hero (10), below the overhead layer (20). All tweens
 * are hosted on the calling scene, so the PauseController's tweens.pauseAll
 * freezes them with everything else; the room-switch scene restart destroys
 * them. dur()-aware: under ?turbo=1 every duration would collapse to 0 and an
 * infinite-repeat tween would spin hot, so turbo places the objects
 * statically instead (documented-acceptable degradation).
 */

const DEPTH = 15;
const DOT_KEY = 'ambient.dot'; // 2×2 square mote
const GLOW_KEY = 'ambient.glow'; // 3×3 round glow
const EMBER_KEY = 'ambient.ember'; // 2×3 tall spark

/** Generate the tiny shared textures once (texture manager is game-global). */
function ensureAmbientTextures(scene: Phaser.Scene): void {
    if (!scene.textures.exists(DOT_KEY)) {
        const g = scene.add.graphics();
        g.fillStyle(0xffffff, 1);
        g.fillRect(0, 0, 2, 2);
        g.generateTexture(DOT_KEY, 2, 2);
        g.destroy();
    }
    if (!scene.textures.exists(GLOW_KEY)) {
        const g = scene.add.graphics();
        g.fillStyle(0xffffff, 0.5);
        g.fillRect(0, 0, 3, 3);
        g.fillStyle(0xffffff, 1);
        g.fillRect(1, 1, 1, 1);
        g.generateTexture(GLOW_KEY, 3, 3);
        g.destroy();
    }
    if (!scene.textures.exists(EMBER_KEY)) {
        const g = scene.add.graphics();
        g.fillStyle(0xffffff, 1);
        g.fillRect(0, 1, 2, 2);
        g.fillStyle(0xffffff, 0.7);
        g.fillRect(0, 0, 1, 1);
        g.generateTexture(EMBER_KEY, 2, 3);
        g.destroy();
    }
}

function spot(widthPx: number, heightPx: number): { x: number; y: number } {
    return {
        x: Phaser.Math.Between(8, Math.max(9, widthPx - 8)),
        y: Phaser.Math.Between(24, Math.max(25, heightPx - 8))
    };
}

/** Room1 gate: slow-drifting dust motes. */
function addDust(scene: Phaser.Scene, widthPx: number, heightPx: number): void {
    for (let i = 0; i < 8; i++) {
        const { x, y } = spot(widthPx, heightPx);
        const mote = scene.add
            .image(x, y, DOT_KEY)
            .setDepth(DEPTH)
            .setTint(0xd8cfa8)
            .setAlpha(0.3);
        if (isTurbo()) {
            continue;
        }
        scene.tweens.add({
            targets: mote,
            x: x + Phaser.Math.Between(-22, 22),
            y: y + Phaser.Math.Between(-12, 12),
            duration: Math.max(1, dur(Phaser.Math.Between(4200, 7600))),
            delay: dur(Phaser.Math.Between(0, 1500)),
            yoyo: true,
            repeat: -1,
            ease: 'Sine.easeInOut'
        });
    }
}

/** Room2 forest: fireflies — warm blink + gentle wander. M11: the first six
 *  get a soft emissive glow (shared texture, capped FX object count). */
function addFireflies(scene: Phaser.Scene, widthPx: number, heightPx: number): void {
    for (let i = 0; i < 14; i++) {
        const { x, y } = spot(widthPx, heightPx);
        const fly = scene.add
            .image(x, y, GLOW_KEY)
            .setDepth(DEPTH)
            .setTint(i % 3 === 0 ? 0xd8ff9a : 0xffe27a)
            .setAlpha(0.4);
        if (isTurbo()) {
            continue;
        }
        scene.tweens.add({
            targets: fly,
            alpha: { from: 0.08, to: 0.5 },
            duration: Math.max(1, dur(Phaser.Math.Between(700, 1500))),
            delay: dur(Phaser.Math.Between(0, 1200)),
            yoyo: true,
            repeat: -1,
            ease: 'Sine.easeInOut'
        });
        scene.tweens.add({
            targets: fly,
            x: x + Phaser.Math.Between(-18, 18),
            y: y + Phaser.Math.Between(-14, 14),
            duration: Math.max(1, dur(Phaser.Math.Between(2800, 5600))),
            yoyo: true,
            repeat: -1,
            ease: 'Sine.easeInOut'
        });
    }
}

/** Room3 marsh: soft translucent fog blobs drifting laterally. */
function addFog(scene: Phaser.Scene, widthPx: number, heightPx: number): void {
    for (let i = 0; i < 8; i++) {
        const { x, y } = spot(widthPx, heightPx);
        const w = Phaser.Math.Between(48, 88);
        const blob = scene.add
            .ellipse(x, y, w, Math.round(w * 0.35), 0xbfd4dc, 0.25)
            .setDepth(DEPTH);
        if (isTurbo()) {
            continue;
        }
        scene.tweens.add({
            targets: blob,
            x: x + Phaser.Math.Between(24, 48) * (i % 2 === 0 ? 1 : -1),
            duration: Math.max(1, dur(Phaser.Math.Between(9000, 14000))),
            delay: dur(Phaser.Math.Between(0, 2000)),
            yoyo: true,
            repeat: -1,
            ease: 'Sine.easeInOut'
        });
    }
}

/** Room4 ruin: embers rising and fading (alpha hits 0 before the snap-back). */
function addEmbers(scene: Phaser.Scene, widthPx: number, heightPx: number): void {
    const tints = [0xffa040, 0xff7020, 0xffc060];
    for (let i = 0; i < 14; i++) {
        const { x, y } = spot(widthPx, heightPx);
        const ember = scene.add
            .image(x, y, EMBER_KEY)
            .setDepth(DEPTH)
            .setTint(tints[i % tints.length])
            .setAlpha(isTurbo() ? 0.4 : 0);
        if (isTurbo()) {
            continue;
        }
        scene.tweens.add({
            targets: ember,
            y: y - Phaser.Math.Between(32, 64),
            x: x + Phaser.Math.Between(-8, 8),
            alpha: { from: Phaser.Math.FloatBetween(0.45, 0.75), to: 0 },
            duration: Math.max(1, dur(Phaser.Math.Between(2200, 4200))),
            delay: dur(Phaser.Math.Between(0, 2200)),
            repeat: -1,
            ease: 'Sine.easeOut'
        });
    }
}

/** Attach the room's ambient layer. Unknown rooms (fallback map) → no-op. */
export function addAmbient(
    scene: Phaser.Scene,
    room: string,
    widthPx: number,
    heightPx: number
): void {
    ensureAmbientTextures(scene);
    if (room === 'room1-gate') {
        addDust(scene, widthPx, heightPx);
    } else if (room === 'room2-forest') {
        addFireflies(scene, widthPx, heightPx);
    } else if (room === 'room3-marsh') {
        addFog(scene, widthPx, heightPx);
    } else if (room === 'room4-ruin') {
        addEmbers(scene, widthPx, heightPx);
    }
}

// ---------------------------------------------------------------------------
// M11 room atmosphere overlays (screen-space, depth 25: above overhead layer
// 20, below menu chrome 50 and the pause scrim 300). Scene-hosted tweens →
// pause-frozen; turbo → static placement; missing textures → skip. The
// forest/marsh sheets ('fx.shafts'/'fx.fog') arrive from the Assets lane —
// the Overworld queues them and calls addRoomOverlays after its loader runs.
// ---------------------------------------------------------------------------

const OVERLAY_DEPTH = 25;
const WARM_GRAD_KEY = 'ambient.warmgrad';

/** Soft top-down warm gradient texture (CanvasTexture: renderer-agnostic). */
function ensureWarmGradient(scene: Phaser.Scene): boolean {
    if (scene.textures.exists(WARM_GRAD_KEY)) {
        return true;
    }
    const tex = scene.textures.createCanvas(WARM_GRAD_KEY, 8, 112);
    if (!tex) {
        return false;
    }
    const ctx = tex.getContext();
    const grad = ctx.createLinearGradient(0, 0, 0, 112);
    grad.addColorStop(0, 'rgba(255, 186, 100, 0.55)');
    grad.addColorStop(1, 'rgba(255, 186, 100, 0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 8, 112);
    tex.refresh();
    return true;
}

/** Room1 gate: golden-hour warm gradient washing down from the sky. */
function addGateGradient(scene: Phaser.Scene): void {
    if (!ensureWarmGradient(scene)) {
        return;
    }
    scene.add
        .image(0, 0, WARM_GRAD_KEY)
        .setOrigin(0, 0)
        .setDisplaySize(256, 112)
        .setScrollFactor(0)
        .setDepth(OVERLAY_DEPTH)
        .setAlpha(0.5)
        .setBlendMode(Phaser.BlendModes.SCREEN);
}

/** Room2 forest: god-ray sheet at screen blend with a slow 6s shimmer. */
function addForestShafts(scene: Phaser.Scene): void {
    if (!scene.textures.exists('fx.shafts')) {
        return;
    }
    const shafts = scene.add
        .image(128, 72, 'fx.shafts')
        .setScrollFactor(0)
        .setDepth(OVERLAY_DEPTH)
        .setAlpha(0.18)
        .setBlendMode(Phaser.BlendModes.SCREEN);
    if (isTurbo()) {
        return;
    }
    scene.tweens.add({
        targets: shafts,
        alpha: 0.1,
        duration: Math.max(1, dur(3000)), // half-cycle; yoyo → 6s shimmer
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut'
    });
}

/** Room3 marsh: ground-fog band hugging the bottom edge, drifting laterally. */
function addMarshFogBand(scene: Phaser.Scene): void {
    if (!scene.textures.exists('fx.fog')) {
        return;
    }
    const fog = scene.add
        .image(128, 192, 'fx.fog')
        .setScrollFactor(0)
        .setDepth(OVERLAY_DEPTH)
        .setAlpha(0.35)
        .setScale(1.1, 1); // overscan so the drift never exposes a seam
    if (isTurbo()) {
        return;
    }
    scene.tweens.add({
        targets: fog,
        x: { from: 120, to: 136 },
        duration: Math.max(1, dur(4000)),
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut'
    });
}

/** Room4 ruin: warm ember light pulsing over the whole frame (4s cycle). */
function addRuinPulse(scene: Phaser.Scene): void {
    const pulse = scene.add
        .rectangle(128, 112, 256, 224, 0xff5a20, 1)
        .setScrollFactor(0)
        .setDepth(OVERLAY_DEPTH)
        .setAlpha(isTurbo() ? 0.08 : 0.05)
        .setBlendMode(Phaser.BlendModes.SCREEN);
    if (isTurbo()) {
        return;
    }
    scene.tweens.add({
        targets: pulse,
        alpha: 0.12,
        duration: Math.max(1, dur(2000)), // half-cycle; yoyo → 4s pulse
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut'
    });
}

/** Attach the room's screen-space atmosphere overlay (M11). */
export function addRoomOverlays(scene: Phaser.Scene, room: string): void {
    if (room === 'room1-gate') {
        addGateGradient(scene);
    } else if (room === 'room2-forest') {
        addForestShafts(scene);
    } else if (room === 'room3-marsh') {
        addMarshFogBand(scene);
    } else if (room === 'room4-ruin') {
        addRuinPulse(scene);
    }
}
