import Phaser from 'phaser';

import { ensureTexture } from '../systems/anims';
import { playMusic } from '../systems/audio';
import { autosave } from '../systems/autosave';
import { makeBattleRequest } from '../systems/battle-request';
import { markHp, markRoom, markScene } from '../systems/hooks';
import {
    buildOverworldMap,
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
// Manifest hero sheet frame order: 0=down, 1=up, 2=left, 3=right.
const DIR_FRAME = { down: 0, up: 1, left: 2, right: 3 } as const;

export class Overworld extends Phaser.Scene {
    /** Zone key of the encounter we left for Battle (victory → cleared flag). */
    private static pendingZone: string | null = null;

    private reg!: GameRegistry;
    private room!: string;
    private hero!: Phaser.Physics.Arcade.Sprite;
    private mapData!: OverworldMapData;
    private zones: (EncounterZone & { key: string })[] = [];
    private heroHasFrames = false;
    private leaving = false;
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

        ensureTexture(this, HERO_KEY, 16, 16, 0x4060c0);
        this.heroHasFrames = this.textures.get(HERO_KEY).frameTotal > 4;

        const returnPos = this.reg.get('overworldReturn');
        const pos = returnPos ?? spawn;
        this.reg.set('overworldReturn', null);

        this.hero = this.physics.add.sprite(pos.x, pos.y, HERO_KEY, 0);
        this.hero.setDepth(10);
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
            this.add
                .rectangle(zone.rect.centerX, zone.rect.centerY, 12, 12, 0xc03030, 0.9)
                .setStrokeStyle(1, 0xff8080)
                .setDepth(5);
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
        new PauseController(this); // §8: P freezes tweens/timers/physics

        const hero = this.reg.get('hero');
        markHp(hero.stats.hp); // pocHp hook, even if the HUD isn't up yet
        this.ui()?.setHeroHud(hero.stats.hp, hero.stats.maxHp, hero.stats.mp, hero.stats.maxMp);

        // §6 audio routing: overworld theme, lazy-loaded on first need. A
        // repeated request for the playing track is a no-op (gapless across
        // room switches and battle returns).
        playMusic(this, 'music.overworld');

        // Autosave on Overworld enter (§4/§8) — persists the current room id.
        autosave(this.reg);
    }

    update(): void {
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
            Phaser.Input.Keyboard.JustDown(this.keys.enter) || Phaser.Input.Keyboard.JustDown(this.keys.z);
        if (pressed && ui) {
            if (!this.checkBossDoors(ui)) {
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

    /** 4-dir movement, no diagonals: horizontal input wins the axis. */
    private move(): void {
        const k = this.keys;
        const left = k.cursors.left.isDown || k.a.isDown;
        const right = k.cursors.right.isDown || k.d.isDown;
        const up = k.cursors.up.isDown || k.w.isDown;
        const down = k.cursors.down.isDown || k.s.isDown;

        let vx = 0;
        let vy = 0;
        let dir: keyof typeof DIR_FRAME | null = null;
        if (left !== right) {
            vx = left ? -SPEED : SPEED;
            dir = left ? 'left' : 'right';
        } else if (up !== down) {
            vy = up ? -SPEED : SPEED;
            dir = up ? 'up' : 'down';
        }
        this.hero.setVelocity(vx, vy);
        if (dir && this.heroHasFrames) {
            this.hero.setFrame(DIR_FRAME[dir]);
        }
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

    private checkSigns(ui: UIOverlay): void {
        for (const sign of this.mapData.signs) {
            const reach = Phaser.Geom.Rectangle.Inflate(Phaser.Geom.Rectangle.Clone(sign.rect), 6, 6);
            if (reach.contains(this.hero.x, this.hero.y)) {
                const entry = this.reg.get('defs').dialogue[sign.dialogueId];
                void ui.showDialogue(entry?.lines ?? ['...']);
                return;
            }
        }
    }
}
