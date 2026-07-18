import Phaser from 'phaser';

import { addAmbient } from '../systems/ambient';
import { ensureTexture, registerAnims } from '../systems/anims';
import { ensureAudio, playMusic } from '../systems/audio';
import { autosave } from '../systems/autosave';
import { makeBattleRequest } from '../systems/battle-request';
import { Chests } from '../systems/chests';
import { FieldMenu } from '../systems/field-menu';
import { markHp, markRoom, markScene } from '../systems/hooks';
import { getInputBus, type InputBus } from '../systems/input-bus';
import {
    buildOverworldMap,
    OVERHEAD_LAYER,
    shimmerAnimFor,
    TILE_SIZE,
    type BossDoorZone,
    type EncounterZone,
    type ExitZone,
    type OverworldMapData
} from '../systems/overworld-map';
import { dur } from '../systems/pacing';
import { isPaused, PauseController } from '../systems/pause';
import { getRegistry, type GameRegistry } from '../systems/registry';
import type { UIOverlay } from './UIOverlay';

const SPEED = 80; // px/s (§ integration contract)
const HERO_KEY = 'hero.overworld';
// Legacy 4-frame hero sheet order: 0=down, 1=up, 2=left, 3=right. The M6
// 8-frame walk sheet's facing frames come from the manifest anims instead.
const DIR_FRAME = { down: 0, up: 1, left: 2, right: 3 } as const;
type Facing = keyof typeof DIR_FRAME;

// M6/M8 tile shimmer: cells resolve via shimmerAnimFor (tile `anim`
// property in tileset v2, legacy index fallback for v1 maps).
const SHIMMER_KEY = 'tile.anim';
const SHIMMER_CAP = 150; // overlays per room

// M8: overworld patrol minis + blob shadow (frame 6 of this sheet).
const MINIS_KEY = 'enemy.minis';
const MINI_BY_ENEMY: Record<string, string> = {
    spider: 'spider',
    wisp: 'wisp',
    revenant: 'revenant'
};

// M8 room mood tints (vale-growing-cold canon) — tile layers + shimmer only.
const ROOM_TINT: Record<string, number> = {
    'room1-gate': 0xfff0e0,
    'room3-marsh': 0xd8e8f0,
    'room4-ruin': 0xc8d0e8
};

export class Overworld extends Phaser.Scene {
    /** Zone key of the encounter we left for Battle (victory → cleared flag). */
    private static pendingZone: string | null = null;

    private reg!: GameRegistry;
    private room!: string;
    private hero!: Phaser.Physics.Arcade.Sprite;
    private mapData!: OverworldMapData;
    private zones: (EncounterZone & { key: string })[] = [];
    private heroHasFrames = false;
    private facing: Facing = 'down';
    private leaving = false;
    private bus!: InputBus;
    private busInteract = false;
    private fieldMenu!: FieldMenu;
    private chests!: Chests;
    private keys!: {
        cursors: Phaser.Types.Input.Keyboard.CursorKeys;
        w: Phaser.Input.Keyboard.Key;
        a: Phaser.Input.Keyboard.Key;
        s: Phaser.Input.Keyboard.Key;
        d: Phaser.Input.Keyboard.Key;
        enter: Phaser.Input.Keyboard.Key;
        z: Phaser.Input.Keyboard.Key;
    };

    constructor() {
        super('Overworld');
    }

