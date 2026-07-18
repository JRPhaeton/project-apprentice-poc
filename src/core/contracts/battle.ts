// M1 FROZEN CONTRACT (§7 of docs/PLAN.md).
// Changes to this file require an orchestrator-approved PR touching
// src/core/contracts/** alone. No Phaser imports — ever.

export type CombatantId = string;

/** Seeded RNG (§4). The only randomness source the combat core may use. */
export interface Rng {
    /** Uniform float in [0, 1). */
    next(): number;
}

export type Stat = 'atk' | 'def' | 'spd';

export interface Stats {
    maxHp: number;
    hp: number;
    maxMp: number;
    mp: number;
    atk: number;
    def: number;
    spd: number;
}

/**
 * Additive percentage on the base stat, fixed duration, refresh-not-stack
 * (§5.2). `turnsLeft: -1` means permanent (boss phase ATK bonus).
 */
export interface StatMod {
    stat: Stat;
    pct: number;
    turnsLeft: number;
    source: string;
}

/** Per-enemy AI parameters, declared in enemies.json (§4). */
export type AiSpec =
    | { kind: 'telegraph'; tellEvery: number; tellDamageMult: number }
    | { kind: 'caster'; spellId: string; chance: number }
    | { kind: 'reviver'; reviveChance: number; reviveHp: number }
    | { kind: 'boss'; phaseAtPct: number; phaseAtkPct: number; phaseUnlock: string };

export interface Combatant {
    id: CombatantId;
    /** Key into enemies.json, or 'hero'. */
    defId: string;
    name: string;
    side: 'hero' | 'enemy';
    stats: Stats;
    // §4 runtime fields — part of the frozen contract so no lane re-invents them.
    mods: StatMod[];
    turnCount: number;
    tellPending: boolean;
    hasRevived: boolean;
    phase: number;
    /** Defend (§5.2): incoming damage ×0.5 this round. */
    defending: boolean;
    /** Defend (§5.2): next attack ×1.5, consumed on that attack. 1 = no boost. */
    nextAttackMult: number;
    alive: boolean;
    ai?: AiSpec;
}

export interface ItemStack {
    itemId: string;
    qty: number;
}

export type BattleOutcome = 'ongoing' | 'victory' | 'defeat' | 'fled';

export interface BattleState {
    seed: number;
    round: number;
    heroId: CombatantId;
    combatants: Record<CombatantId, Combatant>;
    /** Resolution order — hero first (§5.1 player-first alternation). */
    order: CombatantId[];
    inventory: ItemStack[];
    outcome: BattleOutcome;
}

export type Action =
    | { type: 'attack'; actor: CombatantId; target: CombatantId }
    | { type: 'defend'; actor: CombatantId }
    | { type: 'cast'; actor: CombatantId; spellId: string; target: CombatantId }
    | { type: 'useItem'; actor: CombatantId; itemId: string; target: CombatantId }
    | { type: 'run'; actor: CombatantId }
    | { type: 'tell'; actor: CombatantId };

/**
 * Everything the Phaser BattleScene animates. The scene consumes events and
 * never computes outcomes (§4).
 */
export type BattleEvent =
    | { type: 'roundStarted'; round: number }
    | { type: 'turnStarted'; actor: CombatantId }
    | { type: 'damage'; source: CombatantId; target: CombatantId; amount: number; kind: 'attack' | 'spell' }
    | { type: 'heal'; source: CombatantId; target: CombatantId; amount: number }
    | { type: 'mpSpent'; actor: CombatantId; amount: number }
    | { type: 'mpRestored'; target: CombatantId; amount: number }
    | { type: 'itemUsed'; actor: CombatantId; itemId: string; free: boolean }
    | { type: 'buffApplied'; target: CombatantId; stat: Stat; pct: number; turns: number }
    | { type: 'buffExpired'; target: CombatantId; stat: Stat }
    | { type: 'defendStarted'; actor: CombatantId }
    | { type: 'tellStarted'; actor: CombatantId }
    | { type: 'phaseChanged'; actor: CombatantId; phase: number }
    | { type: 'revived'; actor: CombatantId; hp: number }
    | { type: 'runFailed'; actor: CombatantId }
    | { type: 'fled'; actor: CombatantId }
    | { type: 'defeated'; actor: CombatantId }
    | { type: 'battleEnded'; outcome: BattleOutcome };
