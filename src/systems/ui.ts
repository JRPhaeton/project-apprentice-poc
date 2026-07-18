import Phaser from 'phaser';

import type { ArtManifest } from '../core/contracts/data';
import artManifestJson from '../data/art-manifest.json';

/**
 * M6 UI kit: bitmap-font text + 9-slice window chrome, with graceful
 * degradation (§6 placeholder-first). The Art lane ships an 8x8 mono bitmap
 * font (white glyphs, tint for color) and a 48x48 'ui.panel' 9-slice sheet in
 * parallel — until those files land, addUiText falls back to the previous
 * monospace Text path (ONE console.warn per session) and addPanel falls back
 * to the previous stroked rectangles. All call sites accept either shape.
 */

export const FONT_KEY = 'font.main';
export const PANEL_KEY = 'ui.panel';
const FONT_PNG = 'assets/fonts/font.png';
const FONT_FNT = 'assets/fonts/font.fnt';

/** Either text object; both support the common setText/origin/depth/tint API. */
export type UiText = Phaser.GameObjects.BitmapText | Phaser.GameObjects.Text;
/** Either chrome shape; both support setVisible/setDepth/destroy. */
export type UiPanel = Phaser.GameObjects.NineSlice | Phaser.GameObjects.Rectangle;

let warnedFont = false;

/**
 * Queue the bitmap font + window-chrome sheet. Called from Boot.preload so
 * BOTH normal flow and ?scene=battle debug jumps have them; files are tiny.
 * The panel path comes from the art manifest (static import — Boot preloads
 * before the registry defs exist); a missing entry/file degrades to rects.
 */
export function queueUiAssets(load: Phaser.Loader.LoaderPlugin): void {
    const scene = load.scene;
    if (!scene.cache.bitmapFont.exists(FONT_KEY)) {
        load.bitmapFont(FONT_KEY, FONT_PNG, FONT_FNT);
    }
    const panel = (artManifestJson as ArtManifest)[PANEL_KEY];
    if (panel && !scene.textures.exists(PANEL_KEY)) {
        load.image(PANEL_KEY, panel.file);
    }
}

export function fontReady(scene: Phaser.Scene): boolean {
    return scene.cache.bitmapFont.exists(FONT_KEY);
}

/** The dialogue-box "more" marker: '▼' has no glyph in the ASCII bitmap font. */
export function moreMarkerChar(scene: Phaser.Scene): string {
    return fontReady(scene) ? 'v' : '▼';
}

export interface UiTextOpts {
    /** Glyph size in px (8x8 base font; use 16 for headers). Default 8. */
    size?: number;
    /** Color as a tint number (0xrrggbb). Default 0xe0e0e0. */
    color?: number;
    align?: 'left' | 'center' | 'right';
    wrapWidth?: number;
    lineSpacing?: number;
}

function hexColor(color: number): string {
    return `#${color.toString(16).padStart(6, '0')}`;
}

/**
 * Create a text object: BitmapText when the font loaded, else the previous
 * monospace Text (identical layout knobs). Callers chain setOrigin/setDepth/…
 */
export function addUiText(
    scene: Phaser.Scene,
    x: number,
    y: number,
    text: string,
    opts: UiTextOpts = {}
): UiText {
    const size = opts.size ?? 8;
    const color = opts.color ?? 0xe0e0e0;
    if (fontReady(scene)) {
        const t = scene.add.bitmapText(x, y, FONT_KEY, text, size);
        t.setTint(color);
        if (opts.align === 'center') {
            t.setCenterAlign();
        } else if (opts.align === 'right') {
            t.setRightAlign();
        }
        if (opts.wrapWidth !== undefined) {
            t.setMaxWidth(opts.wrapWidth);
        }
        if (opts.lineSpacing !== undefined) {
            t.setLineSpacing(opts.lineSpacing);
        }
        return t;
    }
    if (!warnedFont) {
        warnedFont = true;
        console.warn('[ui] bitmap font unavailable - falling back to monospace text');
    }
    return scene.add.text(x, y, text, {
        fontFamily: 'monospace',
        fontSize: `${size}px`,
        color: hexColor(color),
        align: opts.align ?? 'left',
        wordWrap: opts.wrapWidth !== undefined ? { width: opts.wrapWidth } : undefined,
        lineSpacing: opts.lineSpacing ?? 0
    });
}

/**
 * Window chrome: a 'ui.panel' NineSlice (16px corners) when the sheet loaded
 * and the renderer is WebGL (NineSlice is WebGL-only), else the previous
 * stroked translucent rectangle. Origin is top-left in both shapes.
 *
 * M11: every panel carries a baked-look drop shadow via postFX Shadow — the
 * one-object choice (over a separate offset rect) so the shadow shares the
 * panel's depth/visibility/destroy lifecycle for free. WebGL only; the
 * Canvas fallback rect stays shadowless (consistent with all M11 FX no-ops).
 */
export function addPanel(
    scene: Phaser.Scene,
    x: number,
    y: number,
    width: number,
    height: number
): UiPanel {
    const webgl = scene.game.renderer.type === Phaser.WEBGL;
    let panel: UiPanel;
    if (scene.textures.exists(PANEL_KEY) && webgl) {
        // Shrink the slice insets for panels thinner than two 16px corners.
        const inset = Math.min(16, Math.floor(width / 2), Math.floor(height / 2));
        panel = scene.add
            .nineslice(x, y, PANEL_KEY, 0, width, height, inset, inset, inset, inset)
            .setOrigin(0, 0);
    } else {
        panel = scene.add
            .rectangle(x, y, width, height, 0x101020, 0.92)
            .setOrigin(0, 0)
            .setStrokeStyle(1, 0x8080a0);
    }
    if (webgl) {
        // Light anchored top-left → soft dark falloff toward bottom-right.
        panel.postFX.addShadow(0, 0, 0.06, 0.4, 0x000000, 4, 1);
    }
    return panel;
}
