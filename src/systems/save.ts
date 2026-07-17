import { saveBlobSchema, type SaveBlob } from '../core/contracts/data';

/**
 * Save-blob parsing (§4 of docs/PLAN.md): discard-on-mismatch, never throw.
 * Any failure — JSON parse error, wrong/future version, corrupt shape —
 * returns null and the game starts fresh. Pure function, no Phaser, no
 * storage access; the storage wrapper (feature-detect + try/catch +
 * in-memory fallback, §11) is Engine/Systems work layered on top.
 */
export function parseSaveBlob(raw: string | null): SaveBlob | null {
    if (raw === null) {
        return null;
    }
    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch {
        return null;
    }
    const result = saveBlobSchema.safeParse(parsed);
    return result.success ? result.data : null;
}
