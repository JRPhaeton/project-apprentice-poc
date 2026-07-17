import type { BattleEvent, BattleState, Rng } from '../contracts/battle';
import { chooseAction, endRound, resolveAction } from './resolver';
import type { ContentDefs } from './resolver';

/**
 * Enemy-phase driver (§5.1 player-first alternation). After the hero's
 * action(s) resolve, the scene (or sim) calls this once per round.
 *
 * For each living enemy in `state.order`: chooseAction → resolveAction,
 * stopping early the moment the battle is no longer ongoing (hero defeat,
 * flee — later enemies never act on a decided battle). If the battle is
 * still ongoing after every enemy has acted, end-of-round bookkeeping
 * (endRound: buff ticks, Defend clear, round increment) runs and its events
 * are appended.
 *
 * Pure — no Phaser; all randomness through the injected seeded Rng. Returns
 * the concatenated BattleEvent list for the scene to animate.
 */
export function runEnemyPhase(state: BattleState, rng: Rng, defs: ContentDefs): BattleEvent[] {
    const events: BattleEvent[] = [];
    if (state.outcome !== 'ongoing') {
        return events;
    }

    for (const id of state.order) {
        const combatant = state.combatants[id];
        if (combatant.side !== 'enemy' || !combatant.alive) {
            continue;
        }
        const action = chooseAction(state, id, rng);
        const { events: turnEvents } = resolveAction(state, action, rng, defs);
        events.push(...turnEvents);
        if (state.outcome !== 'ongoing') {
            return events; // battle decided mid-phase — no endRound, no further actors
        }
    }

    const { events: roundEvents } = endRound(state);
    events.push(...roundEvents);
    return events;
}