    create(): void {
        markScene('Overworld');
        this.reg = getRegistry(this);
        this.room = this.reg.get('room');
        markRoom(this.room); // data-poc-room, updated on every room entry (§10)
        this.leaving = false;
        this.consumeBattleResult();

        this.mapData = buildOverworldMap(this, this.room);
        const { widthPx, heightPx, spawn } = this.mapData;
        // M8 room mood tint — tile layers only; hero/minis/UI stay untinted.
        const tint = ROOM_TINT[this.room];
        if (tint !== undefined) {
            for (const layer of this.mapData.tileLayers) {
                layer.setTint(tint);
            }
        }
        this.addTileShimmer(); // M6: animated water/marsh/ember overlays
        addAmbient(this, this.room, widthPx, heightPx); // M10 atmosphere pass
        // M10 chests + NPCs (map objects land from the Assets lane; both
        // arrays are simply empty until then).
        this.chests = new Chests(this, this.room, this.mapData.chests, () => this.ui());
        this.addNpcs();

        ensureTexture(this, HERO_KEY, 16, 16, 0x4060c0);
        this.heroHasFrames = this.textures.get(HERO_KEY).frameTotal > 4;
        this.facing = 'down';

        const returnPos = this.reg.get('overworldReturn');
        const pos = returnPos ?? spawn;
        this.reg.set('overworldReturn', null);

        this.hero = this.physics.add.sprite(pos.x, pos.y, HERO_KEY, 0);
        this.hero.setDepth(10);
        // M8 tall hero (16×24): keep hero.x/y — and therefore every zone,
        // exit and door check — at the SAME world position as the legacy
        // 16×16 sprite by pinning a 16×14 FEET box. Body edges: left/right/
        // bottom identical to v1; only the box top drops 2px (head-room
        // under overhangs). Legacy sheets keep the full-frame default body.
        const frameH = this.hero.frame.height;
        if (frameH > 16) {
            this.hero.setOrigin(0.5, (frameH - 8) / frameH);
            this.hero.body!.setSize(16, 14, false);
            this.hero.body!.setOffset(0, frameH - 14);
        }
        // Blob shadow under the hero's feet (enemy.minis frame 6).
        if (this.textures.exists(MINIS_KEY)) {
            const shadow = this.add.image(pos.x, pos.y + 6, MINIS_KEY, 6).setAlpha(0.4).setDepth(9);
            this.events.on(Phaser.Scenes.Events.UPDATE, () => {
                shadow.setPosition(this.hero.x, this.hero.y + 6);
            });
        }
        this.physics.world.setBounds(0, 0, widthPx, heightPx);
        this.hero.setCollideWorldBounds(true);
        for (const layer of this.mapData.collisionLayers) {
            this.physics.add.collider(this.hero, layer);
        }

        // Telegraphed encounters (§8): visible marker per active patrol zone.
        // Keys derive from the UNFILTERED map order so they stay stable across
        // visits regardless of which patrols are already cleared; the room id
        // scopes them so identical indexes in other rooms never collide.
        const flags = this.reg.get('flags');
        this.zones = this.mapData.encounters
            .map((z, i) => ({ ...z, key: `cleared.${this.room}.${z.encounterId}#${i}` }))
            .filter((z) => !flags[z.key]);
        for (const zone of this.zones) {
            this.addPatrolMarker(zone.rect.centerX, zone.rect.centerY, zone.encounterId);
        }

        // Boss door marker (inert once the boss falls — flag 'boss.defeated').
        if (!flags['boss.defeated']) {
            for (const door of this.mapData.bossDoors) {
                this.add
                    .rectangle(door.rect.centerX, door.rect.centerY, door.rect.width, door.rect.height, 0x503080, 0.35)
                    .setStrokeStyle(1, 0x9060c0)
                    .setDepth(5);
            }
        }

        const cam = this.cameras.main;
        cam.setBounds(0, 0, widthPx, heightPx);
        cam.startFollow(this.hero, true);
        cam.fadeIn(Math.max(1, dur(150)), 0, 0, 0);

        const kb = this.input.keyboard!;
        this.keys = {
            cursors: kb.createCursorKeys(),
            w: kb.addKey(Phaser.Input.Keyboard.KeyCodes.W, false),
            a: kb.addKey(Phaser.Input.Keyboard.KeyCodes.A, false),
            s: kb.addKey(Phaser.Input.Keyboard.KeyCodes.S, false),
            d: kb.addKey(Phaser.Input.Keyboard.KeyCodes.D, false),
            enter: kb.addKey(Phaser.Input.Keyboard.KeyCodes.ENTER, false),
            z: kb.addKey(Phaser.Input.Keyboard.KeyCodes.Z, false)
        };
        // M7 input bus: 'confirm' (touch A) = interact, exactly like Enter/Z;
        // movement OR-merges the bus's held virtual d-pad in move(). The
        // scene restarts on every room switch, so unhook on SHUTDOWN.
        this.bus = getInputBus(this.game);
        this.busInteract = false;
        const onBusConfirm = (): void => {
            this.busInteract = true;
        };
        this.bus.on('confirm', onBusConfirm);
        this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            this.bus.off('confirm', onBusConfirm);
        });
        new PauseController(this); // §8: P freezes tweens/timers/physics
        // M9 field menu: X/Esc/B opens it while nothing else is modal. Its
        // key/bus handlers self-unbind on SHUTDOWN (PauseController-style).
        this.fieldMenu = new FieldMenu(this, {
            canOpen: () => !this.leaving && !this.ui()?.dialogueOpen,
            ui: () => this.ui()
        });

        const hero = this.reg.get('hero');
        markHp(hero.stats.hp); // pocHp hook, even if the HUD isn't up yet
        this.ui()?.setHeroHud(hero.stats.hp, hero.stats.maxHp, hero.stats.mp, hero.stats.maxMp);

        // §6 audio routing: overworld theme, lazy-loaded on first need. A
        // repeated request for the playing track is a no-op (gapless across
        // room switches and battle returns). M10: the chest sfx rides the
        // same lazy loader so the first open isn't silent (missing manifest
        // entry/file degrades to silence as usual).
        ensureAudio(this, ['sfx.chest']);
        playMusic(this, 'music.overworld');
        this.load.start(); // no-op when playMusic already started it

        // M6 first-Overworld move hint, once per save ('hint.move' flag —
        // persisted by the autosave right below, like 'hint.defend').
        const hintFlags = this.reg.get('flags');
        if (!hintFlags['hint.move']) {
            this.reg.set('flags', { ...hintFlags, 'hint.move': true });
            // Next tick: the parallel UIOverlay may not have created yet.
            // Device-aware hint: the menu key differs on touch (B) vs keys (X).
            const menuHint = this.sys.game.device.input.touch ? 'B OPENS MENU' : 'X OPENS MENU';
            this.time.delayedCall(0, () =>
                this.ui()?.toast(`ARROWS TO MOVE\nENTER READS - ${menuHint}`)
            );
        }

        // Autosave on Overworld enter (§4/§8) — persists the current room id.
        autosave(this.reg);
    }

    /**
     * M6 tile shimmer: overlay a playing 'tile.anim' sprite on every water /
     * marsh-water / ember tile (indices 3/9/15), capped per room. Pure
     * presentation — NO map data or collision changes; missing sheet → no-op.
     */
    /**
     * M8: telegraphed patrols render as mini creature sprites (+ shadow)
     * from enemy.minis, picked by the encounter's first enemy. Falls back to
     * the pre-M8 red rect when the sheet is missing (placeholder-first).
     */
    private addPatrolMarker(x: number, y: number, encounterId: string): void {
        const encounters = this.reg.get('defs').encounters;
        const firstEnemy = encounters[encounterId]?.enemies[0] ?? '';
        const animName = MINI_BY_ENEMY[firstEnemy];
        const animKey = `${MINIS_KEY}.${animName}`;
        if (animName && this.textures.exists(MINIS_KEY) && this.anims.exists(animKey)) {
            this.add.image(x, y + 5, MINIS_KEY, 6).setAlpha(0.35).setDepth(8);
            this.add.sprite(x, y, MINIS_KEY).setDepth(9).play(animKey);
            return;
        }
        this.add
            .rectangle(x, y, 12, 12, 0xc03030, 0.9)
            .setStrokeStyle(1, 0xff8080)
            .setDepth(5);
    }

    /**
     * M10 NPCs: static sprite per NpcZone at the rect's bottom-center (feet
     * on the rect bottom), idle anim from the manifest, blob shadow when the
     * minis sheet is present. Non-colliding; interaction is the sign flow
     * (checkSigns iterates signs + npcs). Missing sheet → placeholder rect
     * texture via ensureTexture (§6), same as the hero.
     */
    private addNpcs(): void {
        const art = this.reg.get('defs').art;
        for (const npc of this.mapData.npcs) {
            const x = npc.rect.centerX;
            const y = npc.rect.bottom;
            if (this.textures.exists(MINIS_KEY)) {
                this.add.image(x, y - 2, MINIS_KEY, 6).setAlpha(0.4).setDepth(8);
            }
            const entry = art[npc.spriteId];
            ensureTexture(
                this,
                npc.spriteId,
                entry?.frameWidth ?? 16,
                entry?.frameHeight ?? 24,
                0x9a7a4a
            );
            registerAnims(this, art, npc.spriteId);
            const sprite = this.add
                .sprite(x, y, npc.spriteId, 0)
                .setOrigin(0.5, 1)
                .setDepth(9);
            const idleKey = `${npc.spriteId}.idle`;
            if (this.anims.exists(idleKey)) {
                sprite.play(idleKey);
            }
        }
    }

    private addTileShimmer(): void {
        if (!this.textures.exists(SHIMMER_KEY)) {
            return;
        }
        let count = 0;
        for (const layer of this.mapData.tileLayers) {
            if (layer.layer.name === OVERHEAD_LAYER) {
                continue; // canopies/caps never shimmer
            }
            for (const row of layer.layer.data) {
                for (const tile of row) {
                    const animName = shimmerAnimFor(tile);
                    if (!animName) {
                        continue;
                    }
                    const animKey = `${SHIMMER_KEY}.${animName}`;
                    if (!this.anims.exists(animKey)) {
                        continue;
                    }
                    const overlay = this.add
                        .sprite(tile.pixelX + TILE_SIZE / 2, tile.pixelY + TILE_SIZE / 2, SHIMMER_KEY)
                        .setDepth(1);
                    const roomTint = ROOM_TINT[this.room];
                    if (roomTint !== undefined) {
                        overlay.setTint(roomTint);
                    }
                    overlay.play(animKey);
                    count += 1;
                    if (count >= SHIMMER_CAP) {
                        return;
                    }
                }
            }
        }
    }

    update(): void {
        const busPressed = this.busInteract; // consume even on early return
        this.busInteract = false;
        if (isPaused() || this.leaving || !this.hero.body) {
            return;
        }
        const ui = this.ui();
        if (ui?.dialogueOpen) {
            // Drain interact presses so closing a dialogue can't re-open it.
            Phaser.Input.Keyboard.JustDown(this.keys.enter);
            Phaser.Input.Keyboard.JustDown(this.keys.z);
            this.hero.setVelocity(0, 0);
            return;
        }
        if (this.fieldMenu.isOpen()) {
            // M9 field menu modal: hero frozen; drain interact presses so
            // menu confirms can't fire a sign/door read on the same key.
            Phaser.Input.Keyboard.JustDown(this.keys.enter);
            Phaser.Input.Keyboard.JustDown(this.keys.z);
            this.hero.setVelocity(0, 0);
            return;
        }
        this.move();
        this.checkExits();
        if (this.leaving) {
            return;
        }
        this.checkEncounters();
        if (this.leaving) {
            return;
        }
        const pressed =
            busPressed ||
            Phaser.Input.Keyboard.JustDown(this.keys.enter) || Phaser.Input.Keyboard.JustDown(this.keys.z);
        if (pressed && ui) {
            // Interact priority: boss door → chest → sign/NPC (M10).
            if (!this.checkBossDoors(ui) && !this.chests.tryOpen(this.hero.x, this.hero.y)) {
                this.checkSigns(ui);
            }
        }
    }

    private ui(): UIOverlay | null {
        return this.scene.isActive('UIOverlay') ? (this.scene.get('UIOverlay') as UIOverlay) : null;
    }

    /** Victory on return: mark the fought patrol cleared, once. */
    private consumeBattleResult(): void {
        const zoneKey = Overworld.pendingZone;
        Overworld.pendingZone = null;
        if (!zoneKey) {
            return;
        }
        if (this.reg.get('lastBattleResult')?.outcome === 'victory') {
            this.reg.set('flags', { ...this.reg.get('flags'), [zoneKey]: true });
        }
    }

    /** 4-dir movement, no diagonals: horizontal input wins the axis. The
     *  touch d-pad's held state OR-merges with the keyboard each frame (M7). */
    private move(): void {
        const k = this.keys;
        const bd = this.bus.getDir();
        const left = k.cursors.left.isDown || k.a.isDown || bd.x < 0;
        const right = k.cursors.right.isDown || k.d.isDown || bd.x > 0;
        const up = k.cursors.up.isDown || k.w.isDown || bd.y < 0;
        const down = k.cursors.down.isDown || k.s.isDown || bd.y > 0;

        let vx = 0;
        let vy = 0;
        let dir: Facing | null = null;
        if (left !== right) {
            vx = left ? -SPEED : SPEED;
            dir = left ? 'left' : 'right';
        } else if (up !== down) {
            vy = up ? -SPEED : SPEED;
            dir = up ? 'up' : 'down';
        }
        this.hero.setVelocity(vx, vy);
        if (!this.heroHasFrames) {
            return; // placeholder texture — nothing to animate
        }
        // M6 walk cycle: play the manifest anim while moving; when idle, stop
        // on the FIRST frame of the current facing (manifest-driven — the
        // 8-frame walk sheet and the legacy 4-frame sheet both work).
        if (dir) {
            this.facing = dir;
            const animKey = `${HERO_KEY}.${dir}`;
            if (this.anims.exists(animKey)) {
                this.hero.anims.play(animKey, true);
            } else {
                this.hero.setFrame(DIR_FRAME[dir]);
            }
        } else if (this.hero.anims.isPlaying) {
            this.hero.anims.stop();
            this.hero.setFrame(this.idleFrame());
        }
    }

    /** First frame of the facing's manifest anim (legacy fallback: 0..3). */
    private idleFrame(): number {
        const anims = this.reg.get('defs').art[HERO_KEY]?.anims;
        return anims?.[this.facing]?.frames[0] ?? DIR_FRAME[this.facing];
    }

    /** Room exits (lane convention): overlap → fade → arrive at target tile. */
    private checkExits(): void {
        for (const exit of this.mapData.exits) {
            const inside = exit.rect.contains(this.hero.x, this.hero.y);
            if (!inside) {
                exit.armed = true;
                continue;
            }
            if (!exit.armed) {
                continue;
            }
            this.switchRoom(exit);
            return;
        }
    }

    private switchRoom(exit: ExitZone): void {
        this.leaving = true;
        this.hero.setVelocity(0, 0);
        this.reg.set('room', exit.targetRoom);
        // targetX/targetY are TILE coords — arrive centered on that tile.
        this.reg.set('overworldReturn', {
            x: exit.targetX * TILE_SIZE + TILE_SIZE / 2,
            y: exit.targetY * TILE_SIZE + TILE_SIZE / 2
        });
        const cam = this.cameras.main;
        cam.fadeOut(Math.max(1, dur(150)), 0, 0, 0);
        cam.once(Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE, () => {
            // create() re-runs for the new room: marks data-poc-room and
            // autosaves with the new room id.
            this.scene.restart();
        });
    }

    /** Fire on the not-inside → inside transition (re-arm prevents fled-loops). */
    private checkEncounters(): void {
        for (const zone of this.zones) {
            if (this.leaving) {
                return;
            }
            const inside = zone.rect.contains(this.hero.x, this.hero.y);
            if (!inside) {
                zone.armed = true;
                continue;
            }
            if (!zone.armed) {
                continue;
            }
            this.leaving = true;
            this.hero.setVelocity(0, 0);
            Overworld.pendingZone = zone.key;
            this.startBattle(zone.encounterId);
        }
    }

    /**
     * Boss door (lane convention): overlap + interact → dialogue → on dismiss
     * the boss battle starts via the shared makeBattleRequest factory. After
     * a boss victory the 'boss.defeated' flag keeps the door inert.
     */
    private checkBossDoors(ui: UIOverlay): boolean {
        if (this.reg.get('flags')['boss.defeated']) {
            return false;
        }
        for (const door of this.mapData.bossDoors) {
            // 12px reach: the hero's 16px body against a wall-mounted door tile
            // puts the sprite center a full body-half (8px) + wall clearance
            // away — 6px left the door geometrically untriggerable (M4 QA).
            const reach = Phaser.Geom.Rectangle.Inflate(Phaser.Geom.Rectangle.Clone(door.rect), 12, 12);
            if (!reach.contains(this.hero.x, this.hero.y)) {
                continue;
            }
            this.leaving = true;
            this.hero.setVelocity(0, 0);
            const entry = this.reg.get('defs').dialogue[door.dialogueId];
            void ui.showDialogue(entry?.lines ?? ['...']).then(() => this.enterBossBattle(door));
            return true;
        }
        return false;
    }

    private enterBossBattle(door: BossDoorZone): void {
        if (!this.scene.isActive()) {
            return; // scene was torn down while the dialogue was open
        }
        this.startBattle(door.encounterId);
    }

    private startBattle(encounterId: string): void {
        this.reg.set('overworldReturn', { x: this.hero.x, y: this.hero.y });
        this.reg.set('battleRequest', makeBattleRequest({ encounterId, source: 'overworld' }));
        this.cameras.main.flash(120, 255, 255, 255);
        this.scene.start('Battle');
    }

    /** Signs AND NPCs (M10): both are dialogueId + rect, same reach + flow. */
    private checkSigns(ui: UIOverlay): void {
        for (const sign of [...this.mapData.signs, ...this.mapData.npcs]) {
            const reach = Phaser.Geom.Rectangle.Inflate(Phaser.Geom.Rectangle.Clone(sign.rect), 6, 6);
            if (reach.contains(this.hero.x, this.hero.y)) {
                const entry = this.reg.get('defs').dialogue[sign.dialogueId];
                void ui.showDialogue(entry?.lines ?? ['...']);
                return;
            }
        }
    }
}
