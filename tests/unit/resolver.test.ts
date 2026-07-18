import { describe, expect, it } from 'vitest';

import type { BattleEvent, Rng } from '../../src/core/contracts/battle';
import type { EncountersFile, EnemiesFile, HeroState } from '../../src/core/contracts/data';
import { createBattle } from '../../src/core/battle/factory';
import { mulberry32 } from '../../src/core/battle/rng';
import {
    chooseAction,
    endRound,
    resolveAction,
    runChance,
    type ContentDefs
} from '../../src/core/battle/resolver';
import { itemsFileSchema, spellsFileSchema } from '../../src/core/contracts/data';
import spellsJson from '../../src/data/spells.json';
import itemsJson from '../../src/data/items.json';

// §10: tests run the core through its data-injection path against local
// defs — never through Phaser. Parsing through the schemas narrows the
// JSON imports' widened literal types.
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
    revenant: {
        id: 'revenant',
        name: 'Revenant',
        hp: 30,
        atk: 6,
        def: 6,
        spd: 3,
        xp: 12,
        artId: 'enemy.revenant',
        ai: { kind: 'reviver', reviveChance: 0.5, reviveHp: 12 }
    },
    chimera: {
        id: 'chimera',
        name: 'Cloaked Chimera',
        hp: 66,
        atk: 7,
        def: 5,
        spd: 6,
        xp: 40,
        artId: 'enemy.chimera',
        ai: { kind: 'boss', phaseAtPct: 50, phaseAtkPct: 30, phaseUnlock: 'flameBreath' }
    }
};

const encounters: EncountersFile = {
    'enc-spider': { id: 'enc-spider', enemies: ['spider'], boss: false },
    'enc-revenant': { id: 'enc-revenant', enemies: ['revenant'], boss: false },
    'enc-boss': { id: 'enc-boss', enemies: ['chimera'], boss: true }
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

function damageEvents(events: BattleEvent[]): Extract<BattleEvent, { type: 'damage' }>[] {
    return events.filter((e): e is Extract<BattleEvent, { type: 'damage' }> => e.type === 'damage');
}

describe('damage formula (§5.2)', () => {
    it('hero attack vs spider stays in [2·ATK−DEF−2, 2·ATK−DEF+2]', () => {
        // hero ATK 8 vs spider DEF 5 → raw ∈ [9, 13]
        for (let seed = 1; seed <= 200; seed++) {
            const state = createBattle('enc-spider', hero, seed, { enemies, encounters });
            const { events } = resolveAction(
                state,
                { type: 'attack', actor: 'hero', target: 'spider-0' },
                mulberry32(seed),
                defs
            );
            const [dmg] = damageEvents(events);
            expect(dmg.amount).toBeGreaterThanOrEqual(9);
            expect(dmg.amount).toBeLessThanOrEqual(13);
        }
    });

    it('never deals less than 1', () => {
        const weakHero: HeroState = { ...hero, stats: { ...hero.stats, atk: 1 } };
        // ATK 1 vs DEF 6 → raw ∈ [−6, −2] → clamped to 1
        for (let seed = 1; seed <= 50; seed++) {
            const state = createBattle('enc-revenant', weakHero, seed, { enemies, encounters });
            const { events } = resolveAction(
                state,
                { type: 'attack', actor: 'hero', target: 'revenant-0' },
                mulberry32(seed),
                defs
            );
            expect(damageEvents(events)[0].amount).toBe(1);
        }
    });
});

describe('Defend (§5.2)', () => {
    it('halves incoming damage this turn', () => {
        // spider ATK 7 vs hero DEF 5 → raw ∈ [7, 11] → defended ∈ [4, 6] (round .5 up)
        for (let seed = 1; seed <= 100; seed++) {
            const state = createBattle('enc-spider', hero, seed, { enemies, encounters });
            resolveAction(state, { type: 'defend', actor: 'hero' }, mulberry32(seed), defs);
            const { events } = resolveAction(
                state,
                { type: 'attack', actor: 'spider-0', target: 'hero' },
                mulberry32(seed),
                defs
            );
            const [dmg] = damageEvents(events);
            expect(dmg.amount).toBeGreaterThanOrEqual(4);
            expect(dmg.amount).toBeLessThanOrEqual(6);
        }
    });

    it('boosts the next attack ×1.5 and consumes the boost', () => {
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        resolveAction(state, { type: 'defend', actor: 'hero' }, seq(0.5), defs);

        // rand = 0 (next() = 0.4 → randInt(-2..2) = 0): raw = 16 − 5 = 11 → ×1.5 = 16.5 → 17
        const boosted = resolveAction(
            state,
            { type: 'attack', actor: 'hero', target: 'chimera-0' },
            seq(0.4),
            defs
        );
        expect(damageEvents(boosted.events)[0].amount).toBe(17);
        expect(state.combatants['hero'].nextAttackMult).toBe(1);

        // Same rand, boost gone: raw = 11
        const plain = resolveAction(
            state,
            { type: 'attack', actor: 'hero', target: 'chimera-0' },
            seq(0.4),
            defs
        );
        expect(damageEvents(plain.events)[0].amount).toBe(11);
    });

    it('defending clears at end of round', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        resolveAction(state, { type: 'defend', actor: 'hero' }, seq(0.5), defs);
        expect(state.combatants['hero'].defending).toBe(true);
        endRound(state);
        expect(state.combatants['hero'].defending).toBe(false);
        expect(state.combatants['hero'].nextAttackMult).toBe(1.5); // persists until spent
    });
});

