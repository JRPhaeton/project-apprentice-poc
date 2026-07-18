import Phaser from 'phaser';

import { XP_THRESHOLDS } from '../core/battle/progression';
import type { HeroState } from '../core/contracts/data';
import { autosave } from './autosave';
import { MenuList } from './battle-menu';
import { markFieldMenu } from './hooks';
import { getInputBus, type InputBus } from './input-bus';
import { isPaused } from './pause';
import { getRegistry, type GameRegistry } from './registry';
import { addPanel, addUiText } from './ui';

/**
 * M9 field menu (FF6-style): X/Esc or the touch B button opens a modal menu
 * in the Overworld — ITEM / MAGIC / STATUS / CLOSE — reusing the battle
 * MenuList (keyboard + input-bus + tap rows + disabled-row styling). Field
 * usage applies effects DIRECTLY to the registry HeroState — the battle
 * resolver never runs here. 'heal' effects are field-usable (never at full
 * HP), and M10 'restoreMp' items likewise (never at full MP); buff items/
 * spells show greyed (battle-only). Every use refreshes the HUD, toasts the
 * restored amount, autosaves, and returns to the menu root. While open the Overworld freezes the hero and swallows
 * interacts; body dataset.pocMenu='field' is the QA observability hook (§10).
 *
 * Consume order (B/X while open backs out, never reopens): the open handlers
 * here bind at scene create, BEFORE any MenuList open() binds its cancel
 * handler, so on a press while open they run first and no-op (isOpen); the
 * press that OPENS the menu never reaches the just-bound MenuList handlers
 * because the emitter snapshots its listener list per emit.
 */

/** The slice of UIOverlay the field menu needs (mirrors BattleUi). */
export interface FieldMenuUi {
    setHeroHud(hp: number, maxHp: number, mp: number, maxMp: number): void;
    toast(text: string): void;
}

export interface FieldMenuOpts {
    /** Extra open gate beyond pause: no dialogue open, not mid-transition. */
    canOpen(): boolean;
    ui(): FieldMenuUi | null;
}

// Layout: root below the UIOverlay HUD strip (y 0..16), submenu beside it.
const ROOT_X = 4;
const ROOT_Y = 20;
const ROOT_W = 64;
const SUB_X = 72;
const SUB_W = 136;
const STATUS_W = 192;
const ROW_H = 10;
const PAD = 4;

export class FieldMenu {
    private readonly scene: Phaser.Scene;
    private readonly opts: FieldMenuOpts;
    private readonly reg: GameRegistry;
    private readonly bus: InputBus;
    private readonly root: MenuList;
    private readonly sub: MenuList;
    private active = false;
    private statusBits: Phaser.GameObjects.GameObject[] = [];
    private statusTimer: Phaser.Time.TimerEvent | null = null;

