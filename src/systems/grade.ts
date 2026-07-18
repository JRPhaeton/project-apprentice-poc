import Phaser from 'phaser';

import { dur, isTurbo } from './pacing';

/**
 * M11 "Modern 2D" color grading + emissive bloom (plan workstream 2). Every
 * helper is WebGL-guarded: on the Canvas renderer (which has no FX pipeline)
 * everything is a clean no-op — one code path, no visual crash.
 *
 * Grading = camera postFX: a subtle vignette (strength 0.35, radius 1.0 so
 * the falloff stays soft — the Phaser vignette shader renders FULL BLACK
 * outside its radius, and the frame corner sits at uv-distance ~0.707) plus a
 * ColorMatrix preset built with the saturate/hue/brightness/contrast chain
 * (first op sets, the rest pass multiply=true) and a final per-channel
 * white-balance gain matrix via multiply().
 *
 * Restart note (verified against phaser 3.90 source): CameraManager binds
 * `shutdown` to SceneEvents.SHUTDOWN and destroys every camera there; a
 * scene.restart() therefore gets a FRESH main camera with empty postFX — FX
 * never stack across restarts by construction. clearGrade() is still wired on
 * SHUTDOWN (and applyGrade clears before adding) as defense in depth, and so
 * mid-scene preset swaps never stack either.
 */

export type GradePreset =
    | 'gate'
    | 'forest'
    | 'marsh'
    | 'ruin'
    | 'battle-forest'
    | 'battle-marsh'
    | 'battle-ruin'
    | 'battle-lair'
    | 'intro'
    | 'victory-cold'
    | 'victory-warm';

interface GradeParams {
    /** saturate() amount (0 = identity). */
    sat: number;
    /** hue() rotation in degrees (0 = identity). */
    hue: number;
    /** brightness() scale (1 = identity). */
    bright: number;
    /** contrast() amount (0 = identity). */
    con: number;
    /** Per-channel RGB gain (white balance), 1/1/1 = identity. */
    balance: [number, number, number];
}

const PRESETS: Record<GradePreset, GradeParams> = {
    // Overworld rooms
    gate: { sat: 0.12, hue: 0, bright: 1.04, con: 0.05, balance: [1.1, 1.02, 0.88] },
    forest: { sat: 0.22, hue: -6, bright: 1.0, con: 0.06, balance: [0.92, 1.06, 1.0] },
    marsh: { sat: -0.25, hue: 0, bright: 0.98, con: 0.02, balance: [0.88, 1.02, 1.08] },
    ruin: { sat: -0.12, hue: 0, bright: 0.94, con: 0.12, balance: [0.88, 0.94, 1.14] },
    // Battle variants: same family, slightly punchier
    'battle-forest': { sat: 0.3, hue: -6, bright: 1.02, con: 0.1, balance: [0.92, 1.07, 1.0] },
    'battle-marsh': { sat: -0.18, hue: 0, bright: 1.0, con: 0.08, balance: [0.88, 1.03, 1.1] },
    'battle-ruin': { sat: -0.06, hue: 0, bright: 0.96, con: 0.16, balance: [0.9, 0.94, 1.15] },
    'battle-lair': { sat: 0.05, hue: 0, bright: 0.95, con: 0.18, balance: [1.1, 0.92, 0.94] },
    // Cinematics
    intro: { sat: -0.75, hue: 0, bright: 0.92, con: 0.08, balance: [0.92, 0.96, 1.12] },
    'victory-cold': { sat: -0.55, hue: 0, bright: 0.9, con: 0.05, balance: [0.9, 0.95, 1.15] },
    'victory-warm': { sat: 0.18, hue: 0, bright: 1.05, con: 0.06, balance: [1.14, 1.0, 0.84] }
};

/** Overworld room id → grade preset (fallback rooms stay ungraded). */
const ROOM_GRADE: Record<string, GradePreset> = {
    'room1-gate': 'gate',
    'room2-forest': 'forest',
    'room3-marsh': 'marsh',
    'room4-ruin': 'ruin'
};

/** Battle biome → battle grade preset. */
const BATTLE_GRADE: Record<string, GradePreset> = {
    forest: 'battle-forest',
    marsh: 'battle-marsh',
    ruin: 'battle-ruin',
    lair: 'battle-lair'
};

export function roomGradeFor(room: string): GradePreset | null {
    return ROOM_GRADE[room] ?? null;
}

