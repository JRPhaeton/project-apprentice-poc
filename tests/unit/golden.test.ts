import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import type { Action, BattleEvent, BattleState } from '../../src/core/contracts/battle';
import {
    encountersFileSchema,
    enemiesFileSchema,
    heroDefSchema,
    itemsFileSchema,
    spellsFileSchema
} from '../../src/core/contracts/data';
import { runEnemyPhase } from '../../src/core/battle/driver';
import { createBattle } from '../../src/core/battle/factory';
import { heroStateFromDef } from '../../src/core/battle/progression';
import { resolveAction, type ContentDefs } from '../../src/core/battle/resolver';
import { mulberry32 } from '../../src/core/battle/rng';
import bundle from '../fixtures/balance-v0.json';

/**
 * §10 golden replays — ENGINE DETERMINISM, not balance. Each golden is the
 * complete serialized BattleEvent[] of a scripted battle at a fixed seed,
 * recorded against the frozen tests/fixtures/balance-v0.json dataset (never
 * edited by future tuning — live-data balance drift is the balance sim's
 * job, §10) and compared BYTE-FOR-BYTE against the committed fixture under
 * tests/fixtures/goldens/. Any resolver/driver/rng behavior change shows up
 * as a fixture diff and fails CI.
 *
 * Regeneration is explicit and local-only:
 *     UPDATE_GOLDENS=1 npm test
 * CI runs without the flag, so it always compares and never regenerates.
 *
 * Anti-leak guard (§4 "pure core, seeded Rng only"): global Math.random is
 * replaced with a throwing stub for the duration of every simulated battle —
 * if any core path consulted it, the golden run would explode.
 */

const GOLDEN_DIR = join(__dirname, '..', 'fixtures', 'goldens');
const UPDATE = Boolean(process.env.UPDATE_GOLDENS);

// Frozen dataset through the same zod gate the game's loader uses (§3).
const defs: ContentDefs & Parameters<typeof createBattle>[3] = {
    enemies: enemiesFileSchema.parse(bundle.enemies),
    spells: spellsFileSchema.parse(bundle.spells),
    items: itemsFileSchema.parse(bundle.items),
    encounters: encountersFileSchema.parse(bundle.encounters)
};
const heroDef = heroDefSchema.parse(bundle.hero);

type Controller = (state: BattleState) => Action;

/** Careless script: always attack the first living enemy. */
const attackController: Controller = (state) => {
    const target = state.order
        .map((id) => state.combatants[id])
        .find((c) => c.side === 'enemy' && c.alive);
    if (!target) {
        throw new Error('controller invoked with no living enemies');
    }
    return { type: 'attack', actor: state.heroId, target: target.id };
};

/**
 * Boss script (deliberately independent of policies.ts so goldens pin the
 * ENGINE, not the sim's policy code): defend through tells, heal when low,
 * otherwise attack. Long enough for the ≤50% phase change and a full Flame
 * Breath telegraph→cast cycle to occur before victory.
 */
const bossController: Controller = (state) => {
    const hero = state.combatants[state.heroId];
    const tellPending = state.order
        .map((id) => state.combatants[id])
        .some((c) => c.side === 'enemy' && c.alive && c.tellPending);
    if (tellPending) {
        return { type: 'defend', actor: hero.id };
    }
    if (hero.stats.hp < 14 && hero.stats.mp >= 4) {
        return { type: 'cast', actor: hero.id, spellId: 'heal', target: hero.id };
    }
    return attackController(state);
};

/** Hard cap so a broken engine can never hang the suite. */
const ROUND_CAP = 50;

/** Plays one scripted battle, returning the full ordered event stream. */
function playBattle(encounterId: string, seed: number, controller: Controller): {
    events: BattleEvent[];
    outcome: BattleState['outcome'];
} {
    const state = createBattle(encounterId, heroStateFromDef(heroDef), seed, defs);
    const rng = mulberry32(seed);
    const events: BattleEvent[] = [];
    while (state.outcome === 'ongoing' && state.round <= ROUND_CAP) {
        const { events: heroEvents } = resolveAction(state, controller(state), rng, defs);
        events.push(...heroEvents);
        if (state.outcome !== 'ongoing') {
            break;
        }
        events.push(...runEnemyPhase(state, rng, defs));
    }
    return { events, outcome: state.outcome };
}

/** Runs fn with global Math.random stubbed to throw; always restores. */
function withMathRandomGuard<T>(fn: () => T): T {
    const original = Math.random;
    Math.random = () => {
        throw new Error('Math.random leak: the battle core must only use the injected seeded Rng (§4)');
    };
    try {
        return fn();
    } finally {
        Math.random = original;
    }
}