describe('buffs (§5.2)', () => {
    it('reapplication refreshes duration, never stacks', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const heroC = state.combatants['hero'];

        resolveAction(state, { type: 'cast', actor: 'hero', spellId: 'power', target: 'hero' }, seq(0.5), defs);
        expect(heroC.mods).toHaveLength(1);
        expect(heroC.mods[0]).toMatchObject({ stat: 'atk', pct: 50, turnsLeft: 3 });

        endRound(state);
        expect(heroC.mods[0].turnsLeft).toBe(2);

        resolveAction(state, { type: 'cast', actor: 'hero', spellId: 'power', target: 'hero' }, seq(0.5), defs);
        expect(heroC.mods).toHaveLength(1); // refreshed, not stacked
        expect(heroC.mods[0].turnsLeft).toBe(3);
        expect(heroC.stats.mp).toBe(10 - 3 - 3);
    });

    it('expires after its full duration', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        resolveAction(state, { type: 'cast', actor: 'hero', spellId: 'power', target: 'hero' }, seq(0.5), defs);
        endRound(state);
        endRound(state);
        const { events } = endRound(state);
        expect(events.some((e) => e.type === 'buffExpired')).toBe(true);
        expect(state.combatants['hero'].mods).toHaveLength(0);
    });
});

describe('Run (§5.2)', () => {
    it('clamps to [0.25, 0.95]', () => {
        const slow = createBattle('enc-spider', { ...hero, stats: { ...hero.stats, spd: 1 } }, 1, { enemies, encounters });
        // SPD 1 vs 5 → 0.3 (formula, unclamped)
        expect(runChance(slow, slow.combatants['hero'])).toBeCloseTo(0.3);
        // Against a much faster enemy the lower clamp binds
        slow.combatants['spider-0'].stats.spd = 20;
        expect(runChance(slow, slow.combatants['hero'])).toBe(0.25);

        const fast = createBattle('enc-spider', { ...hero, stats: { ...hero.stats, spd: 99 } }, 1, { enemies, encounters });
        expect(runChance(fast, fast.combatants['hero'])).toBe(0.95);

        // hero SPD 6 vs spider SPD 5 → 0.55
        const base = createBattle('enc-spider', hero, 1, { enemies, encounters });
        expect(runChance(base, base.combatants['hero'])).toBeCloseTo(0.55);
    });

    it('failure costs the turn; success ends the battle as fled', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const fail = resolveAction(state, { type: 'run', actor: 'hero' }, seq(0.99), defs);
        expect(fail.events.some((e) => e.type === 'runFailed')).toBe(true);
        expect(state.outcome).toBe('ongoing');

        const ok = resolveAction(state, { type: 'run', actor: 'hero' }, seq(0.0), defs);
        expect(ok.events.some((e) => e.type === 'fled')).toBe(true);
        expect(state.outcome).toBe('fled');
    });
});

describe('Spider telegraph cycle (§5.3)', () => {
    it('tells first, then bites for 2× — the bite only ever follows a tell', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const spider = state.combatants['spider-0'];

        // Turn 1: turnCount 0 → tell
        const first = chooseAction(state, 'spider-0', seq(0.5));
        expect(first.type).toBe('tell');
        const tellEvents = resolveAction(state, first, seq(0.5), defs);
        expect(tellEvents.events.some((e) => e.type === 'tellStarted')).toBe(true);
        expect(spider.tellPending).toBe(true);

        // Turn 2: bite at 2× — spider ATK 7 vs hero DEF 5 → raw [7,11] → [14,22]
        const second = chooseAction(state, 'spider-0', seq(0.5));
        expect(second.type).toBe('attack');
        const { events } = resolveAction(state, second, mulberry32(42), defs);
        const [dmg] = damageEvents(events);
        expect(dmg.amount).toBeGreaterThanOrEqual(14);
        expect(dmg.amount).toBeLessThanOrEqual(22);
        expect(spider.tellPending).toBe(false);
    });
});

