import { describe, expect, it } from 'vitest';

import {
    encountersFileSchema,
    enemiesFileSchema,
    heroDefSchema,
    itemsFileSchema,
    spellsFileSchema
} from '../../src/core/contracts/data';
import { runGauntletSim, runSim, type SimDefs } from '../../src/core/battle/sim';
import enemiesJson from '../../src/data/enemies.json';
import encountersJson from '../../src/data/encounters.json';
import heroJson from '../../src/data/hero.json';
import itemsJson from '../../src/data/items.json';
import spellsJson from '../../src/data/spells.json';

/**
 * §10 balance simulation — the merge-blocking §5.2 lethality gate, run
 * against the LIVE src/data dataset (schema-parsed, same validation path the
 * game uses). Deterministic: seeds 1..1000 through mulberry32, scripted
 * policies, no Math.random anywhere in the core — so every threshold below
 * is an exact regression assertion, not a statistical one. A data-only PR
 * that shifts an outcome past a §5.2 threshold fails here.
 *
 * Asserted (PLAN §5.2 quantified invariant / §10 "Balance simulation"):
 *  (a) careless (always-attack) vs the boss        → win-rate ≤ 0.05
 *  (b) careless across the no-heal gauntlet        → survival-to-boss ≤ 0.10
 *  (c) tactical (defend-on-tell + Power + Heal<33%) vs boss
 *                                                  → win-rate ≥ 0.95 AND median end-HP ≥ 8
 *  (d) EACH lone mob vs careless                   → win-rate ≥ 0.90 AND median end-HP ≥ 20
 *
 * Tuned M3 dataset (wisp ATK 6, revenant ATK 5, hero HP 42, Heal 18)
 * measures, for the record (seeds 1..1000):
 *   (a) 0.003   (b) 0.000 to-boss (0.000 full)   (c) 1.000 / median 16
 *   (d) spider 1.000/24 · wisp 1.000/35 · revenant 1.000/25
 *   2-mob careless 0.307 (M2 baseline was 0.54) · tactical+leveling gauntlet 1.000
 */

/** §10: "seeds 1..1000 (a committed constant array)". */
export const BALANCE_SEEDS: readonly number[] = Array.from({ length: 1000 }, (_, i) => i + 1);

/** GDD §3/§4: the no-heal gauntlet Room2 → boss on one shared pool. */
const GAUNTLET = [
    'enc-spider',
    'enc-spider',
    'enc-wisp',
    'enc-spider-wisp',
    'enc-revenant',
    'enc-boss'
];

const defs: SimDefs = {
    spells: spellsFileSchema.parse(spellsJson),
    items: itemsFileSchema.parse(itemsJson),
    enemies: enemiesFileSchema.parse(enemiesJson),
    encounters: encountersFileSchema.parse(encountersJson)
};
const heroDef = heroDefSchema.parse(heroJson);

const seeds = [...BALANCE_SEEDS];

describe('§5.2 quantified lethality invariant (live src/data, seeds 1..1000)', () => {
    it('(a) careless play wins ≤ 5% against the boss', () => {
        const r = runSim('attackOnly', 'enc-boss', seeds, defs, heroDef);
        expect(r.winRate).toBeLessThanOrEqual(0.05);
    });

    it('(b) careless play survives-to-boss ≤ 10% across the no-heal gauntlet', () => {
        const r = runGauntletSim('attackOnly', GAUNTLET, seeds, defs, heroDef);
        expect(r.bossReached / seeds.length).toBeLessThanOrEqual(0.1);
        // Full-gauntlet survival can never exceed survival-to-boss.
        expect(r.survivalRate).toBeLessThanOrEqual(r.bossReached / seeds.length);
    });

    it('(c) tactical play beats the boss ≥ 95% with median end-HP ≥ 8', () => {
        const r = runSim('tactical', 'enc-boss', seeds, defs, heroDef);
        expect(r.winRate).toBeGreaterThanOrEqual(0.95);
        expect(r.medianEndHp).toBeGreaterThanOrEqual(8);
    });

    it('(d) each lone mob is winnable careless (≥ 90%) but costly (median end-HP ≥ 20)', () => {
        for (const enc of ['enc-spider', 'enc-wisp', 'enc-revenant']) {
            const r = runSim('attackOnly', enc, seeds, defs, heroDef);
            expect(r.winRate, `${enc} winRate`).toBeGreaterThanOrEqual(0.9);
            expect(r.medianEndHp, `${enc} medianEndHp`).toBeGreaterThanOrEqual(20);
        }
    });
});

describe('informational lethality context (structure asserted, balance not gated)', () => {
    // PLAN §5.2 prose: a standard 2-mob encounter is fatal to careless play.
    // Not one of the four CI-gated thresholds; asserted only loosely enough
    // to document intent (M2 measured 0.54; the tuned dataset measures 0.307).
    it('2-mob encounter punishes careless play harder than any lone mob', () => {
        const twoMob = runSim('attackOnly', 'enc-spider-wisp', seeds, defs, heroDef);
        const loneSpider = runSim('attackOnly', 'enc-spider', seeds, defs, heroDef);
        expect(twoMob.winRate).toBeLessThan(loneSpider.winRate);
        expect(twoMob.medianEndHp).toBeLessThan(loneSpider.medianEndHp);
    });

    // PLAN DoD: the real 4–6 encounter stage — WITH victory XP and the
    // level-up full-heal ding — must be winnable by correct play. The
    // leveling variant models real play; kept informational-structural here
    // (the M3 measurement was 1.000 survival) so future tuning sees drift
    // in the (a)-(d) gates first, not a hair-trigger here.
    it('tactical play with leveling completes the full gauntlet for most seeds', () => {
        const r = runGauntletSim('tactical', GAUNTLET, seeds, defs, heroDef, { leveling: true });
        expect(r.bossReached).toBeGreaterThan(0);
        expect(r.survivalRate).toBeGreaterThan(0.5);
    });
});
