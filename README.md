# Project Apprentice (POC)

A browser-native, SNES-style turn-based RPG proof of concept, inspired by 1990s JRPGs. One stage, a handful of mobs, one boss, one hero — built to nail the feel of a single combat/exploration loop at high polish.

**Play:** https://jrphaeton.github.io/project-apprentice-poc/ *(M0 walking skeleton — gameplay lands milestone by milestone)*

## Status

| Milestone | State |
|---|---|
| M0 — Walking skeleton (repo, CI, deploy) | ✅ |
| M1 — Contracts + design lock | ⏳ |
| M2 — Vertical slice | — |
| M3 — Combat complete | — |
| M4 — Content + art/audio | — |
| M5 — Polish + release | — |

## Development

```bash
npm ci          # install (exact-pinned deps)
npm run dev     # dev server at http://localhost:8080/project-apprentice-poc/
npm test        # unit tests (vitest)
npm run build   # production build
npm run test:e2e  # Playwright smoke vs built `vite preview`
```

## Architecture

Phaser 3 + TypeScript (strict) + Vite. The combat core is pure TypeScript with seeded RNG — no Phaser imports — so every battle is replayable headless in CI. All balance and content live in `src/data/*.json` behind zod schemas.

Full design + engineering plan: [`docs/PLAN.md`](docs/PLAN.md).
