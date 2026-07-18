import Phaser from 'phaser';

import type { ArtManifest } from '../core/contracts/data';
import artManifestJson from '../data/art-manifest.json';
import { markTouch } from './hooks';
import { getInputBus } from './input-bus';
import { addUiText } from './ui';

/**
 * M7 touch controls, created inside the always-on UIOverlay ONLY when the
 * device reports touch (Playwright touch emulation included). All controls
 * emit semantic input-bus events — no scene ever reads raw pointers from
 * here. Layout at the 256×224 internal res, translucent (0.55 idle / 0.85
 * pressed):
 *   - D-pad bottom-left (44px active square): 8-way resolved to 4-dir by
 *     dominant axis, sliding the thumb re-resolves without lifting.
 *   - A bottom-right (confirm, also drives hold-to-fast-forward), B left of
 *     A (cancel), small pause + fullscreen buttons top-right.
 * Art: manifest 'ui.touch' (five 32×32 frames: dpad base / pressed-arm
 * overlay pointing UP (rotated for other dirs) / A / B / pause); missing
 * sheet degrades to generated chrome-style graphics. The fullscreen glyph is
 * always generated (no frame). Multi-touch via input.addPointer; per-control
 * pointer-id tracking keeps simultaneous d-pad + button presses independent.
 */

const TOUCH_KEY = 'ui.touch';

const ALPHA_IDLE = 0.55;
const ALPHA_HELD = 0.85;
const DEPTH = 400; // above HUD (99-102) and the dialogue tap zone (150)

// Layout (256×224): d-pad centered bottom-left, A bottom-right, B left of A,
// pause/fullscreen small in the top-right beside the HUD strip.
const DPAD = { x: 30, y: 188, zone: 44, dead: 3 };
const BTN_A = { x: 228, y: 190, zone: 36 };
const BTN_B = { x: 188, y: 190, zone: 36 };
const PAUSE = { x: 246, y: 26, size: 16, zone: 24 };
const FULLSCREEN = { x: 224, y: 26, size: 16, zone: 24 };

const CHROME_FILL = 0x241c3c; // SNES-purple chrome, matches the panel kit
const CHROME_LINE = 0x8080a0;
const CHROME_HILITE = 0xffff80;

/** Session flag: the portrait rotate hint shows at most once per page load. */
let rotateHintShown = false;

/** True when the runtime reports a touch input source (§ M7 gate). */
export function isTouchDevice(scene: Phaser.Scene): boolean {
    return scene.sys.game.device.input.touch;
}

/**
 * Queue the touch-button sheet (Boot.preload, alongside the UI chrome). Uses
 * the static manifest import — Boot runs before registry defs exist. Missing
 * entry/file degrades to the generated-graphics buttons below.
 */
export function queueTouchAssets(load: Phaser.Loader.LoaderPlugin): void {
    const entry = (artManifestJson as ArtManifest)[TOUCH_KEY];
    if (entry && !load.scene.textures.exists(TOUCH_KEY)) {
        load.spritesheet(TOUCH_KEY, entry.file, {
            frameWidth: entry.frameWidth,
            frameHeight: entry.frameHeight
        });
    }
}

/** Generate a 32×32 fallback texture via a one-off Graphics draw. */
function genTexture(
    scene: Phaser.Scene,
    key: string,
    draw: (g: Phaser.GameObjects.Graphics) => void
): void {
    if (scene.textures.exists(key)) {
        return;
    }
    const g = scene.add.graphics();
    draw(g);
    g.generateTexture(key, 32, 32);
    g.destroy();
}

function genDpadBase(g: Phaser.GameObjects.Graphics): void {
    g.fillStyle(CHROME_FILL, 1);
    g.fillRect(10, 1, 12, 30); // vertical arm
    g.fillRect(1, 10, 30, 12); // horizontal arm
    g.lineStyle(1, CHROME_LINE, 1);
    g.strokeRect(10, 1, 12, 30);
    g.strokeRect(1, 10, 30, 12);
}

