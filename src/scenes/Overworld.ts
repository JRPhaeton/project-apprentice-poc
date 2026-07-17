import Phaser from 'phaser';

import { ensureTexture } from '../systems/anims';
import { autosave } from '../systems/autosave';
import { makeBattleRequest } from '../systems/battle-request';
import { markHp, markScene } from '../systems/hooks';
import { buildOverworldMap, type EncounterZone, type OverworldMapData } from '../systems/overworld-map';
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
        this.leaving = false;
        this.consumeBattleResult();

        this.mapData = buildOverworldMap(this);
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
        // visits regardless of which patrols are already cleared.
        const flags = this.reg.get('flags');
        this.zones = this.mapData.encounters
            .map((z, i) => ({ ...z, key: `cleared.${z.encounterId}#${i}` }))
            .filter((z) => !flags[z.key]);
        for (const zone of this.zones) {
            this.add
                .rectangle(zone.rect.centerX, zone.rect.centerY, 12, 12, 0xc03030, 0.9)
                .setStrokeStyle(1, 0xff8080)
                .setDepth(5);
        }

        const cam = this.cameras.main;
        cam.setBounds(0, 0, widthPx, heightPx);
        cam.startFollow(this.hero, true);

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

        const hero = this.reg.get('hero');
        markHp(hero.stats.hp); // pocHp hook, even if the HUD isn't up yet
        this.ui()?.setHeroHud(hero.stats.hp, hero.stats.maxHp, hero.stats.mp, hero.stats.maxMp);

        // Autosave on Overworld enter (§4/§8).
        autosave(this.reg);
    }

    update(): void {
        if (this.leaving || !this.hero.body) {
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
        this.checkEncounters();
        this.checkSigns(ui);
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
            this.reg.set('overworldReturn', { x: this.hero.x, y: this.hero.y });
            this.reg.set(
                'battleRequest',
                makeBattleRequest({ encounterId: zone.encounterId, source: 'overworld' })
            );
            this.cameras.main.flash(120, 255, 255, 255);
            this.scene.start('Battle');
        }
    }

    private checkSigns(ui: UIOverlay | null): void {
        const pressed =
            Phaser.Input.Keyboard.JustDown(this.keys.enter) || Phaser.Input.Keyboard.JustDown(this.keys.z);
        if (!pressed || !ui) {
            return;
        }
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
