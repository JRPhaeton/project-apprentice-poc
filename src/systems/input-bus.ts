import Phaser from 'phaser';

/**
 * M7 input bus: a tiny per-game semantic event hub. Keyboard stays PRIMARY —
 * every scene keeps its existing key handling and only ADDS bus subscriptions
 * alongside; the touch UI (systems/touch.ts) is the main emitter and desktop
 * mouse clicks on the on-screen buttons ride the same path for free. Events:
 *   'dir'     payload DirState — virtual d-pad held-state CHANGES (touch)
 *   'confirm' A button / tap-confirm      'cancel'  B button
 *   'pause'   pause button                 'speed'   battle speed toggle
 * Beyond events, the bus carries two pieces of polled state: the held
 * direction the Overworld OR-merges with the keyboard each frame, and the
 * A-button held flag the dialogue box merges into hold-to-fast-forward.
 */

export interface DirState {
    x: -1 | 0 | 1;
    y: -1 | 0 | 1;
}

export type InputBusPress = 'confirm' | 'cancel' | 'pause' | 'speed';

export class InputBus extends Phaser.Events.EventEmitter {
    private dir: DirState = { x: 0, y: 0 };
    private confirmHeld = false;

    /** Virtual d-pad held state; emits 'dir' only when it actually changes. */
    setDir(x: DirState['x'], y: DirState['y']): void {
        if (this.dir.x === x && this.dir.y === y) {
            return;
        }
        this.dir = { x, y };
        this.emit('dir', this.dir);
    }

    getDir(): DirState {
        return this.dir;
    }

    setConfirmHeld(held: boolean): void {
        this.confirmHeld = held;
    }

    /** True while the touch A button is held (dialogue hold-to-fast-forward). */
    isConfirmHeld(): boolean {
        return this.confirmHeld;
    }

    press(event: InputBusPress): void {
        this.emit(event);
    }
}

const buses = new WeakMap<Phaser.Game, InputBus>();

/** The per-game-instance bus, created on first use. */
export function getInputBus(game: Phaser.Game): InputBus {
    let bus = buses.get(game);
    if (!bus) {
        bus = new InputBus();
        buses.set(game, bus);
    }
    return bus;
}
