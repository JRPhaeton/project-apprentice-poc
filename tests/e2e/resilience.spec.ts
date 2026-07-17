import { readFileSync } from 'node:fs';

import { expect, test, type Page } from '@playwright/test';

import { BASE } from '../../vite.config';
import { collectConsoleErrors, collectPageErrors, SAVE_KEY } from './helpers';

// §10/§11 resilience: a corrupt, future-version, or unavailable save store
// must never crash boot — discard-on-mismatch lands the player on a fresh
// Title, and blocked storage falls back to in-memory saves.

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

const corruptRaw = readFileSync(new URL('../fixtures/saves/corrupt.txt', import.meta.url), 'utf8');
const futureRaw = readFileSync(new URL('../fixtures/saves/future-version.json', import.meta.url), 'utf8');

/** Seed the autosave slot before any app code runs. */
async function seedSave(page: Page, raw: string): Promise<void> {
    await page.addInitScript(
        ([key, value]) => {
            try {
                window.localStorage.setItem(key, value);
            } catch {
                // Storage unavailable in this context — nothing to seed.
            }
        },
        [SAVE_KEY, raw] as const
    );
}

test('corrupt save blob: fresh Title, zero uncaught errors', async ({ page }) => {
    const pageErrors = collectPageErrors(page);
    const consoleErrors = collectConsoleErrors(page);
    await seedSave(page, corruptRaw);

    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('body[data-poc-scene="Title"]')).toBeAttached();

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
});

test('future-version save blob: fresh Title, zero uncaught errors', async ({ page }) => {
    const pageErrors = collectPageErrors(page);
    const consoleErrors = collectConsoleErrors(page);
    await seedSave(page, futureRaw);

    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('body[data-poc-scene="Title"]')).toBeAttached();

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
});

test('storage blocked: localStorage access throws, game still reaches Title', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    // §11: emulate storage-disabled (Safari private-mode style) by making
    // the localStorage accessor itself throw before any app code runs — the
    // in-memory fallback must carry the game to a playable Title.
    await page.addInitScript(() => {
        Object.defineProperty(window, 'localStorage', {
            configurable: true,
            get() {
                throw new DOMException('The operation is insecure.', 'SecurityError');
            }
        });
    });

    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    await expect(page.locator('body[data-poc-scene="Title"]')).toBeAttached();

    expect(pageErrors).toEqual([]);
});
