import { describe, expect, it } from 'vitest';

import {
    artManifestSchema,
    audioManifestSchema,
    dialogueFileSchema,
    encountersFileSchema,
    enemiesFileSchema,
    heroDefSchema,
    itemsFileSchema,
    spellsFileSchema
} from '../../src/core/contracts/data';
import artManifest from '../../src/data/art-manifest.json';
import audioManifest from '../../src/data/audio-manifest.json';
import dialogue from '../../src/data/dialogue.json';
import encounters from '../../src/data/encounters.json';
import enemies from '../../src/data/enemies.json';
import heroDef from '../../src/data/hero.json';
import items from '../../src/data/items.json';
import spells from '../../src/data/spells.json';

// §10 data-validation gate: every live content file parses against its
// schema, and a committed malformed fixture per schema is rejected.

describe('live src/data files pass their schemas', () => {
    it('enemies.json', () => expect(enemiesFileSchema.safeParse(enemies).success).toBe(true));
    it('spells.json', () => expect(spellsFileSchema.safeParse(spells).success).toBe(true));
    it('items.json', () => expect(itemsFileSchema.safeParse(items).success).toBe(true));
    it('hero.json', () => expect(heroDefSchema.safeParse(heroDef).success).toBe(true));
    it('encounters.json', () => expect(encountersFileSchema.safeParse(encounters).success).toBe(true));
    it('dialogue.json', () => expect(dialogueFileSchema.safeParse(dialogue).success).toBe(true));
    it('art-manifest.json', () => expect(artManifestSchema.safeParse(artManifest).success).toBe(true));
    it('audio-manifest.json', () =>
        expect(audioManifestSchema.safeParse(audioManifest).success).toBe(true));
});

describe('malformed fixtures are rejected', () => {
    it('enemy with an unknown ai kind', () => {
        const bad = {
            spider: {
                id: 'spider',
                name: 'X',
                hp: 10,
                atk: 1,
                def: 1,
                spd: 1,
                xp: 0,
                artId: 'a',
                ai: { kind: 'berserker' }
            }
        };
        expect(enemiesFileSchema.safeParse(bad).success).toBe(false);
    });

    it('spell with negative mp cost', () => {
        const bad = { heal: { id: 'heal', name: 'Heal', mpCost: -1, effect: { kind: 'heal', amount: 5 } } };
        expect(spellsFileSchema.safeParse(bad).success).toBe(false);
    });

    it('item missing freeAction', () => {
        const bad = { herb: { id: 'herb', name: 'Herb', effect: { kind: 'heal', amount: 5 } } };
        expect(itemsFileSchema.safeParse(bad).success).toBe(false);
    });

    it('hero with zero hp', () => {
        const bad = { ...heroDef, hp: 0 };
        expect(heroDefSchema.safeParse(bad).success).toBe(false);
    });

    it('encounter with four enemies', () => {
        const bad = { e: { id: 'e', enemies: ['a', 'b', 'c', 'd'], boss: false } };
        expect(encountersFileSchema.safeParse(bad).success).toBe(false);
    });

    it('dialogue entry with no lines', () => {
        const bad = { d: { id: 'd', lines: [] } };
        expect(dialogueFileSchema.safeParse(bad).success).toBe(false);
    });

    it('art entry with an empty frame list', () => {
        const bad = {
            'enemy.x': {
                file: 'x.png',
                frameWidth: 64,
                frameHeight: 64,
                anims: { idle: { frames: [], frameRate: 4, repeat: -1 } }
            }
        };
        expect(artManifestSchema.safeParse(bad).success).toBe(false);
    });

    it('audio entry with loopStart after loopEnd', () => {
        const bad = {
            'music.x': { ogg: 'x.ogg', m4a: 'x.m4a', volume: 1, loopStart: 10, loopEnd: 5 }
        };
        expect(audioManifestSchema.safeParse(bad).success).toBe(false);
    });
});

describe('referential integrity across data files', () => {
    it('every encounter enemy resolves in enemies.json', () => {
        for (const enc of Object.values(encounters)) {
            for (const defId of enc.enemies) {
                expect(enemies, `encounter ${enc.id} → ${defId}`).toHaveProperty(defId);
            }
        }
    });

    it('every enemy artId resolves in art-manifest.json', () => {
        for (const enemy of Object.values(enemies)) {
            expect(artManifest, `${enemy.id} → ${enemy.artId}`).toHaveProperty(enemy.artId);
        }
    });

    it('caster spellIds and boss phaseUnlock resolve in spells.json', () => {
        for (const enemy of Object.values(enemiesFileSchema.parse(enemies))) {
            const ai = enemy.ai;
            if (ai.kind === 'caster') {
                expect(spells).toHaveProperty(ai.spellId);
            }
            if (ai.kind === 'boss') {
                expect(spells).toHaveProperty(ai.phaseUnlock);
            }
        }
    });

    it('hero spells and inventory resolve', () => {
        for (const spellId of heroDef.spells) {
            expect(spells).toHaveProperty(spellId);
        }
        for (const stack of heroDef.inventory) {
            expect(items).toHaveProperty(stack.itemId);
        }
    });
});
