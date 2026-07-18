import Phaser from 'phaser';

import { mulberry32 } from '../core/battle/rng';
import { createBattle } from '../core/battle/factory';
import { resolveAction, type ContentDefs } from '../core/battle/resolver';
import type { Action, BattleState, Rng } from '../core/contracts/battle';
import type { BattleRequest } from '../core/contracts/registry';
import { queueSheet } from '../systems/anims';
import { BATTLE_AUDIO_KEYS, ensureAudio, playMusic, playSfx, stopMusic } from '../systems/audio';
import { autosave } from '../systems/autosave';
import { animateEvents, createEnemyViews, type BattleView } from '../systems/battle-anim';
import { MenuList } from '../systems/battle-menu';
import type { GameDefs } from '../systems/content';
import { runEnemyPhase } from '../systems/enemy-phase';
import { backdropKeyFor, playBattleEntry, playVictoryFlash } from '../systems/fx';
import { markOutcome, markScene } from '../systems/hooks';
import { getInputBus } from '../systems/input-bus';
import { dur, toggleSpeed } from '../systems/pacing';
import { isPaused, PauseController } from '../systems/pause';
import { getRegistry, type GameRegistry } from '../systems/registry';
import { addUiText } from '../systems/ui';
import type { UIOverlay } from './UIOverlay';

export class Battle extends Phaser.Scene {
    private reg!: GameRegistry;
    private defs!: GameDefs;
    private request!: BattleRequest;
    private state!: BattleState;
    private rng!: Rng;
    private resolverDefs!: ContentDefs;
    private view!: BattleView;
    private menu!: MenuList;
    private submenu!: MenuList;
    /** Enemy ids with a live tap-to-target handler (M7 touch targeting). */
    private targetTapIds: string[] = [];
    private freeActionUsed = false;
    private ended = false;
    private backdropKey = '';

    constructor() {
        super('Battle');
    }

