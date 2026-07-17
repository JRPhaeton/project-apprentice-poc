import type {
    Action,
    BattleEvent,
    BattleState,
    Combatant,
    CombatantId,
    Rng,
    Stat,
    StatMod
} from '../contracts/battle';
import type { ItemsFile, SpellsFile } from '../contracts/data';
import { randInt } from './rng';

/**
 * Pure combat resolver (§4/§5 of docs/PLAN.md). No Phaser, no Math.random —
 * all randomness through the injected seeded Rng. The BattleScene consumes
 * the returned events and animates them; it never computes outcomes.
 *
 * Damage model (§5.2), fixed here so tests can pin it:
 *   raw = effAtk * 2 − effDef + rand(−2..2)
 *   dmg = max(1, round(raw × offMult × defendMult))
 * where offMult combines the attacker's consumed nextAttackMult (Defend
 * boost ×1.5), the tell multiplier on a telegraphed hit, or a spell's mult;
 * defendMult is 0.5 while the target is defending. Stat mods are additive
 * percentages on the BASE stat (§5.2).
 */

export interface ContentDefs {
    spells: SpellsFile;
    items: ItemsFile;
}

export function effectiveStat(c: Combatant, stat: Stat): number {
    const base = c.stats[stat];
    const pct = c.mods.filter((m) => m.stat === stat).reduce((sum, m) => sum + m.pct, 0);
    return Math.max(0, Math.round(base * (1 + pct / 100)));
}

function applyBuff(
    target: Combatant,
    stat: Stat,
    pct: number,
    turns: number,
    source: string,
    events: BattleEvent[]
): void {
    // §5.2: same-buff reapplication refreshes duration, never stacks.
    const existing = target.mods.find((m) => m.source === source && m.stat === stat);
    if (existing) {
        existing.turnsLeft = turns;
    } else {
        target.mods.push({ stat, pct, turnsLeft: turns, source });
    }
    events.push({ type: 'buffApplied', target: target.id, stat, pct, turns });
}

function dealDamage(
    rng: Rng,
    source: Combatant,
    target: Combatant,
    offMult: number,
    kind: 'attack' | 'spell',
    events: BattleEvent[]
): void {
    const raw = effectiveStat(source, 'atk') * 2 - effectiveStat(target, 'def') + randInt(rng, -2, 2);
    const defendMult = target.defending ? 0.5 : 1;
    const amount = Math.max(1, Math.round(raw * offMult * defendMult));
    target.stats.hp = Math.max(0, target.stats.hp - amount);
    events.push({ type: 'damage', source: source.id, target: target.id, amount, kind });

    if (target.stats.hp > 0) {
        maybePhaseChange(target, events);
        return;
    }

    // Reviver (§5.3): one-time self-revive on lethal damage.
    if (target.ai?.kind === 'reviver' && !target.hasRevived && rng.next() < target.ai.reviveChance) {
        target.hasRevived = true;
        target.stats.hp = target.ai.reviveHp;
        events.push({ type: 'revived', actor: target.id, hp: target.ai.reviveHp });
        return;
    }

    target.alive = false;
    events.push({ type: 'defeated', actor: target.id });
}

/** Boss phase change (§5.3): fires exactly once when HP first crosses the threshold. */
function maybePhaseChange(target: Combatant, events: BattleEvent[]): void {
    if (target.ai?.kind !== 'boss' || target.phase !== 0) {
        return;
    }
    if (target.stats.hp <= Math.floor((target.stats.maxHp * target.ai.phaseAtPct) / 100)) {
        target.phase = 1;
        target.mods.push({
            stat: 'atk',
            pct: target.ai.phaseAtkPct,
            turnsLeft: -1,
            source: 'phase'
        });
        events.push({ type: 'phaseChanged', actor: target.id, phase: 1 });
    }
}

/** Run chance (§5.2): clamp(0.5 + (heroSPD − avgEnemySPD) × 0.05, 0.25, 0.95). */
export function runChance(state: BattleState, actor: Combatant): number {
    const enemies = livingEnemies(state);
    const avgSpd = enemies.reduce((s, e) => s + effectiveStat(e, 'spd'), 0) / Math.max(1, enemies.length);
    return Math.min(0.95, Math.max(0.25, 0.5 + (effectiveStat(actor, 'spd') - avgSpd) * 0.05));
}

function livingEnemies(state: BattleState): Combatant[] {
    return state.order
        .map((id) => state.combatants[id])
        .filter((c) => c.side === 'enemy' && c.alive);
}

function checkOutcome(state: BattleState, events: BattleEvent[]): void {
    const hero = state.combatants[state.heroId];
    if (!hero.alive || hero.stats.hp <= 0) {
        hero.alive = false;
        state.outcome = 'defeat';
        events.push({ type: 'battleEnded', outcome: 'defeat' });
    } else if (livingEnemies(state).length === 0) {
        state.outcome = 'victory';
        events.push({ type: 'battleEnded', outcome: 'victory' });
    }
}

