import { describe, expect, it } from 'vitest';

import type { BattleEvent, Rng } from '../../src/core/contracts/battle';
import type { EncountersFile, EnemiesFile, HeroState } from '../../src/core/contracts/data';
import {
    encountersFileSchema,
    enemiesFileSchema,
    heroDefSchema,
    itemsFileSchema,
    spellsFileSchema
} from '../../src/core/contracts/data';
import { runEnemyPhase } from '../../src/core/battle/driver';
import { createBattle } from '../../src/core/battle/factory';
import { mulberry32 } from '../../src/core/battle/rng';
import type { ContentDefs } from '../../src/core/battle/resolver';
import { runGauntletSim, runSim, type SimDefs } from '../../src/core/battle/sim';
import enemiesJson from '../../src/data/enemies.json';
import encountersJson from '../../src/data/encounters.json';
import heroJson from '../../src/data/hero.json';
import itemsJson from '../../src/data/items.json';
import spellsJson from '../../src/data/spells.json';

const defs: ContentDefs = {
    spells: spellsFileSchema.parse(spellsJson),
    items: itemsFileSchema.parse(itemsJson)
};

const enemies: EnemiesFile = {
    spider: {
        id: 'spider',
        name: 'Vale Spider',
        hp: 28,
        atk: 7,
        def: 5,
        spd: 5,
        xp: 8,
        artId: 'enemy.spider',
        ai: { kind: 'telegraph', tellEvery: 3, tellDamageMult: 2 }
    },
    wisp: {
        id: 'wisp',
        name: 'Marsh Wisp',
        hp: 22,
        atk: 5,
        def: 4,
        spd: 7,
        xp: 7,
        artId: 'enemy.wisp',
        ai: { kind: 'caster', spellId: 'weaken', chance: 0.3 }
    }
};

const encounters: EncountersFile = {
    'enc-spider': { id: 'enc-spider', enemies: ['spider'], boss: false },
    'enc-spider-wisp': { id: 'enc-spider-wisp', enemies: ['spider', 'wisp'], boss: false }
};

const hero: HeroState = {
    name: 'Aden',
    level: 1,
    xp: 0,
    stats: { maxHp: 40, hp: 40, maxMp: 10, mp: 10, atk: 8, def: 5, spd: 6 },
    spells: ['heal', 'power'],
    inventory: [
        { itemId: 'herb', qty: 2 },
        { itemId: 'powerBottle', qty: 1 }
    ]
};

/** Rng stub returning a fixed sequence (then repeating the last value). */
function seq(...values: number[]): Rng {
    let i = 0;
    return { next: () => values[Math.min(i++, values.length - 1)] };
}

function ofType<T extends BattleEvent['type']>(
    events: BattleEvent[],
    type: T
): Extract<BattleEvent, { type: T }>[] {
    return events.filter((e): e is Extract<BattleEvent, { type: T }> => e.type === type);
}

describe('runEnemyPhase — spider telegraph cycle over rounds (§5.3)', () => {
    it('tells on round 1, bites 2× on round 2, attacks normally on round 3, re-tells on round 4', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const spider = state.combatants['spider-0'];

        // Round 1: tell only — no damage, round advances.
        const r1 = runEnemyPhase(state, seq(0.5), defs);
        expect(ofType(r1, 'tellStarted')).toHaveLength(1);
        expect(ofType(r1, 'damage')).toHaveLength(0);
        expect(ofType(r1, 'roundStarted')).toEqual([{ type: 'roundStarted', round: 2 }]);
        expect(spider.tellPending).toBe(true);

        // Round 2: the telegraphed bite. rand 0 → raw 7·2−5 = 9 → ×2 = 18.
        const r2 = runEnemyPhase(state, seq(0.5), defs);
        expect(ofType(r2, 'damage')).toEqual([
            { type: 'damage', source: 'spider-0', target: 'hero', amount: 18, kind: 'attack' }
        ]);
        expect(spider.tellPending).toBe(false);
        expect(state.combatants['hero'].stats.hp).toBe(22);
        expect(state.round).toBe(3);

        // Round 3: plain attack, no tell multiplier. rand 0 → 9.
        const r3 = runEnemyPhase(state, seq(0.5), defs);
        expect(ofType(r3, 'damage')[0].amount).toBe(9);
        expect(ofType(r3, 'tellStarted')).toHaveLength(0);

        // Round 4: turnCount 3 → re-tell (every 3rd turn per §5.3).
        const r4 = runEnemyPhase(state, seq(0.5), defs);
        expect(ofType(r4, 'tellStarted')).toHaveLength(1);
        expect(spider.tellPending).toBe(true);
    });

    it('the 2× bite only ever follows a tell (driver path)', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const rng = mulberry32(7);
        let sawTellLastRound = false;
        for (let round = 0; round < 12 && state.outcome === 'ongoing'; round++) {
            const events = runEnemyPhase(state, rng, defs);
            const dmg = ofType(events, 'damage');
            if (dmg.length > 0 && dmg[0].amount >= 14) {
                // A ≥14 hit is only reachable via the 2× tell multiplier (raw ≤ 11).
                expect(sawTellLastRound).toBe(true);
            }
            sawTellLastRound = ofType(events, 'tellStarted').length > 0;
        }
    });
});

