import { expect, test } from '@playwright/test';

import { BASE } from '../../vite.config';
import { collectPageErrors, SAVE_KEY, tap } from './helpers';

// M10 treasure chests: map-object chests open on interact, add loot to the
// inventory, persist via the autosaved flag chest.<room>#<i>.

test.describe.configure({ timeout: 45_000 });

async function hold(page: import('@playwright/test').Page, key: string, ms: number): Promise<void> {
    await page.keyboard.down(key);
    await page.waitForTimeout(ms);
    await page.keyboard.up(key);
}

test('tutorial chest in room1 opens, persists, and stays open', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await page.goto(`${BASE}?scene=overworld&room=room1-gate&turbo=1`);
    await expect(page.locator('body[data-poc-room="room1-gate"]')).toBeAttached({ timeout: 15_000 });

    // Spawn (15,22) → chest at (18,20): east then north, then interact.
    await hold(page, 'ArrowRight', 700);
    await hold(page, 'ArrowUp', 500);
    await tap(page, 'Enter');

    // The open autosaves the flag; poll the save blob for it.
    await page.waitForFunction(
        (key) => {
            const raw = window.localStorage.getItem(key);
            if (!raw) {
                return false;
            }
            const blob = JSON.parse(raw) as { flags?: Record<string, boolean> };
            return blob.flags?.['chest.room1-gate#0'] === true;
        },
        SAVE_KEY,
        { timeout: 5_000 }
    );

    // Loot landed: the herb stack in the save grew beyond the starting 4.
    const herbQty = await page.evaluate((key) => {
        const blob = JSON.parse(window.localStorage.getItem(key) as string) as {
            hero: { inventory: { itemId: string; qty: number }[] };
        };
        return blob.hero.inventory.find((s) => s.itemId === 'herb')?.qty ?? 0;
    }, SAVE_KEY);
    expect(herbQty).toBe(6); // 4 starting + chest herb×2

    // Re-interacting must not loot twice.
    await tap(page, 'Enter');
    await page.waitForTimeout(400);
    const herbQtyAfter = await page.evaluate((key) => {
        const blob = JSON.parse(window.localStorage.getItem(key) as string) as {
            hero: { inventory: { itemId: string; qty: number }[] };
        };
        return blob.hero.inventory.find((s) => s.itemId === 'herb')?.qty ?? 0;
    }, SAVE_KEY);
    expect(herbQtyAfter).toBe(6);

    expect(pageErrors).toEqual([]);
});
