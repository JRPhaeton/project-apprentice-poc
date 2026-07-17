/**
 * E2E observability hooks (§10 of docs/PLAN.md). QA's Playwright suite asserts
 * on these EXACT dataset attributes:
 *   - body[data-poc-ready="1"]    once Title is interactive
 *   - body[data-poc-scene]        active scene key on every scene switch
 *   - body[data-poc-hp]           current hero hp as string, updated on change
 *   - body[data-poc-outcome]      BattleResult outcome after each battle
 */

export type SceneHookKey = 'Title' | 'Overworld' | 'Battle' | 'GameOver' | 'Victory';

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
