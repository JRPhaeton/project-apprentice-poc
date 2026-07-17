import type Phaser from 'phaser';

import type { RegistryShape } from '../core/contracts/registry';
import type { GameDefs } from './content';

/**
 * Typed facade over Phaser's DataManager (§4 of docs/PLAN.md). The frozen
 * contract shape (RegistryShape) is extended here with engine-internal keys —
 * the contract file itself is untouched. The DataManager is injected so this
 * stays trivially testable; the TYPE layer (RegistryShape) has no Phaser
 * import — only this runtime facade does.
 */
export interface EngineRegistryShape extends RegistryShape {
    /** Parsed content defs — zod-validated once at boot (§3). */
    defs: GameDefs;
    /** Where to put the hero back after a battle, else null (fresh spawn). */
    overworldReturn: { x: number; y: number } | null;
    /** Current room id, persisted in the save blob. */
    room: string;
    /** Session stats for the Victory screen. */
    stats: { battlesWon: number; xpEarned: number };
}

export class GameRegistry {
    constructor(private readonly dm: Phaser.Data.DataManager) {}

    get<K extends keyof EngineRegistryShape>(key: K): EngineRegistryShape[K] {
        return this.dm.get(key as string) as EngineRegistryShape[K];
    }

    set<K extends keyof EngineRegistryShape>(key: K, value: EngineRegistryShape[K]): void {
        this.dm.set(key as string, value);
    }
}

/** The game-wide registry facade (wraps game.registry). */
export function getRegistry(scene: Phaser.Scene): GameRegistry {
    return new GameRegistry(scene.registry);
}
