import type { HeroDef, HeroState } from '../contracts/data';

/**
 * Minimal leveling on victory (PLAN §2 scope). Pure — no Phaser, no rng.
 *
 * XP curve (cumulative XP required to BE at each level), levels 1→5:
 *
 *   level:      1    2    3    4    5
 *   total XP:   0   10   25   45   70
 *
 * Level cap is 5: XP keeps accumulating past 70 but grants no further
 * levels. Per level gained: +5 maxHp, +2 maxMp, +1 atk, +1 def, +1 spd,
 * and hp/mp refill to the new max (classic full-heal ding). The
 * orchestrator records this curve in the GDD amendment log.
 */
export const XP_THRESHOLDS: readonly number[] = [0, 10, 25, 45, 70];

export const MAX_LEVEL = XP_THRESHOLDS.length;

export const LEVEL_GAINS = {
    maxHp: 5,
    maxMp: 2,
    atk: 1,
    def: 1,
    spd: 1
} as const;

/** Level (1..MAX_LEVEL) that a cumulative XP total corresponds to. */
export function levelForXp(xp: number): number {
    let level = 1;
    for (let i = 1; i < XP_THRESHOLDS.length; i++) {
        if (xp >= XP_THRESHOLDS[i]) {
            level = i + 1;
        }
    }
    return level;
}

export interface VictoryXpResult {
    hero: HeroState;
    leveledUp: boolean;
    levelsGained: number;
}

/**
 * Applies victory XP and any resulting level-ups. Pure: returns a new
 * HeroState, never mutates the input. A level never goes down.
 */
export function applyVictoryXp(hero: HeroState, xpGained: number): VictoryXpResult {
    const xp = hero.xp + xpGained;
    const newLevel = Math.max(hero.level, levelForXp(xp));
    const levelsGained = newLevel - hero.level;

    const stats = { ...hero.stats };
    if (levelsGained > 0) {
        stats.maxHp += LEVEL_GAINS.maxHp * levelsGained;
        stats.maxMp += LEVEL_GAINS.maxMp * levelsGained;
        stats.atk += LEVEL_GAINS.atk * levelsGained;
        stats.def += LEVEL_GAINS.def * levelsGained;
        stats.spd += LEVEL_GAINS.spd * levelsGained;
        // Full-heal ding: hp/mp refill to the NEW max on level-up.
        stats.hp = stats.maxHp;
        stats.mp = stats.maxMp;
    }

    return {
        hero: {
            ...hero,
            level: newLevel,
            xp,
            stats,
            spells: [...hero.spells],
            inventory: hero.inventory.map((s) => ({ ...s }))
        },
        leveledUp: levelsGained > 0,
        levelsGained
    };
}

/** Fresh level-1 HeroState from the hero.json def (new game / sim start). */
export function heroStateFromDef(def: HeroDef): HeroState {
    return {
        name: def.name,
        level: 1,
        xp: 0,
        stats: {
            maxHp: def.hp,
            hp: def.hp,
            maxMp: def.mp,
            mp: def.mp,
            atk: def.atk,
            def: def.def,
            spd: def.spd
        },
        spells: [...def.spells],
        inventory: def.inventory.map((s) => ({ ...s }))
    };
}
