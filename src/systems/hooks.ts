/**
 * E2E observability hooks (§10 of docs/PLAN.md). QA's Playwright suite asserts
 * on these EXACT dataset attributes:
 *   - body[data-poc-ready="1"]    once Title is interactive
 *   - body[data-poc-scene]        active scene key on every scene switch
 *   - body[data-poc-hp]           current hero hp as string, updated on change
 *   - body[data-poc-outcome]      BattleResult outcome after each battle
 *   - body[data-poc-room]         current room id, updated on every room switch
 *   - body[data-poc-music]        music key ONLY while actually audibly playing;
 *                                 absent when stopped, locked, or files missing
 *   - body[data-poc-touch]        "1" while the touch UI is active (M7)
 */

export type SceneHookKey = 'Title' | 'Intro' | 'Overworld' | 'Battle' | 'GameOver' | 'Victory';

export function markReady(): void {
    document.body.dataset.pocReady = '1';
}

export function markScene(key: SceneHookKey): void {
    document.body.dataset.pocScene = key;
}

export function markHp(hp: number): void {
    document.body.dataset.pocHp = String(hp);
}

export function markOutcome(outcome: 'victory' | 'defeat' | 'fled'): void {
    document.body.dataset.pocOutcome = outcome;
}

export function markRoom(room: string): void {
    document.body.dataset.pocRoom = room;
}

/** Set while the touch UI exists (UIOverlay up on a touch device, M7). */
export function markTouch(active: boolean): void {
    if (active) {
        document.body.dataset.pocTouch = '1';
    } else {
        delete document.body.dataset.pocTouch;
    }
}

/** Set ONLY when a track is really playing (post-unlock, load succeeded). */
export function markMusic(key: string | null): void {
    if (key) {
        document.body.dataset.pocMusic = key;
    } else {
        delete document.body.dataset.pocMusic;
    }
}
