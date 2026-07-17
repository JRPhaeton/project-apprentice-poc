import type { BattleState, Combatant } from '../contracts/battle';
import type { EncountersFile, EnemiesFile, HeroState } from '../contracts/data';

/**
 * Builds the initial BattleState from content data (§4). Data is injected —
 * never imported from src/data directly — so tests can run against frozen
 * fixtures (§10 goldens) while the game passes live data.
 */
export function createBattle(
    encounterId: string,
    hero: HeroState,
    seed: number,
    defs: { enemies: EnemiesFile; encounters: EncountersFile }
): BattleState {
    const encounter = defs.encounters[encounterId];
    if (!encounter) {
        throw new Error(`Unknown encounter: ${encounterId}`);
    }

    const heroCombatant: Combatant = {
        id: 'hero',
        defId: 'hero',
        name: hero.name,
        side: 'hero',
        stats: { ...hero.stats },
        mods: [],
        turnCount: 0,
        tellPending: false,
        hasRevived: false,
        phase: 0,
        defending: false,
        nextAttackMult: 1,
        alive: true
    };

    const combatants: Record<string, Combatant> = { hero: heroCombatant };
    const order = ['hero'];

    encounter.enemies.forEach((defId, i) => {
        const def = defs.enemies[defId];
        if (!def) {
            throw new Error(`Unknown enemy def: ${defId}`);
        }
        const id = `${defId}-${i}`;
        combatants[id] = {
            id,
            defId,
            name: def.name,
            side: 'enemy',
            stats: {
                maxHp: def.hp,
                hp: def.hp,
                maxMp: 0,
                mp: 0,
                atk: def.atk,
                def: def.def,
                spd: def.spd
            },
            mods: [],
            turnCount: 0,
            tellPending: false,
            hasRevived: false,
            phase: 0,
            defending: false,
            nextAttackMult: 1,
            alive: true,
            ai: def.ai
        };
        order.push(id);
    });

    return {
        seed,
        round: 1,
        heroId: 'hero',
        combatants,
        order,
        inventory: hero.inventory.map((s) => ({ ...s })),
        outcome: 'ongoing'
    };
}
