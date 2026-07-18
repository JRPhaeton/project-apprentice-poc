import { readFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

import { BASE } from '../../vite.config';
import { collectPageErrors, SAVE_KEY, tap } from './helpers';

// M6 Intro coverage ("The Stolen Emberheart"): NEW GAME routes Title → Intro
// (four-page taunt, Enter/Z advance, X/Esc skip) → Overworld room1-gate,
// while CONTINUE and debug jumps bypass the Intro entirely. The Intro also
// plays the one-shot 'music.sting' (§6: data-poc-music is set only while a
// track is truly audible). All assertions ride the §10 dataset hooks.

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

// §10: audio is exercised in this file — no-gesture autoplay keeps the
// unlock deterministic in headless Chromium (same pattern as stage.spec).
test.use({ launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });

const validSaveRaw = readFileSync(
    new URL('../fixtures/saves/valid-v1.json', import.meta.url),
    'utf8'
);

/** Boot to the interactive Title at the plain Pages base (no debug params). */
async function bootToTitle(page: Page): Promise<void> {
    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('body[data-poc-scene="Title"]')).toBeAttached();
}

test('NEW GAME on a fresh profile enters the Intro; X skips to room1-gate', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    // Fresh browser context = no save, so Title's Enter IS "NEW GAME" (no
    // CONTINUE menu appears — Title.ts only opens the menu when a save
    // parses) and must route through the Intro before the Overworld.
    await bootToTitle(page);
    await tap(page, 'Enter');
    await expect(page.locator('body[data-poc-scene="Intro"]')).toBeAttached({ timeout: 10_000 });

    // X skips the whole intro at any point (Intro.update handles it even
    // mid-load), landing in the NEW GAME start room.
    await tap(page, 'x');
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 10_000
    });
    await expect(page.locator('body[data-poc-room="room1-gate"]')).toBeAttached();

    expect(pageErrors).toEqual([]);
});

test('NEW GAME Intro: Enter advances all four pages through to the Overworld', async ({
    page
}) => {
    const pageErrors = collectPageErrors(page);

    await bootToTitle(page);
    await tap(page, 'Enter');
    await expect(page.locator('body[data-poc-scene="Intro"]')).toBeAttached({ timeout: 10_000 });

    // Typewriter contract (Intro.update): while a page is still typing, an
    // Enter completes it; on a completed page, Enter advances. Worst case is
    // 2 effective taps per page × 4 pages = 8, plus slack for the 250 ms
    // post-create grace window that eats early presses — so a capped loop of
    // generous size, exiting as soon as the scene moves on. A cap exhaust
    // leaves pocScene='Intro' and fails the Overworld assertion below.
    for (let i = 0; i < 24; i++) {
        const left = await page.evaluate(() => document.body.dataset.pocScene !== 'Intro');
        if (left) {
            break;
        }
        await tap(page, 'Enter');
        await page.waitForTimeout(120);
    }

    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 10_000
    });
    await expect(page.locator('body[data-poc-room="room1-gate"]')).toBeAttached();

    expect(pageErrors).toEqual([]);
});

test('CONTINUE with an existing save bypasses the Intro entirely', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    // Record EVERY data-poc-scene value from before any app code runs — a
    // MutationObserver cannot miss a transition the way interval sampling
    // could, so "the Intro never appeared" is asserted deterministically.
    await page.addInitScript(() => {
        const w = window as unknown as { __pocSceneLog: string[] };
        w.__pocSceneLog = [];
        new MutationObserver(() => {
            const scene = document.body.dataset.pocScene;
            if (scene && w.__pocSceneLog[w.__pocSceneLog.length - 1] !== scene) {
                w.__pocSceneLog.push(scene);
            }
            // Observe the document node: it exists at init-script time
            // (documentElement does NOT yet) and subtree covers <body>.
        }).observe(document, {
            subtree: true,
            attributes: true,
            attributeFilter: ['data-poc-scene']
        });
    });
    // Seed the autosave slot before load (resilience.spec pattern).
    await page.addInitScript(
        ([key, raw]) => {
            window.localStorage.setItem(key, raw);
        },
        [SAVE_KEY, validSaveRaw] as const
    );

    await bootToTitle(page);

    // With a valid save, Enter opens the CONTINUE/NEW GAME MenuList with the
    // cursor reset to the FIRST entry (CONTINUE — battle-menu.ts contract),
    // so a second Enter confirms CONTINUE.
    await tap(page, 'Enter');
    await page.waitForTimeout(150);
    await tap(page, 'Enter');

    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 10_000
    });
    // CONTINUE restores the SAVED room (fixture: room2-forest), never the
    // NEW GAME start room — proving the save actually applied.
    await expect(page.locator('body[data-poc-room="room2-forest"]')).toBeAttached();

    // Direct Title → Overworld arrival: no Intro (and nothing else) between.
    const sceneLog = await page.evaluate(
        () => (window as unknown as { __pocSceneLog: string[] }).__pocSceneLog
    );
    expect(sceneLog).not.toContain('Intro');
    expect(sceneLog).toEqual(['Title', 'Overworld']);

    expect(pageErrors).toEqual([]);
});

test('Intro plays the one-shot music.sting', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await bootToTitle(page);
    // The Enter that starts NEW GAME is the real trusted gesture that
    // unlocks audio; the launch flag above removes the policy variable.
    await tap(page, 'Enter');
    await expect(page.locator('body[data-poc-scene="Intro"]')).toBeAttached({ timeout: 10_000 });

    // hooks.ts sets data-poc-music ONLY once playback truly starts, so this
    // proves the sting OGG resolved, decoded, and began playing. The sting
    // runs 10.6 s, so the 5 s wait cannot race its one-shot COMPLETE clear.
    await expect(page.locator('body[data-poc-music="music.sting"]')).toBeAttached({
        timeout: 5_000
    });

    expect(pageErrors).toEqual([]);
});