export function resolveAction(
    state: BattleState,
    action: Action,
    rng: Rng,
    defs: ContentDefs
): { state: BattleState; events: BattleEvent[] } {
    if (state.outcome !== 'ongoing') {
        return { state, events: [] };
    }

    const events: BattleEvent[] = [];
    const actor = state.combatants[action.actor];
    if (!actor || !actor.alive) {
        return { state, events };
    }

    events.push({ type: 'turnStarted', actor: actor.id });

    switch (action.type) {
        case 'attack': {
            const target = state.combatants[action.target];
            if (!target || !target.alive) {
                break;
            }
            let offMult = 1;
            if (actor.nextAttackMult !== 1) {
                offMult *= actor.nextAttackMult;
                actor.nextAttackMult = 1; // §5.2: consumed on this attack
            }
            if (actor.tellPending && actor.ai?.kind === 'telegraph') {
                offMult *= actor.ai.tellDamageMult;
                actor.tellPending = false;
            }
            dealDamage(rng, actor, target, offMult, 'attack', events);
            break;
        }

        case 'defend': {
            actor.defending = true;
            actor.nextAttackMult = 1.5;
            events.push({ type: 'defendStarted', actor: actor.id });
            break;
        }

        case 'cast': {
            const spell = defs.spells[action.spellId];
            const target = state.combatants[action.target];
            if (!spell || !target) {
                break;
            }
            if (actor.stats.mp < spell.mpCost) {
                break;
            }
            if (spell.mpCost > 0) {
                actor.stats.mp -= spell.mpCost;
                events.push({ type: 'mpSpent', actor: actor.id, amount: spell.mpCost });
            }
            applyEffect(rng, actor, target, spell.effect, spell.id, events);
            if (actor.tellPending) {
                actor.tellPending = false; // telegraphed casts (Flame Breath) land here
            }
            break;
        }

        case 'useItem': {
            const item = defs.items[action.itemId];
            const stack = state.inventory.find((s) => s.itemId === action.itemId);
            const target = state.combatants[action.target];
            if (!item || !stack || stack.qty <= 0 || !target) {
                break;
            }
            stack.qty -= 1;
            events.push({ type: 'itemUsed', actor: actor.id, itemId: item.id, free: item.freeAction });
            applyEffect(rng, actor, target, item.effect, item.id, events);
            break;
        }

        case 'run': {
            const p = runChance(state, actor);
            if (rng.next() < p) {
                state.outcome = 'fled';
                events.push({ type: 'fled', actor: actor.id });
                events.push({ type: 'battleEnded', outcome: 'fled' });
            } else {
                events.push({ type: 'runFailed', actor: actor.id });
            }
            break;
        }

        case 'tell': {
            actor.tellPending = true;
            events.push({ type: 'tellStarted', actor: actor.id });
            break;
        }
    }

    actor.turnCount += 1;
    if (state.outcome === 'ongoing') {
        checkOutcome(state, events);
    }
    return { state, events };
}

function applyEffect(
    rng: Rng,
    actor: Combatant,
    target: Combatant,
    effect: { kind: 'heal'; amount: number } | { kind: 'buff'; stat: Stat; pct: number; turns: number } | { kind: 'attack'; mult: number },
    source: string,
    events: BattleEvent[]
): void {
    switch (effect.kind) {
        case 'heal': {
            const healed = Math.min(effect.amount, target.stats.maxHp - target.stats.hp);
            target.stats.hp += healed;
            events.push({ type: 'heal', source: actor.id, target: target.id, amount: healed });
            break;
        }
        case 'buff': {
            applyBuff(target, effect.stat, effect.pct, effect.turns, source, events);
            break;
        }
        case 'attack': {
            dealDamage(rng, actor, target, effect.mult, 'spell', events);
            break;
        }
    }
}

/**
 * End-of-round bookkeeping (§5.2): tick buff durations (−1 mods are
 * permanent), clear Defend's damage-halving. The consumed-on-attack
 * nextAttackMult persists across rounds until spent.
 */
export function endRound(state: BattleState): { state: BattleState; events: BattleEvent[] } {
    const events: BattleEvent[] = [];
    for (const id of state.order) {
        const c = state.combatants[id];
        c.defending = false;
        const keep: StatMod[] = [];
        for (const mod of c.mods) {
            if (mod.turnsLeft === -1) {
                keep.push(mod);
                continue;
            }
            mod.turnsLeft -= 1;
            if (mod.turnsLeft > 0) {
                keep.push(mod);
            } else {
                events.push({ type: 'buffExpired', target: id, stat: mod.stat });
            }
        }
        c.mods = keep;
    }
    state.round += 1;
    events.push({ type: 'roundStarted', round: state.round });
    return { state, events };
}

/**
 * Enemy AI (§4): pure per-turn action selection dispatching on the `ai`
 * discriminated union. Threshold/death triggers (revive, phase change) live
 * in resolveAction's damage path, not here.
 */
export function chooseAction(state: BattleState, enemyId: CombatantId, rng: Rng): Action {
    const enemy = state.combatants[enemyId];
    const heroId = state.heroId;
    const attack: Action = { type: 'attack', actor: enemyId, target: heroId };
    if (!enemy.ai) {
        return attack;
    }

    switch (enemy.ai.kind) {
        case 'telegraph': {
            if (enemy.tellPending) {
                return attack; // the telegraphed 2× bite
            }
            if (enemy.turnCount % enemy.ai.tellEvery === 0) {
                return { type: 'tell', actor: enemyId };
            }
            return attack;
        }
        case 'caster': {
            if (rng.next() < enemy.ai.chance) {
                return { type: 'cast', actor: enemyId, spellId: enemy.ai.spellId, target: heroId };
            }
            return attack;
        }
        case 'reviver': {
            return attack;
        }
        case 'boss': {
            if (enemy.phase >= 1) {
                if (enemy.tellPending) {
                    return { type: 'cast', actor: enemyId, spellId: enemy.ai.phaseUnlock, target: heroId };
                }
                if (enemy.turnCount % 3 === 0) {
                    return { type: 'tell', actor: enemyId }; // Flame Breath always telegraphed (§5.3)
                }
            }
            return attack;
        }
    }
}
