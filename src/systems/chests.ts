import Phaser from 'phaser';

import { registerAnims } from './anims';
import { playSfx } from './audio';
import { autosave } from './autosave';
import { addHalo } from './grade';
import type { ChestZone } from './overworld-map';
import { getRegistry, type GameRegistry } from './registry';

/**
 * M10 treasure chests (plan §2). Per-room chest presentation + open flow on
 * top of the map's ChestZones. Opened state persists as save flags keyed
 * `chest.<room>#<i>` where <i> is the chest's UNFILTERED map-order index —
 * stable across visits, room-scoped so identical indexes elsewhere never
 * collide (same scheme as the patrol-clear flags).
 *
 * Rendering: art-manifest sheet 'chest' (16×16, frame 0 closed / anim 'open'
 * ending on the open frame, which persists). Placeholder-first (§6): while
 * the sheet is missing every chest is a small gold rect — identical logic,
 * dimmed once opened. Interaction is the Overworld's sign-style press
 * (Enter/Z/A within reach), routed here via tryOpen(); pause gating lives in
 * the Overworld update loop that calls it.
 */

const CHEST_KEY = 'chest';
const DEPTH = 8; // below hero (10) and NPCs (9), above ground/shimmer
const REACH = 6; // sign-style interaction inflate (px)

/** The slice of UIOverlay the chest flow needs. */
export interface ChestUi {
    toast(text: string): void;
}

interface ChestEntry {
    zone: ChestZone;
    flagKey: string;
    opened: boolean;
    sprite: Phaser.GameObjects.Sprite | null;
    fallback: Phaser.GameObjects.Rectangle | null;
    /** M11 glint halo (additive sprite), destroyed on open. */
    halo: Phaser.GameObjects.Image | null;
}

export class Chests {
    private readonly scene: Phaser.Scene;
    private readonly reg: GameRegistry;
    private readonly ui: () => ChestUi | null;
    private readonly entries: ChestEntry[] = [];
    /** Last frame of the manifest 'open' anim — the persistent open pose. */
    private readonly openedFrame: number;

    constructor(scene: Phaser.Scene, room: string, zones: ChestZone[], ui: () => ChestUi | null) {
        this.scene = scene;
        this.reg = getRegistry(scene);
        this.ui = ui;
        const art = this.reg.get('defs').art;
        const openFrames = art[CHEST_KEY]?.anims.open?.frames;
        this.openedFrame = openFrames?.[openFrames.length - 1] ?? 1;

        const hasSheet = scene.textures.exists(CHEST_KEY);
        if (hasSheet) {
            registerAnims(scene, art, CHEST_KEY);
        }
        const flags = this.reg.get('flags');
        zones.forEach((zone, i) => {
            const flagKey = `chest.${room}#${i}`;
            const opened = !!flags[flagKey];
            const x = zone.rect.centerX;
            const y = zone.rect.centerY;
            let sprite: Phaser.GameObjects.Sprite | null = null;
            let fallback: Phaser.GameObjects.Rectangle | null = null;
            let halo: Phaser.GameObjects.Image | null = null;
            if (hasSheet) {
                sprite = scene.add
                    .sprite(x, y, CHEST_KEY, opened ? this.openedFrame : 0)
                    .setDepth(DEPTH);
                if (!opened) {
                    // M11 chest glint — additive halo, not postFX (overworld
                    // glow counts tanked fps on integrated GPUs).
                    halo = addHalo(scene, x, y, 0xffd870, 10, 0.3).setDepth(DEPTH - 1);
                }
            } else {
                // Placeholder-first: small gold box, dimmed once opened.
                fallback = scene.add
                    .rectangle(x, y, 10, 8, opened ? 0x6a5420 : 0xc09030, opened ? 0.5 : 1)
                    .setStrokeStyle(1, opened ? 0x907830 : 0xffe080)
                    .setDepth(DEPTH);
            }
            this.entries.push({ zone, flagKey, opened, sprite, fallback, halo });
        });
    }

    /**
     * Interact press at the hero's position: open the first unopened chest in
     * reach. Returns true when a chest consumed the press (open anim + sfx +
     * toast + inventory add + flag + autosave). Opened chests are inert.
     */
    tryOpen(heroX: number, heroY: number): boolean {
        for (const entry of this.entries) {
            if (entry.opened) {
                continue;
            }
            const reach = Phaser.Geom.Rectangle.Inflate(
                Phaser.Geom.Rectangle.Clone(entry.zone.rect),
                REACH,
                REACH
            );
            if (!reach.contains(heroX, heroY)) {
                continue;
            }
            this.open(entry);
            return true;
        }
        return false;
    }

    private open(entry: ChestEntry): void {
        entry.opened = true;
        entry.halo?.destroy(); // M11: the glint dies with the loot
        entry.halo = null;
        const animKey = `${CHEST_KEY}.open`;
        if (entry.sprite && this.scene.anims.exists(animKey)) {
            entry.sprite.play(animKey); // repeat 0 — the open frame persists
        } else if (entry.sprite) {
            entry.sprite.setFrame(this.openedFrame);
        } else if (entry.fallback) {
            entry.fallback.setFillStyle(0x6a5420, 0.5).setStrokeStyle(1, 0x907830);
        }
        playSfx(this.scene, 'sfx.chest');

        // Inventory add with stack merge (save schema: positive-qty stacks).
        const { itemId, qty } = entry.zone;
        const hero = this.reg.get('hero');
        const inventory = hero.inventory.map((s) => ({ ...s }));
        const stack = inventory.find((s) => s.itemId === itemId);
        if (stack) {
            stack.qty += qty;
        } else {
            inventory.push({ itemId, qty });
        }
        this.reg.set('hero', { ...hero, inventory });
        this.reg.set('flags', { ...this.reg.get('flags'), [entry.flagKey]: true });
        const name = this.reg.get('defs').items[itemId]?.name ?? itemId;
        this.ui()?.toast(`Found ${name} x${qty}!`);
        autosave(this.reg); // the opened flag survives reload immediately
    }
}
