import { expect, test } from '@playwright/test';

import { BASE } from '../../vite.config';

// M0 smoke (§9, §10): the built app boots at the Pages base path with zero
// 404s — the guard that catches absolute-path/base misconfig before deploy.
test('boots at the Pages base with zero 404s', async ({ page }) => {
    const notFound: string[] = [];
    page.on('response', (response) => {
        if (response.status() === 404) {
            notFound.push(response.url());
        }
    });

    await page.goto(BASE);

    await expect(page.locator('canvas')).toBeVisible();
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached();
    expect(notFound).toEqual([]);
});
