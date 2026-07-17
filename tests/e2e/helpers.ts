import type { Page } from '@playwright/test';

/**
 * ASSUMED CONSTANT (orchestrator reconciles at integration): the Engine
 * lane's autosave localStorage key from src/systems/storage.ts. QA cannot
 * read that file mid-round; if the Engine lane picked a different key, this
 * is the single place to fix it.
 */
export const SAVE_KEY = 'poc-save';

/**
 * Collect uncaught page exceptions (§10 resilience: "zero unhandled
 * exceptions"). Attach before navigation; assert the array is empty at the
 * end of the test.
 */
export function collectPageErrors(page: Page): string[] {
    const errors: string[] = [];
    page.on('pageerror', (error) => {
        errors.push(String(error));
    });
    return errors;
}

/**
 * Frame-safe key tap. Playwright's `keyboard.press()` fires keydown+keyup
 * within the same animation frame, which Phaser's per-frame JustDown polling
 * can miss entirely (verified at M2 integration). Holding the key across a
 * few frames matches real human input and registers reliably.
 */
export async function tap(page: Page, key: string): Promise<void> {
    await page.keyboard.down(key);
    await page.waitForTimeout(80);
    await page.keyboard.up(key);
}

/** Collect console.error output (§10 resilience: "no console error"). */
export function collectConsoleErrors(page: Page): string[] {
    const errors: string[] = [];
    page.on('console', (message) => {
        if (message.type() === 'error') {
            errors.push(message.text());
        }
    });
    return errors;
}
