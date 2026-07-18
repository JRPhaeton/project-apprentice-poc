import Phaser from 'phaser';

import type { BattleEvent, BattleState } from '../core/contracts/battle';
import { ensureTexture, playFirstAnim, registerAnims } from './anims';
import { playSfx } from './audio';
import type { GameDefs } from './content';
import { playHitShake, playPhaseFlash, playSlash, playSparkles } from './fx';
import { dur } from './pacing';
import { addUiText } from './ui';

/**
 * Battle event animation (§4/§8 of docs/PLAN.md): the scene consumes the
 * resolver's BattleEvent list and animates it — HP bar tweens, damage popups,
 * per-event sprite anims, one log line per event. Never computes outcomes.
 * All durations route through dur() (?turbo=1 → 0; T toggles 1×/2×). M6
 * presentation: drop-shadow ellipses, hit shake, slash arcs / sparkle bursts,
 * outlined damage numbers with arc motion, phase-change screen flash.
 */

export interface EnemyView {
    id: string;
    artId: string;
    /** Anim-group prefix: '' or 'cloaked.'/'uncloaked.' for the boss. */
    prefix: string;
    sprite: Phaser.GameObjects.Sprite;
    hpBar: Phaser.GameObjects.Rectangle;
    hpBarWidth: number;
}

export interface BattleUi {
    log(line: string): void;
    setHeroHud(hp: number, maxHp: number, mp: number, maxMp: number): void;
}

export interface BattleView {
    scene: Phaser.Scene;
    state: BattleState;
    defs: GameDefs;
    enemies: Map<string, EnemyView>;
    ui: BattleUi;
}

const STAT_NAMES: Record<string, string> = { atk: 'ATTACK', def: 'DEFENSE', spd: 'SPEED' };
const BAR_W = 40;

/**
 * Battle stage layout: enemy sprites centered on the dark backdrop (hero is
 * never drawn — first-person, menu-driven), thin HP bar + name per enemy.
 * Textures fall back to placeholder rects when a sheet is missing (§6).
 */
export function createEnemyViews(
    scene: Phaser.Scene,
    state: BattleState,
    defs: GameDefs
): Map<string, EnemyView> {
    const enemies = new Map<string, EnemyView>();
    const enemyIds = state.order.filter((id) => state.combatants[id].side === 'enemy');
    enemyIds.forEach((id, i) => {
        const c = state.combatants[id];
        const artId = defs.enemies[c.defId].artId;
        const entry = defs.art[artId];
        const fw = entry?.frameWidth ?? 64;
        const fh = entry?.frameHeight ?? 64;
        ensureTexture(scene, artId, fw, fh, 0x803030);
        registerAnims(scene, defs.art, artId);
        const x = 128 + (i - (enemyIds.length - 1) / 2) * 80;
        // Drop-shadow ellipse grounds the sprite against the backdrop (M6).
        const shadowY = Math.min(76 + fh / 2 - 2, 112);
        scene.add.ellipse(x, shadowY, fw * 0.7, 10, 0x000000, 0.35).setDepth(1);
        const sprite = scene.add.sprite(x, 76, artId, 0).setDepth(2);
        // Boss sheets carry cloaked.*/uncloaked.* anim groups (§4).
        const prefix = scene.anims.exists(`${artId}.cloaked.idle`) ? 'cloaked.' : '';
        playFirstAnim(sprite, artId, prefix, ['idle']);
        scene.add.rectangle(x, 116, BAR_W, 3, 0x303040).setDepth(2);
        const hpBar = scene.add
            .rectangle(x - BAR_W / 2, 116, BAR_W, 3, 0x40c050)
            .setOrigin(0, 0.5)
            .setDepth(3);
        addUiText(scene, x, 121, c.name, { color: 0xa0a0b0 }).setOrigin(0.5, 0).setDepth(2);
        enemies.set(id, { id, artId, prefix, sprite, hpBar, hpBarWidth: BAR_W });
    });
    return enemies;
}

function wait(scene: Phaser.Scene, ms: number): Promise<void> {
    return new Promise((resolve) => scene.time.delayedCall(ms, resolve));
}

/** Outlined popup number with arc motion: rises, drifts, then falls fading. */
function popup(scene: Phaser.Scene, x: number, y: number, text: string, color: number): void {
    const shadow = addUiText(scene, 1, 1, text, { color: 0x000000 }).setOrigin(0.5);
    const main = addUiText(scene, 0, 0, text, { color }).setOrigin(0.5);
    const c = scene.add.container(x, y, [shadow, main]).setDepth(60).setScrollFactor(0);
    scene.tweens.add({
        targets: c,
        x: x + Phaser.Math.Between(-8, 8),
        duration: Math.max(1, dur(520)),
        ease: 'Sine.easeOut'
    });
    scene.tweens.add({
        targets: c,
        y: y - 16,
        duration: Math.max(1, dur(260)),
        ease: 'Quad.easeOut',
        onComplete: () => {
            scene.tweens.add({
                targets: c,
                y: y - 6,
                alpha: 0,
                duration: Math.max(1, dur(260)),
                ease: 'Quad.easeIn',
                onComplete: () => c.destroy()
            });
        }
    });
}

function refreshHud(view: BattleView): void {
    const hero = view.state.combatants[view.state.heroId];
    view.ui.setHeroHud(hero.stats.hp, hero.stats.maxHp, hero.stats.mp, hero.stats.maxMp);
}

function tweenHpBar(view: BattleView, ev: EnemyView): void {
    const c = view.state.combatants[ev.id];
    const frac = c.stats.maxHp > 0 ? c.stats.hp / c.stats.maxHp : 0;
    view.scene.tweens.add({
        targets: ev.hpBar,
        displayWidth: Math.max(0, ev.hpBarWidth * frac),
        duration: Math.max(1, dur(300))
    });
}

