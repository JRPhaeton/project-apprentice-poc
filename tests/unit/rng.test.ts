import { describe, expect, it } from 'vitest';

import { mulberry32, randInt } from '../../src/core/battle/rng';

describe('mulberry32', () => {
    it('is deterministic for a given seed', () => {
        const a = mulberry32(1234);
        const b = mulberry32(1234);
        const seqA = Array.from({ length: 20 }, () => a.next());
        const seqB = Array.from({ length: 20 }, () => b.next());
        expect(seqA).toEqual(seqB);
    });

    it('produces different sequences for different seeds', () => {
        const a = mulberry32(1);
        const b = mulberry32(2);
        const seqA = Array.from({ length: 5 }, () => a.next());
        const seqB = Array.from({ length: 5 }, () => b.next());
        expect(seqA).not.toEqual(seqB);
    });

    it('stays in [0, 1)', () => {
        const rng = mulberry32(99);
        for (let i = 0; i < 1000; i++) {
            const v = rng.next();
            expect(v).toBeGreaterThanOrEqual(0);
            expect(v).toBeLessThan(1);
        }
    });

    it('randInt covers the inclusive range', () => {
        const rng = mulberry32(7);
        const seen = new Set<number>();
        for (let i = 0; i < 500; i++) {
            const v = randInt(rng, -2, 2);
            expect(v).toBeGreaterThanOrEqual(-2);
            expect(v).toBeLessThanOrEqual(2);
            seen.add(v);
        }
        expect(seen.size).toBe(5);
    });
});
