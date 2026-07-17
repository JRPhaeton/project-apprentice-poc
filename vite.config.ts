import { defineConfig } from 'vitest/config';

// Single source of truth for the GitHub Pages base path (§3, §10 of docs/PLAN.md).
// Playwright derives its URLs from this export — never hardcode the base elsewhere.
export const BASE = '/project-apprentice-poc/';

export default defineConfig(({ mode }) => ({
    base: BASE,
    // §4/§10: `vite build --mode e2e` enables the debug hooks (?scene=,
    // ?seed=, ?turbo=1) in a production-mode artifact for Playwright. The
    // Pages deploy build (plain `vite build`) leaves the flag unset, so the
    // hooks tree-shake out. Dev server keeps them on.
    define: {
        'import.meta.env.VITE_ENABLE_DEBUG': JSON.stringify(
            mode === 'e2e' || mode === 'development' ? '1' : ''
        )
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (id.includes('node_modules/phaser')) {
                        return 'phaser';
                    }
                }
            }
        }
    },
    server: {
        port: 8080
    },
    preview: {
        port: 8081
    },
    test: {
        include: ['tests/unit/**/*.test.ts']
    }
}));
