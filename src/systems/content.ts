import artManifestJson from '../data/art-manifest.json';
import audioManifestJson from '../data/audio-manifest.json';
import dialogueJson from '../data/dialogue.json';
import encountersJson from '../data/encounters.json';
import enemiesJson from '../data/enemies.json';
import heroJson from '../data/hero.json';
import itemsJson from '../data/items.json';
import spellsJson from '../data/spells.json';
import {
    artManifestSchema,
    audioManifestSchema,
    dialogueFileSchema,
    encountersFileSchema,
    enemiesFileSchema,
    heroDefSchema,
    itemsFileSchema,
    spellsFileSchema,
    type ArtManifest,
    type AudioManifest,
    type DialogueFile,
    type EncountersFile,
    type EnemiesFile,
    type HeroDef,
    type HeroState,
    type ItemsFile,
    type SpellsFile
} from '../core/contracts/data';

/** Every parsed content file, bundled. Parsed ONCE at boot; lives in the registry. */
export interface GameDefs {
    enemies: EnemiesFile;
    spells: SpellsFile;
    items: ItemsFile;
    hero: HeroDef;
    encounters: EncountersFile;
    dialogue: DialogueFile;
    art: ArtManifest;
    audio: AudioManifest;
}

/**
 * Static JSON imports, zod-parsed once at boot in dev builds only (§3 of
 * docs/PLAN.md); production builds trust the CI data-validation gate and cast.
 */
export function loadContent(): GameDefs {
    if (import.meta.env.DEV) {
        return {
            enemies: enemiesFileSchema.parse(enemiesJson),
            spells: spellsFileSchema.parse(spellsJson),
            items: itemsFileSchema.parse(itemsJson),
            hero: heroDefSchema.parse(heroJson),
            encounters: encountersFileSchema.parse(encountersJson),
            dialogue: dialogueFileSchema.parse(dialogueJson),
            art: artManifestSchema.parse(artManifestJson),
            audio: audioManifestSchema.parse(audioManifestJson)
        };
    }
    return {
        enemies: enemiesJson as unknown as EnemiesFile,
        spells: spellsJson as unknown as SpellsFile,
        items: itemsJson as unknown as ItemsFile,
        hero: heroJson as unknown as HeroDef,
        encounters: encountersJson as unknown as EncountersFile,
        dialogue: dialogueJson as unknown as DialogueFile,
        art: artManifestJson as unknown as ArtManifest,
        audio: audioManifestJson as unknown as AudioManifest
    };
}

/** Fresh level-1 HeroState from hero.json (new game / discarded save). */
export function freshHero(def: HeroDef): HeroState {
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
