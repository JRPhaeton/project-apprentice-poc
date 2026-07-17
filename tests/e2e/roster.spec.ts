import { expect, test, type Page } from '@playwright/test';

import { BASE } from '../../vite.config';
import {
    battleEnded,
    collectPageErrors,
    datasetSnapshot,
    dismissDefendHint,
    driveBattle,
    tap,
    waitForBattleTick
} from './helpers';

// §9 M3 roster coverage: every confirmed mob + the boss driven end-to-end
// against the --mode e2e artifact via the §4 debug jump (?scene=battle&
// enemy=<suffix> resolves encounter 'enc-<suffix>'), plus the MAGIC and RUN
// command paths. Placeholder art is expected — these assert battle LOGIC
// (signature turns firing without a wedge, clean ends, correct exit scenes)
// and zero unhandled exceptions, never pixels.

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

/** Debug-jump URL: fixed seed + turbo everywhere for determinism (§10). */
function battleUrl(enemy: string, seed: number): string {
    return `${BASE}?scene=battle&enemy=${enemy}&seed=${seed}&turbo=1`;
}

async function enterBattle(page: Page, enemy: string, seed: number): Promise<void> {
    await page.goto(battleUrl(enemy, seed));
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 15_000 });
}

function outcomeOf(page: Page): Promise<string | undefined> {
    return page.evaluate(() => document.body.dataset.pocOutcome);
}

/** A clean end: outcome recorded, then the flow leaves the Battle scene. */
async function expectCleanEnd(page: Page): Promise<void> {
    expect(await battleEnded(page)).toBe(true);
    await expect(page.locator('body[data-poc-outcome]')).toBeAttached({ timeout: 5_000 });
    expect(['victory', 'defeat', 'fled']).toContain(await outcomeOf(page));
    await page.waitForFunction(() => document.body.dataset.pocScene !== 'Battle', undefined, {
        timeout: 5_000
    });
}

test('wisp battle: attack-only drive survives Weaken turns to a clean end', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await enterBattle(page, 'wisp', 101);
    // Weaken turns are "quiet" (buff event, no hero HP change) — driveBattle
    // tolerates them by design; a wedge would exhaust the turn cap and fail.
    await driveBattle(page);

    await expectCleanEnd(page);
    expect(pageErrors).toEqual([]);
});

test('revenant battle: attack-only drive through the revive to a clean end', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await enterBattle(page, 'revenant', 103);
    // The one-time 50% self-revive (seed-fixed) must re-enter the kill loop,
    // not wedge it: the drive keeps confirming until the battle truly ends.
    await driveBattle(page);

    await expectCleanEnd(page);
    expect(pageErrors).toEqual([]);
});

test('boss battle: fixed-seed drive ends, and defeat/victory exit correctly', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await enterBattle(page, 'boss', 5);
    // Attack-only vs the Chimera normally LOSES (§5.2 lethality target — a
    // defeat here is correct behavior, not a failure); the phase change and
    // Flame Breath tell turns are quiet ticks the drive tolerates. Both ends
    // are asserted so data retuning (M1→M3) cannot silently break the test.
    await driveBattle(page);

    expect(await battleEnded(page)).toBe(true);
    await expect(page.locator('body[data-poc-outcome]')).toBeAttached({ timeout: 5_000 });
    const outcome = await outcomeOf(page);
    expect(['victory', 'defeat']).toContain(outcome);

    if (outcome === 'defeat') {
        // §4 flow: defeat → GameOver, and Enter returns to Title.
        await expect(page.locator('body[data-poc-scene="GameOver"]')).toBeAttached({
            timeout: 5_000
        });
        await tap(page, 'Enter');
        await expect(page.locator('body[data-poc-scene="Title"]')).toBeAttached({
            timeout: 5_000
        });
    } else {
        // Boss victory (encounters.json boss:true) → Victory screen.
        await expect(page.locator('body[data-poc-scene="Victory"]')).toBeAttached({
            timeout: 5_000
        });
    }

    expect(pageErrors).toEqual([]);
});

test('magic path: MAGIC submenu cast progresses the battle to a clean end', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await enterBattle(page, 'spider', 31);
    await dismissDefendHint(page);
    const start = await datasetSnapshot(page);

    // Menu order ATTACK/DEFEND/MAGIC/ITEM/RUN, cursor on ATTACK: two downs
    // reach MAGIC; Enter opens the spell submenu (Heal 4MP / Power 3MP, both
    // affordable at 10 MP); Enter casts the first spell (Heal, self-target —
    // no target submenu on a lone enemy).
    await tap(page, 'ArrowDown');
    await tap(page, 'ArrowDown');
    await tap(page, 'Enter');
    await tap(page, 'Enter');

    // Heal at full HP plus the spider's tell turn can leave the dataset
    // unchanged for a turn, so progress is asserted by driving to an end —
    // which must move the dataset. A wedged submenu would fail the drive.
    await driveBattle(page);

    await expectCleanEnd(page);
    expect(await datasetSnapshot(page)).not.toBe(start);
    expect(pageErrors).toEqual([]);
});

test('run path: repeated RUN attempts end the battle, normally by fleeing', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await enterBattle(page, 'spider', 41);
    await dismissDefendHint(page);

    // RUN is four downs from ATTACK (cursor resets there every hero turn, so
    // the sequence is re-enterable after a failed run's lost turn). §5.2 run
    // odds vs the spider are 0.55, so a fixed seed flees well within 6 tries;
    // a failed attempt is a quiet tick (lost turn) the wait tolerates.
    for (let attempt = 0; attempt < 6; attempt++) {
        if (await battleEnded(page)) {
            break;
        }
        const before = await datasetSnapshot(page);
        await tap(page, 'ArrowDown');
        await tap(page, 'ArrowDown');
        await tap(page, 'ArrowDown');
        await tap(page, 'ArrowDown');
        await tap(page, 'Enter');
        await waitForBattleTick(page, before);
    }

    // Eventual escape is the expected end; any other recorded outcome still
    // counts as "battle otherwise ends" (e.g. the spider winning the war of
    // attrition on a pathological seed) — but it must END, cleanly.
    await expectCleanEnd(page);
    expect(pageErrors).toEqual([]);
});
