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

/** Upper bound on hero menu confirmations in a driven battle. */
export const MAX_TURNS = 20;

/** Snapshot of the observable battle dataset, for change detection. */
export function datasetSnapshot(page: Page): Promise<string> {
    return page.evaluate(() => {
        const d = document.body.dataset;
        return `${d.pocHp ?? ''}|${d.pocOutcome ?? ''}|${d.pocScene ?? ''}`;
    });
}

/** The battle is over once the scene switches or an outcome is recorded. */
export function battleEnded(page: Page): Promise<boolean> {
    return page.evaluate(() => {
        const d = document.body.dataset;
        return (
            d.pocScene !== 'Battle' ||
            d.pocOutcome === 'victory' ||
            d.pocOutcome === 'defeat' ||
            d.pocOutcome === 'fled'
        );
    });
}

/**
 * Wait for the battle dataset to move off `before`, then settle briefly. A
 * quiet turn (enemy tell, failed run — no hero damage) times out harmlessly.
 * The settle matters at battle end: the first observable change can be the
 * hero-HP tick that immediately precedes the outcome being recorded, and
 * without a beat for finish() to run, the caller's next Enter tap could land
 * in the follow-on scene (GameOver/Victory bind Enter → Title).
 */
export async function waitForBattleTick(page: Page, before: string): Promise<void> {
    await page
        .waitForFunction(
            (previous) => {
                const d = document.body.dataset;
                return `${d.pocHp ?? ''}|${d.pocOutcome ?? ''}|${d.pocScene ?? ''}` !== previous;
            },
            before,
            { timeout: 1500 }
        )
        .catch(() => undefined);
    await page.waitForTimeout(120);
}

/**
 * Confirm the battle menu once per loop iteration until the battle ends or
 * the iteration cap is hit. Menu order is fixed ATTACK/DEFEND/MAGIC/ITEM/RUN
 * with the cursor reset to ATTACK at the start of each hero turn, so a bare
 * Enter is always an attack — it can never open the MAGIC/ITEM submenus, and
 * single-enemy encounters auto-resolve targeting, so the drive cannot stall
 * on a submenu (battle-menu.ts implements X/Esc cancel if that ever changes).
 * Early Enter taps also advance the first-use Defend hint harmlessly.
 */
export async function driveBattle(page: Page, maxTurns: number = MAX_TURNS): Promise<void> {
    for (let turn = 0; turn < maxTurns; turn++) {
        if (await battleEnded(page)) {
            return;
        }
        const before = await datasetSnapshot(page);
        await tap(page, 'Enter');
        await waitForBattleTick(page, before);
    }
}

/**
 * Dismiss the first-use Defend hint deterministically. Debug jumps always
 * start from a fresh profile (bootstrap seeds empty flags), so the two-page
 * hint dialogue is guaranteed open once the battle HUD appears (the hooks
 * set body[data-poc-hp] in the same synchronous block that opens it).
 * Holding Enter rides the §8 hold-to-fast-forward path through every page —
 * under ?turbo=1 page text completes instantly and the hold threshold is
 * 1 ms — and the still-held key cannot trigger the command menu that opens
 * afterwards, because the menu only reacts to fresh keydown events.
 */
export async function dismissDefendHint(page: Page): Promise<void> {
    await page.locator('body[data-poc-hp]').waitFor({ state: 'attached', timeout: 15_000 });
    await page.keyboard.down('Enter');
    await page.waitForTimeout(500);
    await page.keyboard.up('Enter');
}