describe('Revenant revive (§5.3)', () => {
    function kill(state: ReturnType<typeof createBattle>, reviveRoll: number) {
        // Massive ATK guarantees lethal damage; second rng value decides revive.
        state.combatants['hero'].stats.atk = 99;
        return resolveAction(
            state,
            { type: 'attack', actor: 'hero', target: 'revenant-0' },
            seq(0.5, reviveRoll),
            defs
        );
    }

    it('revives at most once', () => {
        const state = createBattle('enc-revenant', hero, 1, { enemies, encounters });
        const rev = state.combatants['revenant-0'];

        const first = kill(state, 0.0); // 0.0 < 0.5 → revive
        expect(first.events.some((e) => e.type === 'revived')).toBe(true);
        expect(rev.stats.hp).toBe(12);
        expect(rev.hasRevived).toBe(true);
        expect(rev.alive).toBe(true);

        const second = kill(state, 0.0); // would pass the roll, but hasRevived blocks it
        expect(second.events.some((e) => e.type === 'defeated')).toBe(true);
        expect(rev.alive).toBe(false);
        expect(state.outcome).toBe('victory');
    });

    it('can fail its revive roll and die outright', () => {
        const state = createBattle('enc-revenant', hero, 1, { enemies, encounters });
        const { events } = kill(state, 0.9); // 0.9 ≥ 0.5 → no revive
        expect(events.some((e) => e.type === 'defeated')).toBe(true);
        expect(state.outcome).toBe('victory');
    });
});

describe('Boss phase change (§5.3)', () => {
    it('fires exactly once at ≤ 50% HP and adds the permanent ATK mod', () => {
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        const boss = state.combatants['chimera-0'];
        boss.stats.hp = 34; // threshold is floor(66·50/100) = 33

        // rand = 0 → dmg 11 → hp 23 ≤ 33 → phase change
        const { events } = resolveAction(
            state,
            { type: 'attack', actor: 'hero', target: 'chimera-0' },
            seq(0.4),
            defs
        );
        expect(events.filter((e) => e.type === 'phaseChanged')).toHaveLength(1);
        expect(boss.phase).toBe(1);
        expect(boss.mods).toContainEqual({ stat: 'atk', pct: 30, turnsLeft: -1, source: 'phase' });

        // Further damage: no second phase change
        const again = resolveAction(
            state,
            { type: 'attack', actor: 'hero', target: 'chimera-0' },
            seq(0.4),
            defs
        );
        expect(again.events.some((e) => e.type === 'phaseChanged')).toBe(false);

        // Phase-1 AI telegraphs Flame Breath, then casts it
        boss.turnCount = 3;
        const tell = chooseAction(state, 'chimera-0', seq(0.5));
        expect(tell.type).toBe('tell');
        resolveAction(state, tell, seq(0.5), defs);
        const breath = chooseAction(state, 'chimera-0', seq(0.5));
        expect(breath).toMatchObject({ type: 'cast', spellId: 'flameBreath' });
    });
});

describe('restoreMp (M10 amendment)', () => {
    it('restores MP capped at maxMp and emits mpRestored', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const heroC = state.combatants['hero'];
        heroC.stats.mp = 2;
        state.inventory.push({ itemId: 'manaMoss', qty: 2 });

        const first = resolveAction(
            state,
            { type: 'useItem', actor: 'hero', itemId: 'manaMoss', target: 'hero' },
            seq(0.5),
            defs
        );
        expect(first.events.find((e) => e.type === 'mpRestored')).toMatchObject({ amount: 6 });
        expect(heroC.stats.mp).toBe(8);

        // Second moss: only 2 MP of headroom — capped.
        const second = resolveAction(
            state,
            { type: 'useItem', actor: 'hero', itemId: 'manaMoss', target: 'hero' },
            seq(0.5),
            defs
        );
        expect(second.events.find((e) => e.type === 'mpRestored')).toMatchObject({ amount: 2 });
        expect(heroC.stats.mp).toBe(10);
    });
});

describe('items (§5.2)', () => {
    it('herb heals, capped at maxHp, and decrements the stack', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 35;
        const { events } = resolveAction(
            state,
            { type: 'useItem', actor: 'hero', itemId: 'herb', target: 'hero' },
            seq(0.5),
            defs
        );
        const heal = events.find((e) => e.type === 'heal');
        expect(heal).toMatchObject({ amount: 5 }); // capped at maxHp 40
        expect(state.inventory.find((s) => s.itemId === 'herb')?.qty).toBe(1);
    });

    it('power bottle is a free action carrying the Power buff', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        const { events } = resolveAction(
            state,
            { type: 'useItem', actor: 'hero', itemId: 'powerBottle', target: 'hero' },
            seq(0.5),
            defs
        );
        expect(events.find((e) => e.type === 'itemUsed')).toMatchObject({ free: true });
        expect(events.find((e) => e.type === 'buffApplied')).toMatchObject({ stat: 'atk', pct: 50 });
        expect(state.inventory.find((s) => s.itemId === 'powerBottle')?.qty).toBe(0);
    });
});
