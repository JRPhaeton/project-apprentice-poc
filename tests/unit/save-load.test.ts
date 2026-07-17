import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { parseSaveBlob } from '../../src/systems/save';

// §10 save-load gate: committed fixtures under tests/fixtures/saves/.
// Discard-on-mismatch — parseSaveBlob returns null on ANY failure, never throws.

const fixtures = join(dirname(fileURLToPath(import.meta.url)), '../fixtures/saves');
const read = (name: string) => readFileSync(join(fixtures, name), 'utf8');

describe('parseSaveBlob', () => {
    it('round-trips a current-version blob', () => {
        const blob = parseSaveBlob(read('valid-v1.json'));
        expect(blob).not.toBeNull();
        expect(blob?.v).toBe(1);
        expect(blob?.hero.name).toBe('Aden');
        expect(blob?.room).toBe('room2-forest');
        // Re-serialize and re-parse: stable
        expect(parseSaveBlob(JSON.stringify(blob))).toEqual(blob);
    });

    it('returns null for a future-version blob (fresh game, no throw)', () => {
        expect(parseSaveBlob(read('future-version.json'))).toBeNull();
    });

    it('returns null for truncated/corrupt JSON', () => {
        expect(parseSaveBlob(read('corrupt.txt'))).toBeNull();
    });

    it('returns null for non-JSON garbage and empty input', () => {
        expect(parseSaveBlob('not json at all')).toBeNull();
        expect(parseSaveBlob('')).toBeNull();
        expect(parseSaveBlob(null)).toBeNull();
    });

    it('returns null for valid JSON of the wrong shape', () => {
        expect(parseSaveBlob('{"v":1}')).toBeNull();
        expect(parseSaveBlob('[]')).toBeNull();
        expect(parseSaveBlob('42')).toBeNull();
    });
});
