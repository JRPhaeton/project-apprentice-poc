import type Phaser from 'phaser';

import type { BattleRequest } from '../core/contracts/registry';
import { makeBattleRequest, setSeedOverride } from './battle-request';
import { freshHero, loadContent } from './content';
import { readDebugOptions } from './debug';
import { setTurbo } from './pacing';
import { getRegistry, type GameRegistry } from './registry';

/**
 * One-shot boot init (called from Boot.create): parse content ONCE (zod in
 * dev builds only, §3 of docs/PLAN.md), seed the typed registry with a fresh
 * game state (Title applies a save on CONTINUE), and read the debug hooks.
 * Returns a BattleRequest when ?scene=battle&enemy=<id> asks for a direct
 * jump — built through the same makeBattleRequest factory as the overworld.
 */
export function bootGame(scene: Phaser.Scene): { reg: GameRegistry; jump: BattleRequest | null } {
    const defs = loadContent();
    const reg = getRegistry(scene);
    reg.set('defs', defs);
    reg.set('hero', freshHero(defs.hero));
    reg.set('flags', {});
    reg.set('battleRequest', null);
    reg.set('lastBattleResult', null);
    reg.set('overworldReturn', null);
    reg.set('room', 'room2-forest');
    reg.set('stats', { battlesWon: 0, xpEarned: 0 });

    const dbg = readDebugOptions();
    if (dbg.turbo) {
        setTurbo(true);
    }
    if (dbg.seed !== null) {
        setSeedOverride(dbg.seed);
    }

    let jump: BattleRequest | null = null;
    if (dbg.jumpEncounterId && defs.encounters[dbg.jumpEncounterId]) {
        jump = makeBattleRequest({
            encounterId: dbg.jumpEncounterId,
            seed: dbg.seed ?? undefined,
            source: 'debug'
        });
    }
    return { reg, jump };
}
