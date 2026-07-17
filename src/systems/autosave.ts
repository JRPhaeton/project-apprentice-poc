import { SAVE_VERSION, type SaveBlob } from '../core/contracts/data';
import type { GameRegistry } from './registry';
import { writeSave } from './storage';

/**
 * Autosave (§4/§8 of docs/PLAN.md): on Overworld enter and battle victory.
 * Snapshot comes from the registry; blob shape is the frozen save schema
 * { v: 1, hero, flags, room }.
 */
export function autosave(reg: GameRegistry): void {
    const blob: SaveBlob = {
        v: SAVE_VERSION,
        hero: reg.get('hero'),
        flags: reg.get('flags'),
        room: reg.get('room')
    };
    writeSave(blob);
}
