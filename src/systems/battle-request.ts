import type { BattleRequest } from '../core/contracts/registry';

/**
 * The ONE shared factory for battle payloads (§4 of docs/PLAN.md, frozen
 * handoff): both the overworld encounter trigger and the debug ?scene=battle
 * jump route through here, so the tested path equals the production path.
 */

// Seed counter, seeded once per session. Not core — Date.now is fine here.
let counter = Date.now() >>> 0;

/** Debug ?seed= override (set at boot when VITE_ENABLE_DEBUG is on). */
let seedOverride: number | null = null;

export function setSeedOverride(seed: number): void {
    seedOverride = seed >>> 0;
}

function nextSeed(): number {
    counter = (counter + 0x9e3779b9) >>> 0;
    return counter;
}

export function makeBattleRequest(opts: {
    encounterId: string;
    seed?: number;
    source: 'overworld' | 'debug';
}): BattleRequest {
    return {
        encounterId: opts.encounterId,
        seed: (opts.seed ?? seedOverride ?? nextSeed()) >>> 0,
        source: opts.source
    };
}
