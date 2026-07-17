import { expect, test, type Page } from '@playwright/test';

import { BASE } from '../../vite.config';
import { collectPageErrors, driveBattle, tap } from './helpers';

// M4 stage coverage (§9 M4, §10): the four-room overworld (debug room entry,
// a real exit-walk room transition, the room4 boss door) and the audio
// routing hooks (data-poc-music appears only when playback truly starts).
// All walks are dead-reckoned from the committed map JSONs (hero speed is
// 80 px/s, §4 integration contract) and poll the §10 dataset hooks between
// input bursts, so a passed exit or a triggered battle ends the walk early.

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

// §10: audio is exercised in this file — no-gesture autoplay keeps the
// unlock deterministic in headless Chromium (the Enter taps are real
// trusted gestures, this flag just removes the policy variable).
test.use({ launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });

/** Collect every 404 response (§10 zero-404 guard). */
function collect404s(page: Page): string[] {
    const notFound: string[] = [];
    page.on('response', (response) => {
        if (response.status() === 404) {
            notFound.push(response.url());
        }
    });
    return notFound;
}

/** Hold a movement key for `ms` (velocity movement: 80 px/s ≈ 0.08 px/ms). */
async function hold(page: Page, key: string, ms: number): Promise<void> {
    await page.keyboard.down(key);
    await page.waitForTimeout(ms);
    await page.keyboard.up(key);
}

function currentRoom(page: Page): Promise<string | undefined> {
    return page.evaluate(() => document.body.dataset.pocRoom);
}

async function enterRoom(page: Page, room: string, extra = ''): Promise<void> {
    await page.goto(`${BASE}?scene=overworld&room=${room}&turbo=1${extra}`);
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 15_000
    });
    await expect(page.locator(`body[data-poc-room="${room}"]`)).toBeAttached();
}

// (a) Debug room entry: each M4 room boots via ?scene=overworld&room=<id>
// (§4 debug hooks) straight to its spawn, with the §10 hooks set and the
// zero-404 guard proving every map/tileset path resolves at the Pages base.
for (const room of ['room1-gate', 'room3-marsh', 'room4-ruin']) {
    test(`debug room entry: ${room} boots to Overworld with zero 404s`, async ({ page }) => {
        const pageErrors = collectPageErrors(page);
        const notFound = collect404s(page);

        await enterRoom(page, room);

        expect(pageErrors).toEqual([]);
        expect(notFound).toEqual([]);
    });
}

// (b) Real exit-walk transition, room1-gate → room2-forest. Map facts
// (public/assets/maps/room1-gate.json): spawn tile (15,22), exit rect at
// column 31 spanning rows 12-14, and the column x≈15 plus rows 12-14 are
// obstacle-free. Dead-reckoning: 1.8 s up ≈ 144 px lands mid-window
// (row ≈13.5); east bursts then cross ≈248 px to the exit. Two vertical
// sweep nudges cover dead-reckoning drift either way.
test('exit walk: room1-gate east corridor crosses into room2-forest', async ({ page }) => {
    const pageErrors = collectPageErrors(page);

    await enterRoom(page, 'room1-gate');

    const walkEast = async (bursts: number): Promise<boolean> => {
        for (let i = 0; i < bursts; i++) {
            if ((await currentRoom(page)) === 'room2-forest') {
                return true;
            }
            await hold(page, 'ArrowRight', 500);
        }
        return (await currentRoom(page)) === 'room2-forest';
    };

    await hold(page, 'ArrowUp', 1800);
    let switched = await walkEast(10);
    if (!switched) {
        // Drifted above the exit rows: sweep one row down and push again.
        await hold(page, 'ArrowDown', 300);
        switched = await walkEast(3);
    }
    if (!switched) {
        // Or below them: net two rows up from the first sweep.
        await hold(page, 'ArrowUp', 600);
        switched = await walkEast(3);
    }

    expect(switched).toBe(true);
    await expect(page.locator('body[data-poc-room="room2-forest"]')).toBeAttached();
    expect(pageErrors).toEqual([]);
});

// (c) Audio smoke (§6 routing): data-poc-music is set ONLY once playback
// truly starts (post-unlock, load succeeded — hooks.ts), so asserting it
// proves the primary OGG resolved and decoded; the zero-404 guard proves
// no codec URL in the manifest points at a missing file.
test('audio: overworld music after Enter, boss music in the boss battle, zero 404s', async ({
    page
}) => {
    const pageErrors = collectPageErrors(page);
    const notFound = collect404s(page);

    // Title → Enter (the real user gesture that unlocks audio) → Overworld
    // lazy-loads and starts music.overworld (§2 lazy rule: nothing in
    // Preload, so the budget path stays audio-free).
    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });
    await tap(page, 'Enter');
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 10_000
    });
    await expect(page.locator('body[data-poc-music="music.overworld"]')).toBeAttached({
        timeout: 8_000
    });

    // Boss debug jump: Battle's first-entry batch loads battle+boss music,
    // §6 routing picks music.boss for boss:true encounters. The Enter tap
    // is this fresh document's unlock gesture (it also advances the
    // first-use Defend hint harmlessly).
    await page.goto(`${BASE}?scene=battle&enemy=boss&seed=5&turbo=1`);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 15_000 });
    await tap(page, 'Enter');
    await expect(page.locator('body[data-poc-music="music.boss"]')).toBeAttached({
        timeout: 10_000
    });

    expect(notFound).toEqual([]);
    expect(pageErrors).toEqual([]);
});