export function battleGradeFor(biome: string): GradePreset | null {
    return BATTLE_GRADE[biome] ?? null;
}

/** Objects that carry a postFX component (sprites, images, rects, texts…). */
type FxTarget = Phaser.GameObjects.GameObject & {
    postFX?: Phaser.GameObjects.Components.FX;
    active: boolean;
};

interface GradeState {
    cam: Phaser.Cameras.Scene2D.Camera;
    matrix: Phaser.FX.ColorMatrix;
    lerp: Phaser.Tweens.Tween | null;
}

const gradeStates = new WeakMap<Phaser.Scene, GradeState>();
const bloomed = new WeakMap<Phaser.GameObjects.GameObject, Phaser.FX.Glow>();

/** Reusable 5x4 white-balance gain matrix (no per-call allocation). */
const balanceMatrix = [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0];
/** Scratch used to compose preset matrices off-camera (lerpGrade endpoints). */
const scratchCM = new Phaser.Display.ColorMatrix();
const lerpScratch = new Float32Array(20);

function isWebGL(scene: Phaser.Scene): boolean {
    return scene.game.renderer.type === Phaser.WEBGL;
}

/** Compose a preset onto a ColorMatrix via the documented chaining API. */
function composePreset(cm: Phaser.Display.ColorMatrix, preset: GradePreset): void {
    const p = PRESETS[preset];
    // First op multiply=false: resets the matrix, then SETS. The rest stack.
    cm.saturate(p.sat, false);
    if (p.hue !== 0) {
        cm.hue(p.hue, true);
    }
    cm.brightness(p.bright, true);
    cm.contrast(p.con, true);
    balanceMatrix[0] = p.balance[0];
    balanceMatrix[6] = p.balance[1];
    balanceMatrix[12] = p.balance[2];
    cm.multiply(balanceMatrix, true);
}

/** Read a composed matrix's raw 20 values (internal but stable in 3.90). */
function rawMatrix(cm: Phaser.Display.ColorMatrix): Float32Array {
    return (cm as unknown as { _matrix: Float32Array })._matrix;
}

/**
 * Apply a grade preset to the scene's main camera: subtle vignette + the
 * preset ColorMatrix. Re-applying (same scene, live camera) only rebuilds the
 * matrix — controllers are never stacked. Canvas renderer → no-op.
 */
export function applyGrade(scene: Phaser.Scene, preset: GradePreset): void {
    if (!isWebGL(scene)) {
        return;
    }
    const cam = scene.cameras?.main;
    if (!cam?.postFX) {
        return;
    }
    const state = gradeStates.get(scene);
    if (state && state.cam === cam) {
        // Same camera (mid-scene preset swap): retune the live controller.
        state.lerp?.stop();
        state.lerp = null;
        composePreset(state.matrix, preset);
        return;
    }
    cam.postFX.clear(); // defense in depth — never stack vignette/matrix
    cam.postFX.addVignette(0.5, 0.5, 1.0, 0.35);
    const matrix = cam.postFX.addColorMatrix();
    composePreset(matrix, preset);
    gradeStates.set(scene, { cam, matrix, lerp: null });
    scene.events.once(Phaser.Scenes.Events.SHUTDOWN, () => clearGrade(scene));
}

/**
 * Tween the camera grade from one preset to another (Victory relight beat).
 * Element-wise matrix lerp into a reusable scratch buffer — no per-frame
 * allocation. Turbo/Canvas → jump straight to the target preset.
 */
export function lerpGrade(
    scene: Phaser.Scene,
    from: GradePreset,
    to: GradePreset,
    ms: number
): void {
    if (!isWebGL(scene) || isTurbo() || dur(ms) <= 0) {
        applyGrade(scene, to);
        return;
    }
    applyGrade(scene, from);
    const state = gradeStates.get(scene);
    if (!state) {
        return;
    }
    composePreset(scratchCM, from);
    const a = Float32Array.from(rawMatrix(scratchCM));
    composePreset(scratchCM, to);
    const b = Float32Array.from(rawMatrix(scratchCM));
    const holder = { t: 0 };
    state.lerp?.stop();
    state.lerp = scene.tweens.add({
        targets: holder,
        t: 1,
        duration: Math.max(1, dur(ms)),
        ease: 'Sine.easeInOut',
        onUpdate: () => {
            for (let i = 0; i < 20; i++) {
                lerpScratch[i] = a[i] + (b[i] - a[i]) * holder.t;
            }
            state.matrix.set(lerpScratch);
        }
    });
}

