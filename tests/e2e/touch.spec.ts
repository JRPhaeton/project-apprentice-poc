import { expect, test, type Page } from '@playwright/test';

import { BASE } from '../../vite.config';
import { battleEnded, collectPageErrors, datasetSnapshot, MAX_TURNS, waitForBattleTick } from './helpers';

// M7 touch-controls coverage (§10): the input bus + touch UI driven through a
// touch-enabled context. Phaser gates the touch chrome on device.input.touch
// ('ontouchstart' in window / navigator.maxTouchPoints), which Playwright's
// hasTouch flips on — verified: body[data-poc-touch="1"] appears whenever the
// UIOverlay runs in this context. The viewport is landscape phone-ish so the
// once-per-session portrait rotate hint never shows. Taps ride the real
// touchscreen API; press-and-holds (d-pad steering, A-button fast-forward)
// use mouse down/up — Phaser's mouse pointer drives the same zones, which is
// exactly the "desktop clicks ride the bus for free" contract of touch.ts.

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

test.use({ hasTouch: true, viewport: { width: 851, height: 393 } });

/**
 * Map a point in the 256×224 internal space to page coordinates via the
 * canvas bounding box. Scale.FIT scales the canvas element itself (letterbox
 * margins live outside it), so the box maps 1:1 onto the internal space.
 */
async function internalPoint(page: Page, ix: number, iy: number): Promise<{ x: number; y: number }> {
    const box = await page.locator('canvas').boundingBox();
    if (!box) {
        throw new Error('game canvas is not visible');
    }
    return { x: box.x + (ix / 256) * box.width, y: box.y + (iy / 224) * box.height };
}

/** Real touch tap (touchstart+touchend → Phaser pointerdown/up) at an internal point. */
async function tapInternal(page: Page, ix: number, iy: number): Promise<void> {
    const point = await internalPoint(page, ix, iy);
    await page.touchscreen.tap(point.x, point.y);
}

/** Press-and-hold at an internal point for `ms` (mouse pointer, see header). */
async function holdInternal(page: Page, ix: number, iy: number, ms: number): Promise<void> {
    const point = await internalPoint(page, ix, iy);
    await page.mouse.move(point.x, point.y);
    await page.mouse.down();
    await page.waitForTimeout(ms);
    await page.mouse.up();
}

// Touch-zone geometry from src/systems/touch.ts (d-pad center (30,188), 44px
// active square, dominant-axis resolve; A at (228,190)) — the arm points sit
// 12px from center, inside the zone and well past the 3px dead-zone.
const DPAD_ARM = {
    up: { x: 30, y: 176 },
    down: { x: 30, y: 200 },
    right: { x: 42, y: 188 }
} as const;
const BTN_A = { x: 228, y: 190 };

/** Hold the d-pad on one arm for `ms` (hero speed 80 px/s ≈ 0.08 px/ms). */
async function holdDpad(page: Page, arm: keyof typeof DPAD_ARM, ms: number): Promise<void> {
    await holdInternal(page, DPAD_ARM[arm].x, DPAD_ARM[arm].y, ms);
}

function currentRoom(page: Page): Promise<string | undefined> {
    return page.evaluate(() => document.body.dataset.pocRoom);
}

// (a) The touch UI appears, driven end-to-end by taps alone: Title tap
// anywhere = NEW GAME (fresh profile), Intro SKIP tap zone (bottom-right
// 56×28 at the (256,224) corner, active even mid-load), Overworld runs the
// UIOverlay which builds the touch chrome and sets the §10 hook.
test('tap-through: Title tap → Intro SKIP tap → Overworld with the touch UI active', async ({
    page
}) => {
    const pageErrors = collectPageErrors(page);

    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('body[data-poc-scene="Title"]')).toBeAttached();
    // Title stops the UIOverlay, so the touch hook must be absent here.
    await expect(page.locator('body[data-poc-touch]')).not.toBeAttached();

    // Tap anywhere = Enter (Title's POINTER_UP handler); fresh context has no
    // save, so this IS "NEW GAME" and routes through the Intro.
    await tapInternal(page, 128, 112);
    await expect(page.locator('body[data-poc-scene="Intro"]')).toBeAttached({ timeout: 10_000 });

    // SKIP zone center (228,210): skips the whole taunt, even mid-load.
    await tapInternal(page, 228, 210);
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 10_000
    });
    await expect(page.locator('body[data-poc-room="room1-gate"]')).toBeAttached();
    await expect(page.locator('body[data-poc-touch="1"]')).toBeAttached({ timeout: 5_000 });

    expect(pageErrors).toEqual([]);
});