function genDpadPress(g: Phaser.GameObjects.Graphics): void {
    // Single highlighted arm pointing UP; the sprite is rotated per direction.
    g.fillStyle(CHROME_HILITE, 0.9);
    g.fillRect(12, 2, 8, 10);
}

function genRoundButton(g: Phaser.GameObjects.Graphics): void {
    g.fillStyle(CHROME_FILL, 1);
    g.fillCircle(16, 16, 13);
    g.lineStyle(1, CHROME_LINE, 1);
    g.strokeCircle(16, 16, 13);
}

function genPause(g: Phaser.GameObjects.Graphics): void {
    g.fillStyle(CHROME_FILL, 1);
    g.fillRect(2, 2, 28, 28);
    g.lineStyle(1, CHROME_LINE, 1);
    g.strokeRect(2, 2, 28, 28);
    g.fillStyle(0xe0e0e0, 1);
    g.fillRect(11, 9, 4, 14); // ‖ pause bars
    g.fillRect(17, 9, 4, 14);
}

function genFullscreen(g: Phaser.GameObjects.Graphics): void {
    g.fillStyle(CHROME_FILL, 1);
    g.fillRect(2, 2, 28, 28);
    g.lineStyle(1, CHROME_LINE, 1);
    g.strokeRect(2, 2, 28, 28);
    g.lineStyle(2, 0xe0e0e0, 1);
    // ⛶-style corner brackets.
    g.beginPath();
    g.moveTo(8, 13);
    g.lineTo(8, 8);
    g.lineTo(13, 8);
    g.moveTo(19, 8);
    g.lineTo(24, 8);
    g.lineTo(24, 13);
    g.moveTo(24, 19);
    g.lineTo(24, 24);
    g.lineTo(19, 24);
    g.moveTo(13, 24);
    g.lineTo(8, 24);
    g.lineTo(8, 19);
    g.strokePath();
}

/** A sheet frame when the Assets-lane png landed, else a generated texture. */
function touchSprite(
    scene: Phaser.Scene,
    x: number,
    y: number,
    frame: number,
    genKey: string,
    genDraw: (g: Phaser.GameObjects.Graphics) => void
): Phaser.GameObjects.Sprite {
    if (scene.textures.exists(TOUCH_KEY)) {
        return scene.add.sprite(x, y, TOUCH_KEY, frame);
    }
    genTexture(scene, genKey, genDraw);
    return scene.add.sprite(x, y, genKey);
}

interface FadeTarget {
    setAlpha(alpha: number): unknown;
}

/**
 * Build the touch UI inside a scene (the UIOverlay). Buttons emit bus events
 * on pointerdown (parity with keydown responsiveness); fullscreen toggles on
 * pointerup (user-gesture requirement). Every control tracks its own pointer
 * id so multi-touch (d-pad + A, etc.) works; releases anywhere on screen end
 * a press so a thumb sliding off a button never leaves it stuck.
 */
