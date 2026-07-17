// M1 FROZEN CONTRACT (§7 of docs/PLAN.md).
// Cross-scene handoff types (§4). The runtime facade over Phaser's
// DataManager lives in src/systems/registry.ts (Engine/Systems lane) — this
// file is pure types, no Phaser imports.

import type { HeroState } from './data';

export interface BattleRequest {
    encounterId: string;
    seed: number;
    source: 'overworld' | 'debug';
}

export interface BattleResult {
    outcome: 'victory' | 'defeat' | 'fled';
    heroSnapshot: HeroState;
    itemsDropped?: string[];
}

export interface RegistryShape {
    hero: HeroState;
    battleRequest: BattleRequest | null;
    lastBattleResult: BattleResult | null;
    flags: Record<string, boolean>;
}

export type { HeroState };