    constructor(scene: Phaser.Scene, opts: FieldMenuOpts) {
        this.scene = scene;
        this.opts = opts;
        this.reg = getRegistry(scene);
        this.bus = getInputBus(scene.game);
        this.root = new MenuList(scene, ROOT_X, ROOT_Y, ROOT_W);
        this.sub = new MenuList(scene, SUB_X, ROOT_Y, SUB_W);
        const kb = scene.input.keyboard;
        kb?.on('keydown-X', this.onOpenPress);
        kb?.on('keydown-ESC', this.onOpenPress);
        this.bus.on('cancel', this.onOpenPress);
        scene.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-X', this.onOpenPress);
            kb?.off('keydown-ESC', this.onOpenPress);
            this.bus.off('cancel', this.onOpenPress);
            this.close(); // never leak chrome or the data-poc-menu hook
        });
    }

    /** True from open until close — the Overworld's modal gate (movement,
     *  interacts, exits and encounter checks all sit behind it). */
    isOpen(): boolean {
        return this.active;
    }

    /** X/Esc/B while nothing else is modal; no-op while already open (the
     *  open MenuList's own cancel handler backs out instead). */
    private readonly onOpenPress = (): void => {
        if (this.active || isPaused() || !this.opts.canOpen()) {
            return;
        }
        this.active = true;
        markFieldMenu(true);
        this.openRoot();
    };

    private close(): void {
        this.root.close();
        this.sub.close();
        this.closeStatus();
        if (this.active) {
            this.active = false;
            markFieldMenu(false);
        }
    }

    private openRoot(): void {
        const hero = this.reg.get('hero');
        const hasItems = hero.inventory.some((s) => s.qty > 0);
        this.root.open({
            items: [
                { label: 'ITEM', value: 'item', enabled: hasItems },
                { label: 'MAGIC', value: 'magic', enabled: hero.spells.length > 0 },
                { label: 'STATUS', value: 'status', enabled: true },
                { label: 'CLOSE', value: 'close', enabled: true }
            ],
            onChoose: (value) => {
                if (value === 'item') {
                    this.openItems();
                } else if (value === 'magic') {
                    this.openMagic();
                } else if (value === 'status') {
                    this.openStatus();
                } else {
                    this.close();
                }
            },
            onCancel: () => this.close()
        });
    }

    /** Every held stack shows; heals are field-usable below max HP, restoreMp
     *  items (M10) below max MP — everything else keeps the disabled-row
     *  styling (buffs battle-only, no waste at full HP/MP). */
    private openItems(): void {
        const defs = this.reg.get('defs');
        const hero = this.reg.get('hero');
        const fullHp = hero.stats.hp >= hero.stats.maxHp;
        const fullMp = hero.stats.mp >= hero.stats.maxMp;
        this.sub.open({
            items: hero.inventory
                .filter((s) => s.qty > 0)
                .map((s) => {
                    const item = defs.items[s.itemId];
                    return {
                        label: `${item?.name ?? s.itemId} x${s.qty}`,
                        value: s.itemId,
                        enabled:
                            (item?.effect.kind === 'heal' && !fullHp) ||
                            (item?.effect.kind === 'restoreMp' && !fullMp)
                    };
                }),
            onChoose: (itemId) => this.useItem(itemId),
            onCancel: () => this.openRoot()
        });
    }

    /** Spells with MP cost, battle-style labels; field-castable only when
     *  the effect heals, the MP is there, and the HP is missing. */
    private openMagic(): void {
        const defs = this.reg.get('defs');
        const hero = this.reg.get('hero');
        const fullHp = hero.stats.hp >= hero.stats.maxHp;
        this.sub.open({
            items: hero.spells.map((spellId) => {
                const spell = defs.spells[spellId];
                return {
                    label: `${spell?.name ?? spellId} ${spell?.mpCost ?? 0}MP`,
                    value: spellId,
                    enabled:
                        spell?.effect.kind === 'heal' && hero.stats.mp >= spell.mpCost && !fullHp
                };
            }),
            onChoose: (spellId) => this.castSpell(spellId),
            onCancel: () => this.openRoot()
        });
    }

    private useItem(itemId: string): void {
        const item = this.reg.get('defs').items[itemId];
        const hero = this.reg.get('hero');
        if (item?.effect.kind !== 'heal' && item?.effect.kind !== 'restoreMp') {
            return; // disabled rows can't confirm; belt and braces
        }
        // Save schema: stack qty stays positive — drop emptied stacks.
        const inventory = hero.inventory
            .map((s) => (s.itemId === itemId ? { ...s, qty: s.qty - 1 } : { ...s }))
            .filter((s) => s.qty > 0);
        if (item.effect.kind === 'heal') {
            const healed = Math.min(item.effect.amount, hero.stats.maxHp - hero.stats.hp);
            this.commit(`+${healed} HP`, {
                ...hero,
                stats: { ...hero.stats, hp: hero.stats.hp + healed },
                inventory
            });
        } else {
            // M10 restoreMp (Mana Moss class): capped exactly like the heals.
            const restored = Math.min(item.effect.amount, hero.stats.maxMp - hero.stats.mp);
            this.commit(`+${restored} MP`, {
                ...hero,
                stats: { ...hero.stats, mp: hero.stats.mp + restored },
                inventory
            });
        }
    }

    private castSpell(spellId: string): void {
        const spell = this.reg.get('defs').spells[spellId];
        const hero = this.reg.get('hero');
        if (spell?.effect.kind !== 'heal' || hero.stats.mp < spell.mpCost) {
            return;
        }
        const healed = Math.min(spell.effect.amount, hero.stats.maxHp - hero.stats.hp);
        this.commit(`+${healed} HP`, {
            ...hero,
            stats: { ...hero.stats, hp: hero.stats.hp + healed, mp: hero.stats.mp - spell.mpCost }
        });
    }

    /** Field-use commit: registry, HUD (marks pocHp), toast, autosave, root. */
    private commit(toastText: string, next: HeroState): void {
        this.reg.set('hero', next);
        const ui = this.opts.ui();
        ui?.setHeroHud(next.stats.hp, next.stats.maxHp, next.stats.mp, next.stats.maxMp);
        ui?.toast(toastText);
        autosave(this.reg);
        this.openRoot();
    }

    /** STATUS page: name/LV, XP against the next progression threshold,
     *  HP/MP, base stats, item count. ANY key or tap returns to the root. */
    private openStatus(): void {
        const hero = this.reg.get('hero');
        const { stats } = hero;
        // XP_THRESHOLDS[level] is the cumulative total for the NEXT level
        // (index i = XP to BE at level i+1); past the cap there is none.
        const nextXp = XP_THRESHOLDS[hero.level];
        const items = hero.inventory.reduce((sum, s) => sum + s.qty, 0);
        const lines = [
            `${hero.name}  LV ${hero.level}`,
            nextXp === undefined ? `XP ${hero.xp} (MAX)` : `XP ${hero.xp}/${nextXp}`,
            `HP ${stats.hp}/${stats.maxHp}  MP ${stats.mp}/${stats.maxMp}`,
            `ATK ${stats.atk}  DEF ${stats.def}  SPD ${stats.spd}`,
            `ITEMS ${items}`
        ];
        const h = lines.length * ROW_H + PAD * 2;
        this.statusBits.push(
            addPanel(this.scene, ROOT_X, ROOT_Y, STATUS_W, h).setDepth(50).setScrollFactor(0)
        );
        lines.forEach((line, i) => {
            this.statusBits.push(
                addUiText(this.scene, ROOT_X + PAD, ROOT_Y + PAD + i * ROW_H, line)
                    .setDepth(51)
                    .setScrollFactor(0)
            );
        });
        const zone = this.scene.add
            .zone(0, 0, 256, 224)
            .setOrigin(0, 0)
            .setDepth(52)
            .setScrollFactor(0)
            .setInteractive();
        zone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_UP, this.onStatusPress);
        this.statusBits.push(zone);
        // Bind the any-KEY dismiss next tick: keydown-ENTER/Z and the generic
        // 'keydown' fire back-to-back for the SAME key event, so a same-tick
        // bind would let the press that opened the page also close it.
        this.statusTimer = this.scene.time.delayedCall(0, () => {
            this.statusTimer = null;
            this.scene.input.keyboard?.on('keydown', this.onStatusKey);
            this.bus.on('confirm', this.onStatusPress);
            this.bus.on('cancel', this.onStatusPress);
        });
    }

    private readonly onStatusKey = (event: KeyboardEvent): void => {
        // P is the pause toggle — it must not double as dismiss on unpause.
        if (event.keyCode === Phaser.Input.Keyboard.KeyCodes.P) {
            return;
        }
        this.onStatusPress();
    };

    private readonly onStatusPress = (): void => {
        if (isPaused()) {
            return;
        }
        this.closeStatus();
        this.openRoot();
    };

    private closeStatus(): void {
        this.statusTimer?.remove(false);
        this.statusTimer = null;
        this.scene.input.keyboard?.off('keydown', this.onStatusKey);
        this.bus.off('confirm', this.onStatusPress);
        this.bus.off('cancel', this.onStatusPress);
        for (const bit of this.statusBits) {
            bit.destroy();
        }
        this.statusBits = [];
    }
}