export function createTouchControls(scene: Phaser.Scene): void {
    const bus = getInputBus(scene.game);
    const input = scene.input;

    // Up to 4 concurrent pointers (d-pad + A + B + one spare). addPointer is
    // game-global — top up instead of stacking on every UIOverlay relaunch.
    const missing = 4 - input.manager.pointersTotal;
    if (missing > 0) {
        input.addPointer(missing);
    }

    // Releases-anywhere: pointer-id → release handler, run on any up event.
    const releases = new Map<number, () => void>();
    const onAnyUp = (pointer: Phaser.Input.Pointer): void => {
        const release = releases.get(pointer.id);
        if (release) {
            releases.delete(pointer.id);
            release();
        }
    };
    input.on(Phaser.Input.Events.POINTER_UP, onAnyUp);
    input.on(Phaser.Input.Events.POINTER_UP_OUTSIDE, onAnyUp);

    // ---------------------------------------------------------------- d-pad
    const dpadBase = touchSprite(scene, DPAD.x, DPAD.y, 0, 'ui.touch.gen.dpad', genDpadBase)
        .setDepth(DEPTH)
        .setAlpha(ALPHA_IDLE);
    const dpadPress = touchSprite(scene, DPAD.x, DPAD.y, 1, 'ui.touch.gen.dpad-press', genDpadPress)
        .setDepth(DEPTH + 1)
        .setAlpha(ALPHA_HELD)
        .setVisible(false);

    const resolveDpad = (px: number, py: number): void => {
        const dx = px - DPAD.x;
        const dy = py - DPAD.y;
        if (Math.abs(dx) < DPAD.dead && Math.abs(dy) < DPAD.dead) {
            bus.setDir(0, 0);
        } else if (Math.abs(dx) >= Math.abs(dy)) {
            // Dominant axis wins: 8-way thumb input resolves to 4-dir.
            bus.setDir(dx < 0 ? -1 : 1, 0);
        } else {
            bus.setDir(0, dy < 0 ? -1 : 1);
        }
        const dir = bus.getDir();
        if (dir.x === 0 && dir.y === 0) {
            dpadPress.setVisible(false);
        } else {
            // Frame 1 points UP; rotate for the other directions.
            dpadPress.setVisible(true).setAngle(dir.y === -1 ? 0 : dir.y === 1 ? 180 : dir.x === 1 ? 90 : 270);
        }
    };

    let dpadPointer = -1;
    const dpadZone = scene.add
        .zone(DPAD.x, DPAD.y, DPAD.zone, DPAD.zone)
        .setDepth(DEPTH + 2)
        .setInteractive();
    dpadZone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_DOWN, (pointer: Phaser.Input.Pointer) => {
        if (dpadPointer !== -1) {
            return;
        }
        dpadPointer = pointer.id;
        dpadBase.setAlpha(ALPHA_HELD);
        resolveDpad(pointer.x, pointer.y);
        releases.set(pointer.id, () => {
            dpadPointer = -1;
            dpadBase.setAlpha(ALPHA_IDLE);
            dpadPress.setVisible(false);
            bus.setDir(0, 0);
        });
    });
    // Sliding the thumb re-resolves the direction without lifting — tracked
    // scene-wide so steering keeps working outside the zone bounds.
    const onMove = (pointer: Phaser.Input.Pointer): void => {
        if (pointer.id === dpadPointer && pointer.isDown) {
            resolveDpad(pointer.x, pointer.y);
        }
    };
    input.on(Phaser.Input.Events.POINTER_MOVE, onMove);

    // -------------------------------------------------------------- buttons
    /** Wire a zone as a press-tracked button with alpha feedback. */
    const wireButton = (
        x: number,
        y: number,
        zoneSize: number,
        visuals: FadeTarget[],
        onDown?: () => void,
        onUp?: () => void
    ): void => {
        const zone = scene.add.zone(x, y, zoneSize, zoneSize).setDepth(DEPTH + 2).setInteractive();
        let pid = -1;
        zone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_DOWN, (pointer: Phaser.Input.Pointer) => {
            if (pid !== -1) {
                return;
            }
            pid = pointer.id;
            for (const v of visuals) {
                v.setAlpha(ALPHA_HELD);
            }
            onDown?.();
            releases.set(pointer.id, () => {
                pid = -1;
                for (const v of visuals) {
                    v.setAlpha(ALPHA_IDLE);
                }
                onUp?.();
            });
        });
    };

    /** Sprite (sheet frame or generated) + fallback letter label. */
    const button = (
        x: number,
        y: number,
        frame: number,
        genKey: string,
        genDraw: (g: Phaser.GameObjects.Graphics) => void,
        label: string,
        size?: number
    ): FadeTarget[] => {
        const sprite = touchSprite(scene, x, y, frame, genKey, genDraw)
            .setDepth(DEPTH)
            .setAlpha(ALPHA_IDLE);
        if (size !== undefined) {
            sprite.setDisplaySize(size, size);
        }
        const visuals: FadeTarget[] = [sprite];
        if (!scene.textures.exists(TOUCH_KEY) && label) {
            visuals.push(
                addUiText(scene, x, y, label, { color: 0xe0e0e0 })
                    .setOrigin(0.5)
                    .setDepth(DEPTH + 1)
                    .setAlpha(ALPHA_IDLE)
            );
        }
        return visuals;
    };

    wireButton(
        BTN_A.x,
        BTN_A.y,
        BTN_A.zone,
        button(BTN_A.x, BTN_A.y, 2, 'ui.touch.gen.a', genRoundButton, 'A'),
        () => {
            bus.setConfirmHeld(true);
            bus.press('confirm');
        },
        () => bus.setConfirmHeld(false)
    );
    wireButton(
        BTN_B.x,
        BTN_B.y,
        BTN_B.zone,
        button(BTN_B.x, BTN_B.y, 3, 'ui.touch.gen.b', genRoundButton, 'B'),
        () => bus.press('cancel')
    );
    // M9 clarity: contextual caption under B — it OPENS the field menu in the
    // overworld and backs out everywhere else. Reads the pocScene hook so it
    // tracks scene switches without coupling to scene internals.
    const bCaption = addUiText(scene, BTN_B.x, BTN_B.y + 21, 'BACK', { color: 0xc0c0d0 })
        .setOrigin(0.5)
        .setDepth(DEPTH + 1)
        .setAlpha(0.8);
    let bCaptionText = 'BACK';
    scene.events.on(Phaser.Scenes.Events.UPDATE, () => {
        const wanted = document.body.dataset.pocScene === 'Overworld' ? 'MENU' : 'BACK';
        if (wanted !== bCaptionText) {
            bCaptionText = wanted;
            bCaption.setText(wanted);
        }
    });
    wireButton(
        PAUSE.x,
        PAUSE.y,
        PAUSE.zone,
        button(PAUSE.x, PAUSE.y, 4, 'ui.touch.gen.pause', genPause, '', PAUSE.size),
        () => bus.press('pause')
    );
    if (scene.scale.fullscreen.available) {
        // Always the generated glyph — the sheet has no fullscreen frame. The
        // toggle MUST run in the pointerUP handler (browser user gesture).
        genTexture(scene, 'ui.touch.gen.fs', genFullscreen);
        const fs = scene.add
            .sprite(FULLSCREEN.x, FULLSCREEN.y, 'ui.touch.gen.fs')
            .setDepth(DEPTH)
            .setAlpha(ALPHA_IDLE)
            .setDisplaySize(FULLSCREEN.size, FULLSCREEN.size);
        wireButton(FULLSCREEN.x, FULLSCREEN.y, FULLSCREEN.zone, [fs], undefined, () => {
            if (scene.scale.isFullscreen) {
                scene.scale.stopFullscreen();
            } else {
                scene.scale.startFullscreen();
            }
        });
    }

    maybeShowRotateHint(scene);
    markTouch(true); // §10 E2E observability: body[data-poc-touch="1"]

    scene.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
        // Never leak held state past the overlay's life (Title/GameOver stop
        // it); scene-owned listeners/objects die with the scene itself.
        bus.setDir(0, 0);
        bus.setConfirmHeld(false);
        markTouch(false);
    });
}

/**
 * Portrait hint: touch device held portrait → a small non-blocking toast,
 * once per session; dismissed by rotating to landscape or after 4s.
 */
function maybeShowRotateHint(scene: Phaser.Scene): void {
    if (rotateHintShown || window.innerHeight <= window.innerWidth) {
        return;
    }
    rotateHintShown = true;
    const hint = addUiText(scene, 128, 64, 'ROTATE FOR BEST VIEW', { color: 0xffff80 })
        .setOrigin(0.5)
        .setDepth(500);
    const dismiss = (): void => {
        window.removeEventListener('resize', onResize);
        if (hint.active) {
            hint.destroy();
        }
    };
    const onResize = (): void => {
        if (window.innerHeight <= window.innerWidth) {
            dismiss();
        }
    };
    window.addEventListener('resize', onResize);
    scene.time.delayedCall(4000, dismiss);
    scene.events.once(Phaser.Scenes.Events.SHUTDOWN, dismiss);
}