    create(): void {
        markScene('Battle');
        this.reg = getRegistry(this);
        this.defs = this.reg.get('defs');
        this.ended = false;
        this.freeActionUsed = false;
        const request = this.reg.get('battleRequest');
        if (!request || !this.defs.encounters[request.encounterId]) {
            this.scene.start('Title');
            return;
        }
        this.request = request;
        if (!this.scene.isActive('UIOverlay')) {
            this.scene.launch('UIOverlay');
        }

        this.add.rectangle(128, 112, 256, 224, 0x0a0a14).setDepth(0);
        this.menu = new MenuList(this, 8, 108, 64);
        this.submenu = new MenuList(this, 76, 108, 116);
        const kb = this.input.keyboard;
        const bus = getInputBus(this.game);
        const onSpeed = (): void => {
            if (!isPaused()) {
                this.ui().toast(`SPEED ${toggleSpeed()}x`);
            }
        };
        kb?.on('keydown-T', onSpeed);
        bus.on('speed', onSpeed); // M7 bus event, same handler as T
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            kb?.off('keydown-T', onSpeed);
            bus.off('speed', onSpeed);
            this.targetTapIds = [];
            this.menu.destroy();
            this.submenu.destroy();
        });
        new PauseController(this); // §8: P freezes tweens/timers/physics

        // §2 lazy-load rule: battle sheets AND battle/boss music + SFX load
        // here, on first Battle entry, behind the same loading affordance.
        // M6: the biome backdrop joins the same batch — picked by the room the
        // battle started from; boss encounters always use the lair.
        const artIds = this.defs.encounters[this.request.encounterId].enemies.map(
            (defId) => this.defs.enemies[defId].artId
        );
        this.backdropKey = backdropKeyFor(
            this.reg.get('room'),
            this.defs.encounters[this.request.encounterId].boss
        );
        this.load.setBaseURL(import.meta.env.BASE_URL);
        for (const artId of artIds) {
            queueSheet(this.load, this.defs.art, artId);
        }
        queueSheet(this.load, this.defs.art, this.backdropKey);
        ensureAudio(this, BATTLE_AUDIO_KEYS);
        if (this.load.list.size > 0) {
            const loading = addUiText(this, 128, 112, 'LOADING...', { color: 0x808080 })
                .setOrigin(0.5)
                .setDepth(1);
            this.load.once(Phaser.Loader.Events.COMPLETE, () => {
                loading.destroy();
                this.begin();
            });
            this.load.start();
        } else {
            // Defer one tick so a same-step UIOverlay launch has created.
            this.time.delayedCall(0, () => this.begin());
        }
    }

    private ui(): UIOverlay {
        return this.scene.get('UIOverlay') as UIOverlay;
    }

    private begin(): void {
        // §6 routing: 'music.boss' for boss:true encounters, else 'music.battle'.
        playMusic(
            this,
            this.defs.encounters[this.request.encounterId].boss ? 'music.boss' : 'music.battle'
        );
        // M6 presentation: biome backdrop behind the enemies (missing file →
        // the dark base rect), then the shutter-bar entry transition on top.
        if (this.textures.exists(this.backdropKey)) {
            this.add.image(128, 72, this.backdropKey).setDepth(1);
        }
        playBattleEntry(this);
        const hero = this.reg.get('hero');
        this.state = createBattle(this.request.encounterId, hero, this.request.seed, {
            enemies: this.defs.enemies,
            encounters: this.defs.encounters
        });
        this.rng = mulberry32(this.request.seed);
        this.resolverDefs = { spells: this.defs.spells, items: this.defs.items };

        const enemies = createEnemyViews(this, this.state, this.defs);

        const ui = this.ui();
        ui.pinBox(true);
        this.view = { scene: this, state: this.state, defs: this.defs, enemies, ui };
        ui.setHeroHud(hero.stats.hp, hero.stats.maxHp, hero.stats.mp, hero.stats.maxMp);
        // M6 controls clarity: battle menu footer hint.
        addUiText(this, 8, 169, 'ENTER CONFIRM  X BACK', { color: 0x606080 }).setDepth(5);
        const names = [...new Set([...enemies.keys()].map((id) => this.state.combatants[id].name))];
        ui.log(`${names.join(' and ')} attacks!`);

        // First-use Defend hint, once per save (§8), flag persisted on autosave.
        const flags = this.reg.get('flags');
        if (!flags['hint.defend']) {
            this.reg.set('flags', { ...flags, 'hint.defend': true });
            void ui
                .showDialogue([
                    'HINT: DEFEND halves damage this turn and powers up your next attack.',
                    'Watch for enemy tells - defend through the big hit, then strike back.'
                ])
                .then(() => this.playerTurn());
        } else {
            this.playerTurn();
        }
    }

    /** Hero command menu. Reopening resets the cursor to ATTACK every turn. */
    private playerTurn(): void {
        if (this.ended) {
            return;
        }
        const hero = this.state.combatants[this.state.heroId];
        const heroState = this.reg.get('hero');
        const hasItems = this.state.inventory.some((s) => s.qty > 0);
        this.menu.open({
            items: [
                { label: 'ATTACK', value: 'attack', enabled: true },
                { label: 'DEFEND', value: 'defend', enabled: true },
                { label: 'MAGIC', value: 'magic', enabled: heroState.spells.length > 0 },
                { label: 'ITEM', value: 'item', enabled: hasItems },
                { label: 'RUN', value: 'run', enabled: true }
            ],
            onChoose: (value) => {
                if (value === 'attack') {
                    this.pickTarget((target) =>
                        this.commit({ type: 'attack', actor: hero.id, target })
                    );
                } else if (value === 'defend') {
                    void this.commit({ type: 'defend', actor: hero.id });
                } else if (value === 'magic') {
                    this.openMagic();
                } else if (value === 'item') {
                    this.openItems();
                } else {
                    void this.commit({ type: 'run', actor: hero.id });
                }
            }
        });
    }

    private livingEnemies(): string[] {
        return this.state.order.filter(
            (id) => this.state.combatants[id].side === 'enemy' && this.state.combatants[id].alive
        );
    }

    private pickTarget(cb: (target: string) => void): void {
        const ids = this.livingEnemies();
        if (ids.length <= 1) {
            cb(ids[0] ?? this.state.heroId);
            return;
        }
        // Every path out of targeting (submenu choose/cancel, sprite tap)
        // tears the M7 tap handlers down before continuing.
        const done = (target: string): void => {
            this.disableEnemyTaps();
            cb(target);
        };
        this.submenu.open({
            items: ids.map((id) => ({ label: this.state.combatants[id].name, value: id, enabled: true })),
            onChoose: done,
            onCancel: () => {
                this.disableEnemyTaps();
                this.playerTurn();
            }
        });
        this.enableEnemyTaps(ids, (id) => {
            this.submenu.close();
            done(id);
        });
    }

    /** M7 touch targeting: while the target submenu is open, tapping an
     *  enemy sprite selects AND confirms it (bigger target than the rows). */
    private enableEnemyTaps(ids: string[], choose: (id: string) => void): void {
        this.targetTapIds = ids;
        for (const id of ids) {
            const sprite = this.view.enemies.get(id)?.sprite;
            if (!sprite?.active) {
                continue;
            }
            sprite.setInteractive({ useHandCursor: true });
            sprite.on(Phaser.Input.Events.GAMEOBJECT_POINTER_UP, () => {
                if (isPaused() || !this.targetTapIds.includes(id)) {
                    return;
                }
                choose(id);
            });
        }
    }

    private disableEnemyTaps(): void {
        for (const id of this.targetTapIds) {
            const sprite = this.view.enemies.get(id)?.sprite;
            if (sprite?.active) {
                sprite.off(Phaser.Input.Events.GAMEOBJECT_POINTER_UP);
                sprite.disableInteractive();
            }
        }
        this.targetTapIds = [];
    }

    private openMagic(): void {
        const heroState = this.reg.get('hero');
        const mp = this.state.combatants[this.state.heroId].stats.mp;
        this.submenu.open({
            items: heroState.spells.map((spellId) => {
                const spell = this.defs.spells[spellId];
                return {
                    label: `${spell?.name ?? spellId} ${spell?.mpCost ?? 0}MP`,
                    value: spellId,
                    enabled: !!spell && mp >= spell.mpCost // grey if unaffordable
                };
            }),
            onChoose: (spellId) => {
                const spell = this.defs.spells[spellId];
                if (spell?.effect.kind === 'attack') {
                    this.pickTarget((target) =>
                        this.commit({ type: 'cast', actor: this.state.heroId, spellId, target })
                    );
                } else {
                    void this.commit({
                        type: 'cast',
                        actor: this.state.heroId,
                        spellId,
                        target: this.state.heroId
                    });
                }
            },
            onCancel: () => this.playerTurn()
        });
    }

    private openItems(): void {
        this.submenu.open({
            items: this.state.inventory
                .filter((s) => s.qty > 0)
                .map((s) => {
                    const item = this.defs.items[s.itemId];
                    const free = item?.freeAction === true;
                    return {
                        label: `${item?.name ?? s.itemId} x${s.qty}`,
                        value: s.itemId,
                        // §5.2: at most ONE free action per turn.
                        enabled: !free || !this.freeActionUsed
                    };
                }),
            onChoose: (itemId) => void this.useItem(itemId),
            onCancel: () => this.playerTurn()
        });
    }

    /** Free-action items resolve without ending the command phase (§5.2). */
    private async useItem(itemId: string): Promise<void> {
        const action: Action = {
            type: 'useItem',
            actor: this.state.heroId,
            itemId,
            target: this.state.heroId
        };
        if (this.defs.items[itemId]?.freeAction && !this.freeActionUsed) {
            this.freeActionUsed = true;
            const { events } = resolveAction(this.state, action, this.rng, this.resolverDefs);
            await animateEvents(this.view, events);
            if (!this.checkEnd()) {
                this.playerTurn();
            }
            return;
        }
        await this.commit(action);
    }

    /** The turn-consuming command: resolve → animate → enemy phase → repeat. */
    private async commit(action: Action): Promise<void> {
        // §6 SFX mapping: hero attack commit / spell cast.
        if (action.type === 'attack') {
            playSfx(this, 'sfx.attack');
        } else if (action.type === 'cast') {
            playSfx(this, 'sfx.magic');
        }
        const { events } = resolveAction(this.state, action, this.rng, this.resolverDefs);
        await animateEvents(this.view, events);
        if (this.checkEnd()) {
            return;
        }
        const enemyEvents = runEnemyPhase(this.state, this.rng, this.resolverDefs);
        await animateEvents(this.view, enemyEvents);
        if (this.checkEnd()) {
            return;
        }
        this.freeActionUsed = false;
        this.playerTurn();
    }

    private checkEnd(): boolean {
        if (this.state.outcome === 'ongoing') {
            return false;
        }
        if (!this.ended) {
            this.ended = true;
            void this.finish();
        }
        return true;
    }

    private async finish(): Promise<void> {
        const outcome = this.state.outcome as 'victory' | 'defeat' | 'fled';
        const hero = { ...this.reg.get('hero') };
        const heroCombatant = this.state.combatants[this.state.heroId];
        hero.stats = { ...hero.stats, hp: heroCombatant.stats.hp, mp: heroCombatant.stats.mp };
        hero.inventory = this.state.inventory.filter((s) => s.qty > 0).map((s) => ({ ...s }));

        if (outcome === 'victory') {
            const xp = this.defs.encounters[this.request.encounterId].enemies.reduce(
                (sum, defId) => sum + this.defs.enemies[defId].xp,
                0
            );
            hero.xp += xp;
            const stats = this.reg.get('stats');
            this.reg.set('stats', {
                battlesWon: stats.battlesWon + 1,
                xpEarned: stats.xpEarned + xp
            });
            this.reg.set('hero', hero);
            if (this.defs.encounters[this.request.encounterId].boss) {
                // Boss down: keeps room4's door inert on re-entry (persisted
                // by the autosave below, so CONTINUE stays inert too).
                this.reg.set('flags', { ...this.reg.get('flags'), 'boss.defeated': true });
            }
            stopMusic(this); // §6: music stops on win; fanfare stands alone
            playSfx(this, 'sfx.victory');
            playVictoryFlash(this); // M6: victory screen flash
            this.ui().toast(`+${xp} XP`);
            autosave(this.reg); // autosave on battle victory (§4)
            await new Promise((r) => this.time.delayedCall(Math.max(1, dur(1000)), r));
        } else {
            this.reg.set('hero', hero);
        }

        this.reg.set('battleRequest', null);
        this.reg.set('lastBattleResult', { outcome, heroSnapshot: hero });
        markOutcome(outcome);
        this.ui().pinBox(false);

        if (outcome === 'defeat') {
            this.scene.start('GameOver');
        } else if (outcome === 'victory' && this.defs.encounters[this.request.encounterId].boss) {
            this.scene.start('Victory');
        } else {
            this.scene.start('Overworld'); // victory (non-boss) or fled
        }
    }
}
