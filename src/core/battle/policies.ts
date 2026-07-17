import type { Action, BattleState, Combatant } from '../contracts/battle';
import type { ContentDefs } from './resolver';

/**
 * Scripted hero policies for the §10 balance sim. Deterministic — no rng of
 * their own (the only randomness in a simmed battle is the resolver's
 * injected Rng). Each policy picks the hero's action for the current turn.
 *
 * Data IDs are the GDD-locked spell/item ids (heal/power/herb/powerBottle);
 * the policies gate every pick on the id actually resolving in `defs`.
 */
export type HeroPolicy = (state: BattleState, defs: ContentDefs) => Action;

const HEAL_SPELL = 'heal';
const POWER_SPELL = 'power';
const HERB_ITEM = 'herb';
const POWER_BOTTLE_ITEM = 'powerBottle';

function livingEnemies(state: BattleState): Combatant[] {
    return state.order
        .map((id) => state.combatants[id])
        .filter((c) => c.side === 'enemy' && c.alive);
}

function firstLivingEnemy(state: BattleState): Combatant {
    const enemy = livingEnemies(state)[0];
    if (!enemy) {
        throw new Error('policy invoked with no living enemies');
    }
    return enemy;
}

function itemQty(state: BattleState, itemId: string): number {
    return state.inventory.find((s) => s.itemId === itemId)?.qty ?? 0;
}

/**
 * Careless baseline (§5.2/§10 "always-attack, never defend/heal/buff"):
 * always attack the first living enemy in order.
 */
export const attackOnlyPolicy: HeroPolicy = (state) => {
    return { type: 'attack', actor: state.heroId, target: firstLivingEnemy(state).id };
};

/**
 * Correct play (§10 "defend-on-tell + Power before boss + Heal below 33%"):
 * 1. Defend when any living enemy has a tell pending (ride out the 2× hit,
 *    counter with the consumed ×1.5).
 * 2. At battle start (round 1) vs the boss, put Power up — the free-action
 *    Power Bottle first if available (the sim grants the follow-up normal
 *    action per §5.2), else cast Power if MP suffices.
 * 3. Heal when hp < 33% of maxHp: cast Heal if MP suffices, else Herb if any.
 * 4. Otherwise attack the first living enemy.
 */
export const tacticalPolicy: HeroPolicy = (state, defs) => {
    const hero = state.combatants[state.heroId];
    const enemies = livingEnemies(state);

    if (enemies.some((e) => e.tellPending)) {
        return { type: 'defend', actor: hero.id };
    }

    const bossPresent = enemies.some((e) => e.ai?.kind === 'boss');
    const powered = hero.mods.some((m) => m.stat === 'atk' && m.pct > 0);
    if (bossPresent && state.round === 1 && !powered) {
        if (defs.items[POWER_BOTTLE_ITEM] && itemQty(state, POWER_BOTTLE_ITEM) > 0) {
            return { type: 'useItem', actor: hero.id, itemId: POWER_BOTTLE_ITEM, target: hero.id };
        }
        const power = defs.spells[POWER_SPELL];
        if (power && hero.stats.mp >= power.mpCost) {
            return { type: 'cast', actor: hero.id, spellId: POWER_SPELL, target: hero.id };
        }
    }

    if (hero.stats.hp < hero.stats.maxHp * 0.33) {
        const heal = defs.spells[HEAL_SPELL];
        if (heal && hero.stats.mp >= heal.mpCost) {
            return { type: 'cast', actor: hero.id, spellId: HEAL_SPELL, target: hero.id };
        }
        if (defs.items[HERB_ITEM] && itemQty(state, HERB_ITEM) > 0) {
            return { type: 'useItem', actor: hero.id, itemId: HERB_ITEM, target: hero.id };
        }
    }

    return { type: 'attack', actor: hero.id, target: firstLivingEnemy(state).id };
};

export const policies = {
    attackOnly: attackOnlyPolicy,
    tactical: tacticalPolicy
} as const;

export type PolicyName = keyof typeof policies;
