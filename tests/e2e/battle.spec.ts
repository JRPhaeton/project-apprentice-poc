import { expect, test } from '@playwright/test';

import { BASE } from '../../vite.config';
import {
    battleEnded,
    collectPageErrors,
    datasetSnapshot,
    driveBattle,
    SAVE_KEY,
    tap,
    waitForBattleTick
} from './helpers';

// §10: debug-jump battle path against the --mode e2e artifact. The debug
// hooks (?scene=battle&enemy=spider, &seed=, &turbo=1) only resolve in that
// build (§4 of docs/PLAN.md); playwright.config.ts already builds it.
// driveBattle/battleEnded/datasetSnapshot live in helpers.ts (shared with
// roster.spec.ts since M3).

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

test('debug-jump spider battle: ATTACK to victory, autosave survives reload', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto(`${BASE}?scene=battle&enemy=spider&seed=7&turbo=1`);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 15_000 });

    await driveBattle(page);

    await expect(page.locator('body[data-poc-outcome="victory"]')).toBeAttached({ timeout: 10_000 });

    // §4: autosave on victory. SAVE_KEY is an assumed constant (helpers.ts).
    const savedRaw = await page.evaluate((key) => window.localStorage.getItem(key), SAVE_KEY);
    expect(savedRaw).not.toBeNull();

    // Reload at the plain base: the save must survive into a fresh Title
    // boot (the continue path) as valid JSON with v === 1.
    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    const persistedRaw = await page.evaluate((key) => window.localStorage.getItem(key), SAVE_KEY);
    expect(persistedRaw).not.toBeNull();
    const blob = JSON.parse(persistedRaw as string) as { v?: number };
    expect(blob.v).toBe(1);

    expect(pageErrors).toEqual([]);
});

test('defend path: DEFEND then ATTACK still progresses to an end, no crash', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto(`${BASE}?scene=battle&enemy=spider&seed=13&turbo=1`);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 15_000 });

    // Turn 1: DEFEND — one ArrowDown from ATTACK in the fixed menu order.
    // (The first-use Defend hint dialogue may be open on a fresh profile;
    // extra Enter taps advance it harmlessly before the menu.)
    await tap(page, 'Enter');
    await tap(page, 'Enter');
    const before = await datasetSnapshot(page);
    await tap(page, 'ArrowDown');
    await tap(page, 'Enter');
    await waitForBattleTick(page, before);

    // Then keep confirming turns. Per §10 this test asserts progress and a
    // clean end only — victory or defeat are both acceptable outcomes.
    await driveBattle(page);

    expect(await battleEnded(page)).toBe(true);
    expect(pageErrors).toEqual([]);
});
