import Phaser from 'phaser';

import type { ArtManifest } from '../core/contracts/data';

/**
 * Manifest-driven sprite loading (§4 of docs/PLAN.md): texture keys ARE the
 * art-manifest logical IDs; frame sizes and anim defs come from the manifest,
 * never from code — the M4 placeholder→final swap is a pure data diff.
 * Missing files degrade to generated placeholder rectangles so the slice is
 * never blocked on art (§6).
 */

/** Queue a manifest sheet on a loader. File paths come from the manifest as-is. */
export function queueSheet(load: Phaser.Loader.LoaderPlugin, art: ArtManifest, id: string): void {
    const entry = art[id];
    if (!entry || load.scene.textures.exists(id)) {
        return;
    }
    load.spritesheet(id, entry.file, {
        frameWidth: entry.frameWidth,
        frameHeight: entry.frameHeight
    });
}

/** Register the manifest's anims for a loaded sheet. Safe to call repeatedly. */
export function registerAnims(scene: Phaser.Scene, art: ArtManifest, id: string): void {
    const entry = art[id];
    if (!entry || !scene.textures.exists(id)) {
        return;
    }
    for (const [name, anim] of Object.entries(entry.anims)) {
        const key = `${id}.${name}`;
        if (scene.anims.exists(key)) {
            continue;
        }
        scene.anims.create({
            key,
            frames: scene.anims.generateFrameNumbers(id, { frames: anim.frames }),
            frameRate: anim.frameRate,
            repeat: anim.repeat
        });
    }
}

/**
 * Ensure SOME texture exists under `id` — a flat placeholder rect when the
 * real sheet failed to load or the manifest lacks the entry.
 */
export function ensureTexture(
    scene: Phaser.Scene,
    id: string,
    width: number,
    height: number,
    color: number
): void {
    if (scene.textures.exists(id)) {
        return;
    }
    const g = scene.add.graphics();
    g.fillStyle(color, 1);
    g.fillRect(0, 0, width, height);
    g.lineStyle(1, 0xffffff, 0.6);
    g.strokeRect(0, 0, width, height);
    g.generateTexture(id, width, height);
    g.destroy();
}

/**
 * Play the first existing anim among `<artId>.<prefix><name>` candidates.
 * Returns the played key, or null when none exist (placeholder texture case).
 */
export function playFirstAnim(
    sprite: Phaser.GameObjects.Sprite,
    artId: string,
    prefix: string,
    names: string[]
): string | null {
    const anims = sprite.scene.anims;
    for (const name of names) {
        const key = `${artId}.${prefix}${name}`;
        if (anims.exists(key)) {
            sprite.play(key);
            return key;
        }
    }
    return null;
}