// (b) The virtual d-pad moves the hero: the M4 exit-walk (stage.spec.ts),
// d-pad edition. Map facts (room1-gate.json): spawn (15,22), exit at column
// 31 spanning rows 12-14, obstacle-free path. Held up ≈1.8s lands mid-window;
// east bursts cross to the exit; pocRoom polled between bursts ends the walk
// the moment the transition fires. Two vertical sweep nudges absorb drift.
test('touch d-pad: held walk crosses room1-gate into room2-forest', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto(`${BASE}?scene=overworld&room=room1-gate&turbo=1`);
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 15_000
    });
    await expect(page.locator('body[data-poc-room="room1-gate"]')).toBeAttached();
    await expect(page.locator('body[data-poc-touch="1"]')).toBeAttached({ timeout: 5_000 });

    const walkEast = async (bursts: number): Promise<boolean> => {
        for (let i = 0; i < bursts; i++) {
            if ((await currentRoom(page)) === 'room2-forest') {
                return true;
            }
            await holdDpad(page, 'right', 500);
        }
        return (await currentRoom(page)) === 'room2-forest';
    };

    await holdDpad(page, 'up', 1800);
    let switched = await walkEast(10);
    if (!switched) {
        // Drifted above the exit rows: sweep one row down and push again.
        await holdDpad(page, 'down', 300);
        switched = await walkEast(3);
    }
    if (!switched) {
        // Or below them: net two rows up from the first sweep.
        await holdDpad(page, 'up', 600);
        switched = await walkEast(3);
    }

    expect(switched).toBe(true);
    await expect(page.locator('body[data-poc-room="room2-forest"]')).toBeAttached();
    expect(pageErrors).toEqual([]);
});

// (c) Touch battle: debug-jump spider fight driven by touch alone. Holding
// the A button rides hold-to-fast-forward through the first-use Defend hint
// (bus confirm-held, the dismissDefendHint pattern), then direct taps on the
// ATTACK menu row (MenuList at (8,108) w64: row 0 zone spans y 111-121, so
// its center is (40,116)) confirm each turn — a row tap moves the cursor AND
// confirms in one touch. Seed 7 is the known attack-only victory.
test('touch battle: A-button hold clears the hint, ATTACK row taps reach victory', async ({
    page
}) => {
    const pageErrors = collectPageErrors(page);

    await page.goto(`${BASE}?scene=battle&enemy=spider&seed=7&turbo=1`);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('body[data-poc-touch="1"]')).toBeAttached({ timeout: 10_000 });

    // The hint dialogue is guaranteed open once the HUD hook appears; the
    // held A fast-forwards both pages (turbo: instant text, 1 ms threshold).
    await page.locator('body[data-poc-hp]').waitFor({ state: 'attached', timeout: 15_000 });
    await holdInternal(page, BTN_A.x, BTN_A.y, 600);

    // Tap ATTACK until the battle ends (cap = the shared driveBattle bound).
    // A tap that lands while the menu is closed (enemy phase) hits nothing
    // and the tick-wait times out harmlessly, so the loop cannot wedge.
    for (let turn = 0; turn < MAX_TURNS; turn++) {
        if (await battleEnded(page)) {
            break;
        }
        const before = await datasetSnapshot(page);
        await tapInternal(page, 40, 116);
        await waitForBattleTick(page, before);
    }

    await expect(page.locator('body[data-poc-outcome="victory"]')).toBeAttached({
        timeout: 10_000
    });
    expect(pageErrors).toEqual([]);
});