function name(view: BattleView, id: string): string {
    return view.state.combatants[id]?.name ?? id;
}

/** Play one event's log line + visuals; returns the pacing delay to wait. */
function playEvent(view: BattleView, e: BattleEvent): number {
    const { scene, ui } = view;
    switch (e.type) {
        case 'roundStarted':
        case 'turnStarted':
            return 0;
        case 'damage': {
            playSfx(scene, 'sfx.hit'); // §6 SFX mapping: damage event lands
            const src = view.enemies.get(e.source);
            if (src) {
                playFirstAnim(src.sprite, src.artId, src.prefix, e.kind === 'spell' ? ['breath', 'cast', 'attack', 'bite'] : ['bite', 'attack']);
            }
            const tgt = view.enemies.get(e.target);
            const hitX = tgt ? tgt.sprite.x : 128;
            const hitY = tgt ? tgt.sprite.y : 150;
            // M6 impact language: white-flash + 4px shake on every hit; slash
            // arc for physical, sparkle burst for spell damage.
            playHitShake(scene);
            if (e.kind === 'spell') {
                playSparkles(scene, hitX, hitY, 0x9fc8ff);
            } else {
                playSlash(scene, hitX, hitY);
            }
            if (tgt) {
                tweenHpBar(view, tgt);
                popup(scene, tgt.sprite.x, tgt.sprite.y - 20, `-${e.amount}`, 0xff8080);
                tgt.sprite.setTintFill(0xffffff);
                scene.time.delayedCall(Math.max(1, dur(120)), () => tgt.sprite.clearTint());
            } else {
                popup(scene, 128, 138, `-${e.amount}`, 0xff8080);
                refreshHud(view);
            }
            ui.log(`${name(view, e.source)} hits ${name(view, e.target)} for ${e.amount}!`);
            return 500;
        }
        case 'heal': {
            const tgt = view.enemies.get(e.target);
            playSparkles(scene, tgt ? tgt.sprite.x : 128, tgt ? tgt.sprite.y : 150, 0x80ff80);
            popup(scene, tgt ? tgt.sprite.x : 128, tgt ? tgt.sprite.y - 20 : 138, `+${e.amount}`, 0x80ff80);
            if (tgt) {
                tweenHpBar(view, tgt);
            } else {
                refreshHud(view);
            }
            ui.log(`${name(view, e.target)} recovers ${e.amount} HP.`);
            return 400;
        }
        case 'mpSpent':
            refreshHud(view);
            return 0;
        case 'itemUsed': {
            const item = view.defs.items[e.itemId];
            ui.log(`${name(view, e.actor)} uses ${item?.name ?? e.itemId}${e.free ? ' (free)' : ''}.`);
            return 350;
        }
        case 'buffApplied': {
            const word = e.pct >= 0 ? 'rises' : 'falls';
            const ev = view.enemies.get(e.target);
            // '+'/'-' glyphs: the ASCII bitmap font has no ▲/▼ (M6).
            popup(scene, ev ? ev.sprite.x : 128, ev ? ev.sprite.y - 20 : 138, e.pct >= 0 ? '+' : '-', e.pct >= 0 ? 0x80c0ff : 0xc080ff);
            ui.log(`${name(view, e.target)}'s ${STAT_NAMES[e.stat] ?? e.stat} ${word}!`);
            return 400;
        }
        case 'buffExpired':
            ui.log(`${name(view, e.target)}'s ${STAT_NAMES[e.stat] ?? e.stat} returns to normal.`);
            return 250;
        case 'defendStarted':
            ui.log(`${name(view, e.actor)} defends.`);
            return 300;
        case 'tellStarted': {
            const ev = view.enemies.get(e.actor);
            if (ev) {
                playFirstAnim(ev.sprite, ev.artId, ev.prefix, ['tell', 'step']);
            }
            ui.log(`${name(view, e.actor)} is preparing something...`);
            return 500;
        }
        case 'phaseChanged': {
            const ev = view.enemies.get(e.actor);
            if (ev) {
                ev.prefix = 'uncloaked.';
                playPhaseFlash(scene); // M6: screen flash sells the reveal
                scene.cameras.main.shake(Math.max(1, dur(250)), 0.01);
                playFirstAnim(ev.sprite, ev.artId, ev.prefix, ['idle']);
            }
            ui.log('The cloak falls away!');
            return 600;
        }
        case 'revived': {
            const ev = view.enemies.get(e.actor);
            if (ev) {
                ev.sprite.setAlpha(1);
                playFirstAnim(ev.sprite, ev.artId, ev.prefix, ['reassemble', 'idle']);
                tweenHpBar(view, ev);
            }
            ui.log(`${name(view, e.actor)} reassembles!`);
            return 550;
        }
        case 'runFailed':
            ui.log("Can't escape!");
            return 400;
        case 'fled':
            ui.log(`${name(view, e.actor)} flees!`);
            return 400;
        case 'defeated': {
            const ev = view.enemies.get(e.actor);
            if (ev) {
                scene.tweens.add({ targets: ev.sprite, alpha: 0, duration: Math.max(1, dur(350)) });
                tweenHpBar(view, ev);
            }
            ui.log(`${name(view, e.actor)} is defeated!`);
            return 450;
        }
        case 'battleEnded':
            return 300;
    }
}

/** Animate an event list sequentially, respecting turbo/speed pacing. */
export async function animateEvents(view: BattleView, events: BattleEvent[]): Promise<void> {
    for (const e of events) {
        const delay = playEvent(view, e);
        if (delay > 0) {
            await wait(view.scene, Math.max(1, dur(delay)));
        }
    }
    refreshHud(view);
}