interface GoldenScenario {
    /** Fixture basename under tests/fixtures/goldens/. */
    name: string;
    encounterId: string;
    seed: number;
    controller: Controller;
    /** Signature behaviors the recorded battle must actually contain. */
    verify: (events: BattleEvent[], outcome: BattleState['outcome']) => void;
}

const scenarios: GoldenScenario[] = [
    {
        // Spider full cycle: tell → 2× bite → normal attack → re-tell window.
        name: 'spider-full-cycle',
        encounterId: 'enc-spider',
        seed: 3,
        controller: attackController,
        verify: (events, outcome) => {
            expect(outcome).toBe('victory');
            expect(events.some((e) => e.type === 'tellStarted' && e.actor === 'spider-0')).toBe(true);
            // Bite: 2× tell multiplier → ≥14 vs the hero (normal hits cap at 11).
            expect(
                events.some((e) => e.type === 'damage' && e.source === 'spider-0' && e.amount >= 14)
            ).toBe(true);
        }
    },
    {
        // Wisp Weaken proc: the −25% ATK debuff lands on the hero.
        name: 'wisp-weaken',
        encounterId: 'enc-wisp',
        seed: 6,
        controller: attackController,
        verify: (events, outcome) => {
            expect(outcome).toBe('victory');
            expect(
                events.some(
                    (e) => e.type === 'buffApplied' && e.target === 'hero' && e.pct === -25
                )
            ).toBe(true);
        }
    },
    {
        // Boss: ≤50% phase change, then Flame Breath telegraph → cast.
        name: 'boss-phase-flame-breath',
        encounterId: 'enc-boss',
        seed: 5,
        controller: bossController,
        verify: (events, outcome) => {
            expect(outcome).toBe('victory');
            const phaseIdx = events.findIndex((e) => e.type === 'phaseChanged');
            expect(phaseIdx).toBeGreaterThanOrEqual(0);
            const tellIdx = events.findIndex(
                (e, i) => i > phaseIdx && e.type === 'tellStarted' && e.actor === 'chimera-0'
            );
            expect(tellIdx).toBeGreaterThan(phaseIdx);
            // The telegraphed cast lands after its tell (spell-kind damage).
            const flameIdx = events.findIndex(
                (e, i) => i > tellIdx && e.type === 'damage' && e.kind === 'spell' && e.source === 'chimera-0'
            );
            expect(flameIdx).toBeGreaterThan(tellIdx);
        }
    },
    {
        // Revenant: the one-time 50% self-revive passes, then it dies for good.
        name: 'revenant-revive',
        encounterId: 'enc-revenant',
        seed: 7,
        controller: attackController,
        verify: (events, outcome) => {
            expect(outcome).toBe('victory');
            const revivedIdx = events.findIndex((e) => e.type === 'revived');
            expect(revivedIdx).toBeGreaterThanOrEqual(0);
            const finalDeath = events.findIndex(
                (e, i) => i > revivedIdx && e.type === 'defeated' && e.actor === 'revenant-0'
            );
            expect(finalDeath).toBeGreaterThan(revivedIdx);
        }
    }
];

function serialize(scenario: GoldenScenario, events: BattleEvent[], outcome: string): string {
    return (
        JSON.stringify(
            {
                dataset: 'balance-v0',
                encounterId: scenario.encounterId,
                seed: scenario.seed,
                outcome,
                events
            },
            null,
            2
        ) + '\n'
    );
}

describe('golden replays (§10 — frozen balance-v0 dataset, byte-for-byte)', () => {
    for (const scenario of scenarios) {
        it(`${scenario.name} (seed ${scenario.seed})`, () => {
            const { events, outcome } = withMathRandomGuard(() =>
                playBattle(scenario.encounterId, scenario.seed, scenario.controller)
            );

            // The scenario must exhibit its signature behavior in BOTH modes,
            // so a regeneration can never silently record a degenerate battle.
            scenario.verify(events, outcome);

            const file = join(GOLDEN_DIR, `${scenario.name}.json`);
            const actual = serialize(scenario, events, outcome);

            if (UPDATE) {
                writeFileSync(file, actual);
                return;
            }

            if (!existsSync(file)) {
                throw new Error(
                    `Missing golden fixture ${file} — run UPDATE_GOLDENS=1 npm test locally and commit the result`
                );
            }
            expect(actual).toBe(readFileSync(file, 'utf8'));
        });
    }

    it('the Math.random guard actually guards (and restores)', () => {
        const original = Math.random;
        expect(() =>
            withMathRandomGuard(() => {
                return Math.random();
            })
        ).toThrow(/Math\.random leak/);
        expect(Math.random).toBe(original);
        expect(() => Math.random()).not.toThrow();
    });
});
