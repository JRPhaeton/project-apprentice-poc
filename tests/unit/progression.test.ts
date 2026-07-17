import { describe, expect, it } from 'vitest';

import type { HeroState } from '../../src/core/contracts/data';
import { heroDefSchema } from '../../src/core/contracts/data';
import {
    applyVictoryXp,
    heroStateFromDef,
    LEVEL_GAINS,
    levelForXp,
    MAX_LEVEL,
    XP_THRESHOLDS
} from '../../src/core/battle/progression';
import heroJson from '../../src/data/hero.json';

function makeHero(overrides: Partial<HeroState> = {}): HeroState {
    return {
        name: 'Aden',
        level: 1,
        xp: 0,
        stats: { maxHp: 40, hp: 40, maxMp: 10, mp: 10, atk: 8, def: 5, spd: 6 },
        spells: ['heal', 'power'],
        inventory: [
            { itemId: 'herb', qty: 2 },
            { itemId: 'powerBottle', qty: 1 }
        ],
        ...overrides
    };
}

describe('XP curve (levels 1→5: 0/10/25/45/70 cumulative)', () => {
    it('pins the documented thresholds', () => {
        expect(XP_THRESHOLDS).toEqual([0, 10, 25, 45, 70]);
        expect(MAX_LEVEL).toBe(5);
    });

    it('maps cumulative XP to levels, boundaries inclusive', () => {
        const cases: [number, number][] = [
            [0, 1],
            [9, 1],
            [10, 2],
            [24, 2],
            [25, 3],
            [44, 3],
            [45, 4],
            [69, 4],
            [70, 5],
            [71, 5],
            [1000, 5] // capped
        ];
        for (const [xp, level] of cases) {
            expect(levelForXp(xp), `xp=${xp}`).toBe(level);
        }
    });
});

describe('applyVictoryXp', () => {
    it('levels up at the threshold: +5 maxHp, +2 maxMp, +1 atk/def/spd, full-heal ding', () => {
        const damaged = makeHero({
            stats: { maxHp: 40, hp: 20, maxMp: 10, mp: 2, atk: 8, def: 5, spd: 6 }
        });
        const { hero, leveledUp, levelsGained } = applyVictoryXp(damaged, 10);

        expect(leveledUp).toBe(true);
        expect(levelsGained).toBe(1);
        expect(hero.level).toBe(2);
        expect(hero.xp).toBe(10);
        expect(hero.stats).toEqual({
            maxHp: 45,
            hp: 45, // refilled to the NEW max
            maxMp: 12,
            mp: 12,
            atk: 9,
            def: 6,
            spd: 7
        });
    });

    it('gains multiple levels from one large award', () => {
        const { hero, leveledUp, levelsGained } = applyVictoryXp(makeHero(), 45);
        expect(leveledUp).toBe(true);
        expect(levelsGained).toBe(3); // L1 → L4
        expect(hero.level).toBe(4);
        expect(hero.stats).toEqual({
            maxHp: 40 + 3 * LEVEL_GAINS.maxHp,
            hp: 55,
            maxMp: 10 + 3 * LEVEL_GAINS.maxMp,
            mp: 16,
            atk: 11,
            def: 8,
            spd: 9
        });
    });

    it('accumulates XP across victories', () => {
        const first = applyVictoryXp(makeHero(), 5);
        expect(first.leveledUp).toBe(false);
        expect(first.hero.xp).toBe(5);

        const second = applyVictoryXp(first.hero, 5);
        expect(second.leveledUp).toBe(true);
        expect(second.hero.level).toBe(2);
        expect(second.hero.xp).toBe(10);
    });

    it('without a level-up, stats are untouched and hp/mp are NOT refilled', () => {
        const damaged = makeHero({
            stats: { maxHp: 40, hp: 20, maxMp: 10, mp: 2, atk: 8, def: 5, spd: 6 }
        });
        const { hero, leveledUp, levelsGained } = applyVictoryXp(damaged, 9);
        expect(leveledUp).toBe(false);
        expect(levelsGained).toBe(0);
        expect(hero.level).toBe(1);
        expect(hero.xp).toBe(9);
        expect(hero.stats).toEqual(damaged.stats);
    });

    it('caps at level 5: XP accumulates, no further gains or refills', () => {
        const maxed = makeHero({
            level: 5,
            xp: 70,
            stats: { maxHp: 60, hp: 31, maxMp: 18, mp: 4, atk: 12, def: 9, spd: 10 }
        });
        const { hero, leveledUp, levelsGained } = applyVictoryXp(maxed, 100);
        expect(leveledUp).toBe(false);
        expect(levelsGained).toBe(0);
        expect(hero.level).toBe(5);
        expect(hero.xp).toBe(170);
        expect(hero.stats).toEqual(maxed.stats);
    });

    it('never lowers a level', () => {
        // Degenerate state (level ahead of xp) — level must not regress.
        const ahead = makeHero({ level: 3, xp: 0 });
        const { hero } = applyVictoryXp(ahead, 0);
        expect(hero.level).toBe(3);
    });

    it('is pure: the input hero is never mutated', () => {
        const input = makeHero({
            stats: { maxHp: 40, hp: 20, maxMp: 10, mp: 2, atk: 8, def: 5, spd: 6 }
        });
        const snapshot = structuredClone(input);
        const { hero } = applyVictoryXp(input, 25);
        expect(input).toEqual(snapshot);
        expect(hero).not.toBe(input);
        expect(hero.stats).not.toBe(input.stats);
        expect(hero.inventory).not.toBe(input.inventory);
    });
});

describe('heroStateFromDef', () => {
    it('builds a fresh level-1 state from the live hero.json def', () => {
        const def = heroDefSchema.parse(heroJson);
        const state = heroStateFromDef(def);
        expect(state.level).toBe(1);
        expect(state.xp).toBe(0);
        expect(state.stats).toEqual({
            maxHp: def.hp,
            hp: def.hp,
            maxMp: def.mp,
            mp: def.mp,
            atk: def.atk,
            def: def.def,
            spd: def.spd
        });
        expect(state.spells).toEqual(def.spells);
        expect(state.spells).not.toBe(def.spells);
        expect(state.inventory).toEqual(def.inventory);
        expect(state.inventory[0]).not.toBe(def.inventory[0]);
    });
});
