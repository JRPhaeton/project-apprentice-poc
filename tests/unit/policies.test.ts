import { describe, expect, it } from 'vitest';

import type { Rng } from '../../src/core/contracts/battle';
import type { EncountersFile, EnemiesFile, HeroState } from '../../src/core/contracts/data';
import { itemsFileSchema, spellsFileSchema } from '../../src/core/contracts/data';
import { createBattle } from '../../src/core/battle/factory';
import { attackOnlyPolicy, policies, tacticalPolicy } from '../../src/core/battle/policies';
import { resolveAction } from '../../src/core/battle/resolver';
import type { ContentDefs } from '../../src/core/battle/resolver';
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
    'enc-spider-wisp': { id: 'enc-spider-wisp', enemies: ['spider', 'wisp'], boss: false },
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

describe('attackOnlyPolicy (§5.2 careless baseline)', () => {
    it('always attacks the first living enemy in order', () => {
        const state = createBattle('enc-spider-wisp', hero, 1, { enemies, encounters });
        expect(attackOnlyPolicy(state, defs)).toEqual({
            type: 'attack',
            actor: 'hero',
            target: 'spider-0'
        });
    });

    it('retargets past dead enemies', () => {
        const state = createBattle('enc-spider-wisp', hero, 1, { enemies, encounters });
        state.combatants['spider-0'].alive = false;
        expect(attackOnlyPolicy(state, defs)).toMatchObject({ type: 'attack', target: 'wisp-1' });
    });

    it('never defends or heals, even at death\'s door', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 3;
        state.combatants['spider-0'].tellPending = true;
        expect(attackOnlyPolicy(state, defs).type).toBe('attack');
    });
});

describe('tacticalPolicy (§10 correct play)', () => {
    it('defends when any living enemy has a tell pending', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['spider-0'].tellPending = true;
        expect(tacticalPolicy(state, defs)).toEqual({ type: 'defend', actor: 'hero' });
    });

    it('defend-on-tell outranks healing', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['spider-0'].tellPending = true;
        state.combatants['hero'].stats.hp = 5;
        expect(tacticalPolicy(state, defs).type).toBe('defend');
    });

    it('uses the free-action Power Bottle at battle start vs the boss, then attacks', () => {
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        const first = tacticalPolicy(state, defs);
        expect(first).toEqual({
            type: 'useItem',
            actor: 'hero',
            itemId: 'powerBottle',
            target: 'hero'
        });

        // §5.2 free action: the bottle does not consume the turn — the
        // follow-up pick is the normal action, now powered → attack.
        resolveAction(state, first, seq(0.5), defs);
        expect(tacticalPolicy(state, defs)).toEqual({
            type: 'attack',
            actor: 'hero',
            target: 'chimera-0'
        });
    });

    it('casts Power at boss battle start when no bottle remains', () => {
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        state.inventory = [{ itemId: 'herb', qty: 2 }];
        expect(tacticalPolicy(state, defs)).toEqual({
            type: 'cast',
            actor: 'hero',
            spellId: 'power',
            target: 'hero'
        });
    });

    it('attacks at boss start when neither bottle nor MP can buy Power', () => {
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        state.inventory = [];
        state.combatants['hero'].stats.mp = 2; // Power costs 3
        expect(tacticalPolicy(state, defs)).toMatchObject({ type: 'attack', target: 'chimera-0' });
    });

    it('only powers up at battle start (round 1)', () => {
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        state.round = 2;
        expect(tacticalPolicy(state, defs)).toMatchObject({ type: 'attack', target: 'chimera-0' });
    });

    it('does not power up against non-boss encounters', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        expect(tacticalPolicy(state, defs)).toMatchObject({ type: 'attack', target: 'spider-0' });
    });

    it('casts Heal below 33% maxHp when MP suffices', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 13; // 13 < 40·0.33 = 13.2
        expect(tacticalPolicy(state, defs)).toEqual({
            type: 'cast',
            actor: 'hero',
            spellId: 'heal',
            target: 'hero'
        });
    });

    it('does not heal at or above the threshold', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 14; // 14 ≥ 13.2
        expect(tacticalPolicy(state, defs)).toMatchObject({ type: 'attack' });
    });

    it('falls back to Herb when MP cannot buy Heal', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 13;
        state.combatants['hero'].stats.mp = 3; // Heal costs 4
        expect(tacticalPolicy(state, defs)).toEqual({
            type: 'useItem',
            actor: 'hero',
            itemId: 'herb',
            target: 'hero'
        });
    });

    it('attacks when low but out of both MP and Herbs', () => {
        const state = createBattle('enc-spider', hero, 1, { enemies, encounters });
        state.combatants['hero'].stats.hp = 13;
        state.combatants['hero'].stats.mp = 3;
        state.inventory = [{ itemId: 'powerBottle', qty: 1 }]; // no herb
        expect(tacticalPolicy(state, defs)).toMatchObject({ type: 'attack', target: 'spider-0' });
    });
});

describe('policy registry', () => {
    it('exposes both §10 policies by name, deterministically', () => {
        expect(Object.keys(policies).sort()).toEqual(['attackOnly', 'tactical']);
        const state = createBattle('enc-boss', hero, 1, { enemies, encounters });
        expect(policies.tactical(state, defs)).toEqual(policies.tactical(state, defs));
        expect(policies.attackOnly(state, defs)).toEqual(policies.attackOnly(state, defs));
    });
});
