import type { Action, BattleState, Rng } from '../contracts/battle';
import type { EncountersFile, EnemiesFile, HeroDef, HeroState } from '../contracts/data';
import { runEnemyPhase } from './driver';
import { createBattle } from './factory';
import { policies } from './policies';
import type { PolicyName } from './policies';
import { heroStateFromDef } from './progression';
import { resolveAction } from './resolver';
import type { ContentDefs } from './resolver';
import { mulberry32 } from './rng';

/**
 * §10 balance simulation harness. Pure/headless: seeded battles through the
 * exact production path (createBattle → policy → resolveAction →
 * runEnemyPhase), one mulberry32(seed) stream per battle (per gauntlet run
 * for runGauntletSim). Deterministic for a given (policy, encounter, seeds,
 * data) tuple, so it doubles as a data-regression assertion in CI.
 *
 * The §5.2 lethality thresholds are NOT asserted here — the sim reports;
 * the M3 tuning task brings src/data into line and adds the CI assertions.
 */
export interface SimDefs extends ContentDefs {
    enemies: EnemiesFile;
    encounters: EncountersFile;
}

export interface SimResult {
    wins: number;
    losses: number;
    fled: number;
    winRate: number;
    medianEndHp: number;
    meanRounds: number;
}

export interface GauntletResult {
    /** Fraction of seeds that won every encounter, boss included. */
    survivalRate: number;
    /** Count of seeds that survived to enter the final (boss) encounter. */
    bossReached: number;
}

/** Hard cap: a battle still ongoing after this many full rounds is a loss. */
export const ROUND_CAP = 100;

function isFreeItemAction(action: Action, defs: ContentDefs): boolean {
    return action.type === 'useItem' && defs.items[action.itemId]?.freeAction === true;
}

/**
 * One hero turn under a policy. §5.2 free action: a freeAction item applies
 * without consuming the turn, so the policy is consulted again for its one
 * normal action — at most one free action per turn (the follow-up gets no
 * further bonus even if it is itself a freeAction item).
 */
function runHeroTurn(state: BattleState, policyName: PolicyName, rng: Rng, defs: SimDefs): void {
    const policy = policies[policyName];
    const action = policy(state, defs);
    resolveAction(state, action, rng, defs);
    if (isFreeItemAction(action, defs) && state.outcome === 'ongoing') {
        resolveAction(state, policy(state, defs), rng, defs);
    }
}

/** Plays one battle to its end (or the round cap), mutating `state`. */
function runBattle(state: BattleState, policyName: PolicyName, rng: Rng, defs: SimDefs): void {
    while (state.outcome === 'ongoing' && state.round <= ROUND_CAP) {
        runHeroTurn(state, policyName, rng, defs);
        if (state.outcome !== 'ongoing') {
            return;
        }
        runEnemyPhase(state, rng, defs); // includes endRound → round increment
    }
}

function median(values: number[]): number {
    if (values.length === 0) {
        return 0;
    }
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Runs one encounter under one policy across all seeds (fresh hero each). */
export function runSim(
    policyName: PolicyName,
    encounterId: string,
    seeds: number[],
    defs: SimDefs,
    heroDef: HeroDef
): SimResult {
    let wins = 0;
    let losses = 0;
    let fled = 0;
    const endHps: number[] = [];
    let totalRounds = 0;

    for (const seed of seeds) {
        const rng = mulberry32(seed);
        const state = createBattle(encounterId, heroStateFromDef(heroDef), seed, defs);
        runBattle(state, policyName, rng, defs);

        if (state.outcome === 'victory') {
            wins += 1;
        } else if (state.outcome === 'fled') {
            fled += 1;
        } else {
            losses += 1; // defeat, or still ongoing at the round cap
        }
        endHps.push(state.combatants[state.heroId].stats.hp);
        totalRounds += Math.min(state.round, ROUND_CAP);
    }

    const n = seeds.length;
    return {
        wins,
        losses,
        fled,
        winRate: n === 0 ? 0 : wins / n,
        medianEndHp: median(endHps),
        meanRounds: n === 0 ? 0 : totalRounds / n
    };
}

/**
 * §10 item 2 — the no-heal gauntlet: sequential encounters on ONE shared
 * hero hp/mp/inventory pool, no rests. The last encounterId is the boss.
 * One mulberry32(seed) stream carries across a seed's whole gauntlet run.
 *
 * Deliberately excludes victory-XP leveling: the full-heal ding
 * (progression.ts) would act as a rest and mask the attrition PLAN §10
 * measures. Whether the tuned M3 sim levels mid-gauntlet is an M3 call.
 */
export function runGauntletSim(
    policyName: PolicyName,
    encounterIds: string[],
    seeds: number[],
    defs: SimDefs,
    heroDef: HeroDef
): GauntletResult {
    let survived = 0;
    let bossReached = 0;
    const bossIndex = encounterIds.length - 1;

    for (const seed of seeds) {
        const rng = mulberry32(seed);
        let hero: HeroState = heroStateFromDef(heroDef);
        let alive = true;

        for (let i = 0; i < encounterIds.length; i++) {
            if (i === bossIndex) {
                bossReached += 1;
            }
            const state = createBattle(encounterIds[i], hero, seed, defs);
            runBattle(state, policyName, rng, defs);
            if (state.outcome !== 'victory') {
                alive = false;
                break;
            }
            // Carry the shared pool forward: hp/mp as they ended, spent items gone.
            const end = state.combatants[state.heroId].stats;
            hero = {
                ...hero,
                stats: { ...hero.stats, hp: end.hp, mp: end.mp },
                inventory: state.inventory.filter((s) => s.qty > 0).map((s) => ({ ...s }))
            };
        }

        if (alive) {
            survived += 1;
        }
    }

    return {
        survivalRate: seeds.length === 0 ? 0 : survived / seeds.length,
        bossReached
    };
}
