/**
 * Animation pacing (§8 of docs/PLAN.md): battle speed toggle (1×/2×, animation
 * time only, never combat math) and the ?turbo=1 debug flag (all durations 0).
 * Every battle/text tween duration in the game routes through dur().
 */

let turbo = false;
let speed: 1 | 2 = 1;

export function setTurbo(on: boolean): void {
    turbo = on;
}

export function isTurbo(): boolean {
    return turbo;
}

/** Toggle 1× ↔ 2× battle speed. Returns the new speed. */
export function toggleSpeed(): 1 | 2 {
    speed = speed === 1 ? 2 : 1;
    return speed;
}

export function currentSpeed(): 1 | 2 {
    return speed;
}

/** Effective duration in ms for a base duration. 0 under ?turbo=1. */
export function dur(baseMs: number): number {
    return turbo ? 0 : Math.round(baseMs / speed);
}