// (d) Boss door, room4-ruin. Map facts (room4-ruin.json): spawn tile (4,14)
// on the open row-13/14 corridor; the row-8 inner wall's only gap is cols
// 16-18, guarded by the enc-revenant zone (rows 8-9); above it the boss
// door sits at tile (17,3) with the dlg-sign-door sign at (17,4). Route:
// east ≈208 px to x≈280, north through the gap (fighting the revenant —
// &seed=9 makes that attack-only fight a deterministic victory, verified
// against the core sim), then north to the door and Enter. The door
// dialogue's dismissal must start the boss battle.
//
// FIXME(engine, M4): the boss door is geometrically untriggerable, so this
// stays fixme until Overworld.checkBossDoors (or the map) is fixed. The
// walk itself is proven: both debug iterations got through the revenant
// fight and back to the door wall; only the final trigger never fires.
// Root cause, verified against Phaser 3.90 source + an on-wall ±3-tile
// x-sweep of interact attempts: checkBossDoors inflates the door rect
// (272,48,16,16) by only 6 px, so its reach ends at y=70, while the hero's
// 16 px arcade body blocked by the row-3 wall can stand no higher than
// center y=72 — 2 px short from every reachable position. The only spots
// with center y ≤ 70 lie inside the 1-tile doorway pocket, whose 16 px gap
// exactly equals the body width, demanding float-exact x=280.0 alignment
// that velocity integration never produces. (The sign at (17,4) shares
// dialogueId dlg-sign-door, so manual play still SEES door text — from the
// sign — masking that the battle-start branch is unreachable.) Fix: inflate
// by ≥ 10 px (body half-height 8 + margin), or widen the doorway/door rect;
// then flip this fixme back to test.
test('boss door: room4 walk + revenant fight + door dialogue starts the boss battle', async ({
    page
}) => {
    const pageErrors = collectPageErrors(page);

    await enterRoom(page, 'room4-ruin', '&seed=9');

    // East along row 14 to the door/gap column (x 72 → ≈280 at 80 px/s).
    await hold(page, 'ArrowRight', 2600);

    // North into the revenant trigger (zone bottom y=160, ≈72 px away).
    await hold(page, 'ArrowUp', 1200);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached({ timeout: 5_000 });

    // Attack-only drive; the Enter taps also clear the first-use Defend
    // hint. Seed 9 ends it in 3 rounds with the hero at 22 HP.
    await driveBattle(page);
    await expect(page.locator('body[data-poc-outcome="victory"]')).toBeAttached({
        timeout: 10_000
    });
    await expect(page.locator('body[data-poc-scene="Overworld"]')).toBeAttached({
        timeout: 10_000
    });

    // Continue north from the cleared zone (y≈160) to the door wall.
    await hold(page, 'ArrowUp', 1400);

    // Interact: Enter opens dlg-sign-door via the boss door; holding Enter
    // rides the §8 hold-to-fast-forward through both pages (turbo: instant
    // text, 1 ms hold threshold — the dismissDefendHint pattern), and the
    // dismissal callback starts the enc-boss battle. The x-sweep retries
    // (±3 tiles in 8 px steps, re-pressing north against the wall each
    // time) make east-walk dead-reckoning drift immaterial: some attempt
    // stands squarely under the door tile.
    const attemptDoor = async (): Promise<boolean> => {
        await tap(page, 'Enter');
        await page.waitForTimeout(200);
        await page.keyboard.down('Enter');
        await page.waitForTimeout(600);
        await page.keyboard.up('Enter');
        return page
            .waitForFunction(() => document.body.dataset.pocScene === 'Battle', undefined, {
                timeout: 2_000
            })
            .then(() => true)
            .catch(() => false);
    };

    let bossStarted = await attemptDoor();
    const sweep: [string, number][] = [
        ['ArrowLeft', 100],
        ['ArrowLeft', 100],
        ['ArrowLeft', 100],
        ['ArrowRight', 100],
        ['ArrowRight', 100],
        ['ArrowRight', 100],
        ['ArrowRight', 100],
        ['ArrowRight', 100],
        ['ArrowRight', 100]
    ];
    for (const [key, ms] of sweep) {
        if (bossStarted) {
            break;
        }
        await hold(page, key, ms);
        await hold(page, 'ArrowUp', 300);
        bossStarted = await attemptDoor();
    }

    expect(bossStarted).toBe(true);
    await expect(page.locator('body[data-poc-scene="Battle"]')).toBeAttached();
    expect(pageErrors).toEqual([]);
});
