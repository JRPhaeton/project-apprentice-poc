import { expect, test } from '@playwright/test';

import { BASE } from '../../vite.config';
import { collectPageErrors, driveBattle, tap } from './helpers';

// M9 field menu (X/Esc or touch B in the Overworld): view inventory, use
// heal items/spells outside battle. Observability: body[data-poc-menu].

test.describe.configure({ timeout: 45_000 });

test('field menu opens with X, closes with X, blocks nothing after', async ({ page }) => {
    const pageErrors = collectPageErrors(page);
    await page.goto(`${BASE}?scene=overworld&room=room1-gate&turbo=1`);
    await expect(page.locator('body[data-poc-room="room1-gate"]')).toBeAttached({ timeout: 15_000 });

    await tap(page, 'x');
    await expect(page.locator('body[data-poc-menu="field"]')).toBeAttached({ timeout: 5_000 });

    await tap(page, 'x');
    await expect(page.locator('body[data-poc-menu="field"]')).not.toBeAttached({ timeout: 5_000 });
    expect(pageErrors).toEqual([]);
});

test('herb heals from the field menu after battle damage', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    // Take real damage: spider battle to victory (seed 7 lands the 2× bite).
    await page.goto(`${BASE}?scene=battle&enemy=spider&seed=7&turbo=1`);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 15_000 });
    await driveBattle(page);
    await expect(page.locator('body[data-poc-outcome="victory"]')).toBeAttached({ timeout: 10_000 });
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({ timeout: 10_000 });

    const hpBefore = Number(
        await page.evaluate(() => document.body.dataset.pocHp ?? '0')
    );
    expect(hpBefore).toBeLessThan(42); // the bite landed

    // X → ITEM (first row) → first item (Herb, enabled below max HP).
    await tap(page, 'x');
    await expect(page.locator('body[data-poc-menu="field"]')).toBeAttached({ timeout: 5_000 });
    await tap(page, 'Enter');
    await page.waitForTimeout(300);
    await tap(page, 'Enter');

    await page.waitForFunction(
        (before) => Number(document.body.dataset.pocHp ?? '0') > before,
        hpBefore,
        { timeout: 5_000 }
    );

    await tap(page, 'x'); // close menu
    await expect(page.locator('body[data-poc-menu="field"]')).not.toBeAttached({ timeout: 5_000 });
    expect(pageErrors).toEqual([]);
});