describe('runEnemyPhase — early stop and bookkeeping', () => {
    it('stops the phase on hero defeat: later enemies never act, endRound never runs', () => {
        const state = createBattle('enc-spider-wisp', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 1;
        state.combatants['spider-0'].turnCount = 1; // %3 ≠ 0 → plain attack, not a tell

        const events = runEnemyPhase(state, seq(0.5), defs);

        expect(state.outcome).toBe('defeat');
        expect(ofType(events, 'battleEnded')).toEqual([{ type: 'battleEnded', outcome: 'defeat' }]);
        // The wisp (after the spider in order) never acted.
        expect(ofType(events, 'turnStarted').map((e) => e.actor)).toEqual(['spider-0']);
        // No endRound after a decided battle: no roundStarted, round untouched.
        expect(ofType(events, 'roundStarted')).toHaveLength(0);
        expect(state.round).toBe(1);
        expect(events[events.length - 1].type).toBe('battleEnded');
    });

    it('skips dead enemies', () => {
        const state = createBattle('enc-spider-wisp', hero, 1, { enemies, encounters });
        state.combatants['spider-0'].alive = false;
        state.combatants['spider-0'].stats.hp = 0;

        // 0.9 ≥ 0.30 → wisp attacks; rand 0 → 5·2−5 = 5.
        const events = runEnemyPhase(state, seq(0.9, 0.5), defs);
        expect(ofType(events, 'turnStarted').map((e) => e.actor)).toEqual(['wisp-1']);
        expect(ofType(events, 'damage')).toEqual([
            { type: 'damage', source: 'wisp-1', target: 'hero', amount: 5, kind: 'attack' }
        ]);
        expect(ofType(events, 'roundStarted')).toEqual([{ type: 'roundStarted', round: 2 }]);
    });

    it('drives the wisp Weaken branch (§5.3)', () => {
        const state = createBattle('enc-spider-wisp', hero, 1, { enemies, encounters });
        state.combatants['spider-0'].alive = false; // isolate the wisp
        state.combatants['spider-0'].stats.hp = 0;

        // 0.1 < 0.30 → cast weaken on the hero.
        const events = runEnemyPhase(state, seq(0.1), defs);
        expect(ofType(events, 'buffApplied')).toEqual([
            { type: 'buffApplied', target: 'hero', stat: 'atk', pct: -25, turns: 3 }
        ]);
        expect(ofType(events, 'damage')).toHaveLength(0);
        expect(state.combatants['hero'].mods).toContainEqual({
            stat: 'atk',
            pct: -25,
            turnsLeft: 2, // endRound already ticked it once
            source: 'weaken'
        });
    });

    it('returns no events when the battle is already decided', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.outcome = 'victory';
        expect(runEnemyPhase(state, seq(0.5), defs)).toEqual([]);
        expect(state.round).toBe(1);
    });
});

// ---------------------------------------------------------------------------
// §10 sim harness — structure/determinism only. The §5.2 lethality
// thresholds are deliberately NOT asserted here; they enter CI at M3 after
// the tuning pass (PLAN §5/§10: sim expected red until then).

const simDefs: SimDefs = {
    ...defs,
    enemies: enemiesFileSchema.parse(enemiesJson),
    encounters: encountersFileSchema.parse(encountersJson)
};
const heroDef = heroDefSchema.parse(heroJson);
const seeds50 = Array.from({ length: 50 }, (_, i) => i + 1);
const GAUNTLET = ['enc-spider', 'enc-spider', 'enc-wisp', 'enc-spider-wisp', 'enc-revenant', 'enc-boss'];

describe('runSim (§10 balance harness)', () => {
    it('attackOnly vs the boss returns a sane, complete result on 50 seeds', () => {
        const result = runSim('attackOnly', 'enc-boss', seeds50, simDefs, heroDef);

        expect(result.wins + result.losses + result.fled).toBe(50);
        expect(result.fled).toBe(0); // neither policy ever runs
        expect(typeof result.winRate).toBe('number');
        expect(Number.isNaN(result.winRate)).toBe(false);
        expect(result.winRate).toBeGreaterThanOrEqual(0);
        expect(result.winRate).toBeLessThanOrEqual(1);
        expect(result.winRate).toBeCloseTo(result.wins / 50);
        expect(result.medianEndHp).toBeGreaterThanOrEqual(0);
        expect(result.medianEndHp).toBeLessThanOrEqual(heroDef.hp);
        expect(result.meanRounds).toBeGreaterThan(0);
    });

    it('tactical vs a lone spider returns a sane result', () => {
        const result = runSim('tactical', 'enc-spider', seeds50, simDefs, heroDef);
        expect(result.wins + result.losses + result.fled).toBe(50);
        expect(result.winRate).toBeGreaterThanOrEqual(0);
        expect(result.winRate).toBeLessThanOrEqual(1);
    });

    it('is deterministic for identical seeds', () => {
        const a = runSim('tactical', 'enc-boss', seeds50, simDefs, heroDef);
        const b = runSim('tactical', 'enc-boss', seeds50, simDefs, heroDef);
        expect(a).toEqual(b);
    });
});

describe('runGauntletSim (§10 item 2)', () => {
    it('returns a sane structure across the no-heal gauntlet', () => {
        const result = runGauntletSim('attackOnly', GAUNTLET, seeds50, simDefs, heroDef);
        expect(result.survivalRate).toBeGreaterThanOrEqual(0);
        expect(result.survivalRate).toBeLessThanOrEqual(1);
        expect(Number.isInteger(result.bossReached)).toBe(true);
        expect(result.bossReached).toBeGreaterThanOrEqual(0);
        expect(result.bossReached).toBeLessThanOrEqual(50);
        // Winning the whole gauntlet requires having reached the boss.
        expect(result.survivalRate * 50).toBeLessThanOrEqual(result.bossReached);
    });

    it('is deterministic for identical seeds', () => {
        const a = runGauntletSim('tactical', GAUNTLET, seeds50, simDefs, heroDef);
        const b = runGauntletSim('tactical', GAUNTLET, seeds50, simDefs, heroDef);
        expect(a).toEqual(b);
    });
});
