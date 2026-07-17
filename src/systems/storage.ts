import type { SaveBlob } from '../core/contracts/data';
import { parseSaveBlob } from './save';

/**
 * Storage wrapper (§4/§11 of docs/PLAN.md): feature-detect localStorage, wrap
 * ALL I/O in try/catch, fall back to in-memory storage, and expose a
 * 'saving disabled' flag the HUD shows. Never throws, never console.errors —
 * a blocked-storage boot must be silent (E2E asserts zero console errors).
 */

/** Autosave localStorage key — QA's E2E suite asserts this exact key. */
export const SAVE_KEY = 'poc-save';

let memoryBlob: string | null = null;
let storageOk: boolean | null = null;

function detectStorage(): boolean {
    if (storageOk !== null) {
        return storageOk;
    }
    try {
        const probe = '__poc-probe__';
        window.localStorage.setItem(probe, '1');
        window.localStorage.removeItem(probe);
        storageOk = true;
    } catch {
        storageOk = false;
    }
    return storageOk;
}

/** True when localStorage is unusable and saves live in memory only (HUD notice). */
export function savingDisabled(): boolean {
    return !detectStorage();
}

/** Read + parse the save. Discard-on-mismatch: any failure returns null, never throws. */
export function loadSave(): SaveBlob | null {
    let raw: string | null = memoryBlob;
    if (detectStorage()) {
        try {
            raw = window.localStorage.getItem(SAVE_KEY);
        } catch {
            raw = memoryBlob;
        }
    }
    return parseSaveBlob(raw);
}

/** Write the save. Falls back to memory (and flips the disabled flag) on failure. */
export function writeSave(blob: SaveBlob): void {
    let raw: string;
    try {
        raw = JSON.stringify(blob);
    } catch {
        return;
    }
    memoryBlob = raw;
    if (!detectStorage()) {
        return;
    }
    try {
        window.localStorage.setItem(SAVE_KEY, raw);
    } catch {
        // Quota / blocked mid-session: degrade to memory-only.
        storageOk = false;
    }
}

export function clearSave(): void {
    memoryBlob = null;
    if (!detectStorage()) {
        return;
    }
    try {
        window.localStorage.removeItem(SAVE_KEY);
    } catch {
        storageOk = false;
    }
}
