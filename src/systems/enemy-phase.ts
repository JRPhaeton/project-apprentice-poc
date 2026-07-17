/**
 * Enemy-phase entry point for the Battle scene. The implementation is the
 * Combat lane's pure driver (chooseAction + resolveAction per living enemy,
 * then endRound) — re-exported here so the Engine lane has a single stable
 * import site. (This file briefly carried a local stub before
 * core/battle/driver.ts landed; now reconciled to the real driver.)
 */
export { runEnemyPhase } from '../core/battle/driver';
