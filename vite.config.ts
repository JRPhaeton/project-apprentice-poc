import { defineConfig } from 'vitest/config';

// Single source of truth for the GitHub Pages base path (§3, §10 of docs/PLAN.md).
// Playwright derives its URLs from this export — never hardcode the base elsewhere.
export const BASE = '/project-apprentice-poc/';

export default defineConfig({
    base: BASE,
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
});