/** Remove all camera postFX for the scene (SHUTDOWN-safe: camera may be gone). */
export function clearGrade(scene: Phaser.Scene): void {
    const state = gradeStates.get(scene);
    if (!state) {
        return;
    }
    gradeStates.delete(scene);
    state.lerp?.stop();
    // CameraManager destroys cameras on SHUTDOWN before this runs on restart
    // paths; only touch the controller when the camera is still the live one.
    const cam = scene.cameras?.main;
    if (cam && cam === state.cam && cam.postFX) {
        cam.postFX.clear();
    }
}

export interface BloomOpts {
    /** Glow color. Default 0xffffff. */
    color?: number;
    /** Outer glow strength. Default 2. */
    strength?: number;
    /** Glow distance in px (postFX-only knob, fixed at create). Default 8. */
    distance?: number;
}

/**
 * Put a persistent emissive glow on an object (postFX Glow — reads better
 * than Bloom on small sprites/particles). Idempotent per object; the
 * controller dies with the object. KEEP COUNTS LOW (≤10 per scene).
 */
export function bloom(obj: Phaser.GameObjects.GameObject, opts: BloomOpts = {}): void {
    const target = obj as FxTarget;
    if (!isWebGL(obj.scene) || !target.postFX || bloomed.has(obj)) {
        return;
    }
    const glow = target.postFX.addGlow(
        opts.color ?? 0xffffff,
        opts.strength ?? 2,
        0,
        false,
        0.1,
        opts.distance ?? 8
    );
    bloomed.set(obj, glow);
}

/**
 * M11 perf: cheap emissive halo — an additive-blend radial-gradient sprite
 * behind the emitter. ONE draw call, no postFX pipeline pass. Use this for
 * overworld emissives (many small lights); reserve bloom() for battle/intro
 * where counts stay ≤2-8. Measured: per-object Glow across ~10 overworld
 * objects cost ~15-20 fps on integrated graphics; halos are free.
 */
export function addHalo(
    scene: Phaser.Scene,
    x: number,
    y: number,
    color: number,
    radius = 10,
    alpha = 0.35
): Phaser.GameObjects.Image {
    const key = 'fx.halo.radial';
    if (!scene.textures.exists(key)) {
        const size = 32;
        const canvas = scene.textures.createCanvas(key, size, size);
        if (canvas) {
            const ctx = canvas.getContext();
            const g = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
            g.addColorStop(0, 'rgba(255,255,255,1)');
            g.addColorStop(0.5, 'rgba(255,255,255,0.35)');
            g.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, size, size);
            canvas.refresh();
        }
    }
    return scene.add
        .image(x, y, key)
        .setDisplaySize(radius * 2, radius * 2)
        .setTint(color)
        .setAlpha(alpha)
        .setBlendMode(Phaser.BlendModes.ADD);
}

/** Remove a bloom() glow from an object. Safe when none was applied. */
export function unbloom(obj: Phaser.GameObjects.GameObject): void {
    const target = obj as FxTarget;
    const glow = bloomed.get(obj);
    bloomed.delete(obj);
    if (glow && target.active && target.postFX) {
        target.postFX.remove(glow);
    }
}

export interface BloomSpikeOpts {
    color?: number;
    /** Peak outer strength. Default 4. */
    strength?: number;
    /** Full up-and-down duration in ms (dur()-scaled). Default 400. */
    ms?: number;
}

/**
 * One-shot bloom spike (flame breath, phase flash, battle entry): a glow that
 * swells to `strength` and back, then removes itself. Scene-hosted tween →
 * pause-frozen; turbo/Canvas → no-op.
 */
export function bloomSpike(
    scene: Phaser.Scene,
    obj: Phaser.GameObjects.GameObject,
    opts: BloomSpikeOpts = {}
): void {
    const target = obj as FxTarget;
    const ms = opts.ms ?? 400;
    if (!isWebGL(scene) || isTurbo() || dur(ms) <= 0 || !target.postFX) {
        return;
    }
    const glow = target.postFX.addGlow(opts.color ?? 0xffffff, 0, 0, false, 0.1, 8);
    scene.tweens.add({
        targets: glow,
        outerStrength: opts.strength ?? 4,
        duration: Math.max(1, Math.floor(dur(ms) / 2)),
        yoyo: true,
        ease: 'Sine.easeInOut',
        onComplete: () => {
            if (target.active && target.postFX) {
                target.postFX.remove(glow);
            }
        }
    });
}
