// M1 FROZEN CONTRACT (§7 of docs/PLAN.md).
// zod schemas for every src/data/*.json content file plus the persisted save
// blob (§4). Validated in tests and at boot in dev builds. No Phaser imports.

import { z } from 'zod';

// ---------------------------------------------------------------------------
// Shared

export const statSchema = z.enum(['atk', 'def', 'spd']);

export const effectSchema = z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('heal'), amount: z.number().int().positive() }),
    z.object({
        kind: z.literal('buff'),
        stat: statSchema,
        pct: z.number().int(),
        turns: z.number().int().positive()
    }),
    z.object({ kind: z.literal('attack'), mult: z.number().positive() }),
    // M10 amendment (GDD row 9): MP restoration for the Mana Moss item class.
    z.object({ kind: z.literal('restoreMp'), amount: z.number().int().positive() })
]);

// ---------------------------------------------------------------------------
// enemies.json

export const aiSpecSchema = z.discriminatedUnion('kind', [
    z.object({
        kind: z.literal('telegraph'),
        tellEvery: z.number().int().positive(),
        tellDamageMult: z.number().positive()
    }),
    z.object({
        kind: z.literal('caster'),
        spellId: z.string(),
        chance: z.number().min(0).max(1)
    }),
    z.object({
        kind: z.literal('reviver'),
        reviveChance: z.number().min(0).max(1),
        reviveHp: z.number().int().positive()
    }),
    z.object({
        kind: z.literal('boss'),
        phaseAtPct: z.number().int().min(1).max(99),
        phaseAtkPct: z.number().int(),
        phaseUnlock: z.string()
    })
]);

export const enemyDefSchema = z.object({
    id: z.string(),
    name: z.string(),
    hp: z.number().int().positive(),
    atk: z.number().int().positive(),
    def: z.number().int().nonnegative(),
    spd: z.number().int().positive(),
    xp: z.number().int().nonnegative(),
    artId: z.string(),
    ai: aiSpecSchema
});

export const enemiesFileSchema = z.record(z.string(), enemyDefSchema);

// ---------------------------------------------------------------------------
// spells.json / items.json

export const spellDefSchema = z.object({
    id: z.string(),
    name: z.string(),
    mpCost: z.number().int().nonnegative(),
    effect: effectSchema
});

export const spellsFileSchema = z.record(z.string(), spellDefSchema);

export const itemDefSchema = z.object({
    id: z.string(),
    name: z.string(),
    /** §5.2: applies without consuming the hero's turn. At most one per turn. */
    freeAction: z.boolean(),
    effect: effectSchema
});

export const itemsFileSchema = z.record(z.string(), itemDefSchema);

// ---------------------------------------------------------------------------
// hero.json (hero base stats + starting loadout; balance lives in data, §5)

export const heroDefSchema = z.object({
    name: z.string(),
    hp: z.number().int().positive(),
    mp: z.number().int().nonnegative(),
    atk: z.number().int().positive(),
    def: z.number().int().nonnegative(),
    spd: z.number().int().positive(),
    spells: z.array(z.string()),
    inventory: z.array(z.object({ itemId: z.string(), qty: z.number().int().positive() }))
});

// ---------------------------------------------------------------------------
// encounters.json

export const encounterDefSchema = z.object({
    id: z.string(),
    /** defIds into enemies.json, in display order. */
    enemies: z.array(z.string()).min(1).max(3),
    boss: z.boolean()
});

export const encountersFileSchema = z.record(z.string(), encounterDefSchema);

// ---------------------------------------------------------------------------
// dialogue.json

export const dialogueEntrySchema = z.object({
    id: z.string(),
    lines: z.array(z.string()).min(1)
});

export const dialogueFileSchema = z.record(z.string(), dialogueEntrySchema);

// ---------------------------------------------------------------------------
// art-manifest.json (§4 — sheet-level logical IDs with frame metadata)

export const artAnimSchema = z.object({
    frames: z.array(z.number().int().nonnegative()).min(1),
    frameRate: z.number().positive(),
    repeat: z.number().int().min(-1)
});

export const artEntrySchema = z.object({
    file: z.string(),
    frameWidth: z.number().int().positive(),
    frameHeight: z.number().int().positive(),
    anims: z.record(z.string(), artAnimSchema)
});

export const artManifestSchema = z.record(z.string(), artEntrySchema);

// ---------------------------------------------------------------------------
// audio-manifest.json (§4/§6 — dual codec; loop points optional/reserved)

export const audioEntrySchema = z
    .object({
        ogg: z.string(),
        m4a: z.string(),
        volume: z.number().min(0).max(1),
        loopStart: z.number().nonnegative().optional(),
        loopEnd: z.number().positive().optional()
    })
    .refine(
        (e) =>
            (e.loopStart === undefined && e.loopEnd === undefined) ||
            (e.loopStart !== undefined && e.loopEnd !== undefined && e.loopStart < e.loopEnd),
        { message: 'loopStart/loopEnd must be paired with loopStart < loopEnd' }
    );

export const audioManifestSchema = z.record(z.string(), audioEntrySchema);

// ---------------------------------------------------------------------------
// Save blob (§4 — versioned from day one; discard-on-mismatch, never throw)

export const heroStateSchema = z.object({
    name: z.string(),
    level: z.number().int().positive(),
    xp: z.number().int().nonnegative(),
    stats: z.object({
        maxHp: z.number().int().positive(),
        hp: z.number().int().nonnegative(),
        maxMp: z.number().int().nonnegative(),
        mp: z.number().int().nonnegative(),
        atk: z.number().int().positive(),
        def: z.number().int().nonnegative(),
        spd: z.number().int().positive()
    }),
    spells: z.array(z.string()),
    inventory: z.array(z.object({ itemId: z.string(), qty: z.number().int().positive() }))
});

export const SAVE_VERSION = 1;

export const saveBlobSchema = z.object({
    v: z.literal(SAVE_VERSION),
    hero: heroStateSchema,
    /** Overworld position/progress flags (World lane extends via amendment). */
    flags: z.record(z.string(), z.boolean()),
    room: z.string()
});

// ---------------------------------------------------------------------------
// Inferred types

export type EnemyDef = z.infer<typeof enemyDefSchema>;
export type EnemiesFile = z.infer<typeof enemiesFileSchema>;
export type SpellDef = z.infer<typeof spellDefSchema>;
export type SpellsFile = z.infer<typeof spellsFileSchema>;
export type ItemDef = z.infer<typeof itemDefSchema>;
export type ItemsFile = z.infer<typeof itemsFileSchema>;
export type HeroDef = z.infer<typeof heroDefSchema>;
export type EncounterDef = z.infer<typeof encounterDefSchema>;
export type EncountersFile = z.infer<typeof encountersFileSchema>;
export type DialogueFile = z.infer<typeof dialogueFileSchema>;
export type ArtManifest = z.infer<typeof artManifestSchema>;
export type AudioManifest = z.infer<typeof audioManifestSchema>;
export type HeroState = z.infer<typeof heroStateSchema>;
export type SaveBlob = z.infer<typeof saveBlobSchema>;
