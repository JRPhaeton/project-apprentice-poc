/**
 * Debug hooks (§4 of docs/PLAN.md), gated on import.meta.env.VITE_ENABLE_DEBUG
 * (set by `vite build --mode e2e` and the dev server; tree-shaken out of the
 * Pages deploy build). Query params:
 *   ?seed=<int>                    battle seed override
 *   ?scene=battle&enemy=<suffix>   jump straight into that battle from boot
 *                                  ('spider' → encounter 'enc-spider')
 *   ?scene=overworld&room=<id>     boot into that room at its 'spawn' object
 *                                  (normal bootstrap, fresh hero)
 *   ?turbo=1                       all battle/text tween durations 0
 */

export interface DebugOptions {
    seed: number | null;
    /** Full encounter id to jump into from boot, or null. */
    jumpEncounterId: string | null;
    /** Room id to boot the Overworld into, or null. */
    jumpRoomId: string | null;
    turbo: boolean;
}

export function readDebugOptions(): DebugOptions {
    const none: DebugOptions = { seed: null, jumpEncounterId: null, jumpRoomId: null, turbo: false };
    if (!import.meta.env.VITE_ENABLE_DEBUG) {
        return none;
    }
    let params: URLSearchParams;
    try {
        params = new URLSearchParams(window.location.search);
    } catch {
        return none;
    }

    const seedRaw = params.get('seed');
    const seedNum = seedRaw === null ? NaN : Number.parseInt(seedRaw, 10);
    const seed = Number.isFinite(seedNum) ? seedNum >>> 0 : null;

    let jumpEncounterId: string | null = null;
    const enemy = params.get('enemy');
    if (params.get('scene') === 'battle' && enemy) {
        jumpEncounterId = `enc-${enemy}`;
    }

    let jumpRoomId: string | null = null;
    const room = params.get('room');
    if (params.get('scene') === 'overworld' && room) {
        jumpRoomId = room;
    }

    return { seed, jumpEncounterId, jumpRoomId, turbo: params.get('turbo') === '1' };
}
