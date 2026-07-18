import { defineConfig } from 'vitest/config';
import { VitePWA } from 'vite-plugin-pwa';

// Single source of truth for the GitHub Pages base path (§3, §10 of docs/PLAN.md).
// Playwright derives its URLs from this export — never hardcode the base elsewhere.
export const BASE = '/project-apprentice-poc/';

export default defineConfig(({ mode }) => ({
    base: BASE,
    // M7 mobile publish: installable PWA. The whole game (~5 MiB incl. both
    // audio codecs) precaches for full offline play. Registration happens on
    // window load, after the title is interactive, so the §10 initial-load
    // budget measurement (stops at pocReady) is unaffected.
    plugins: [
        VitePWA({
            registerType: 'autoUpdate',
            includeAssets: ['apple-touch-icon.png', 'favicon.png'],
            manifest: {
                name: 'Trial of the Apprentice',
                short_name: 'Emberheart',
                description:
                    'SNES-style turn-based RPG. The Chimera stole the Emberheart - take the fire back.',
                display: 'fullscreen',
                orientation: 'landscape',
                background_color: '#000000',
                theme_color: '#0a0a14',
                start_url: BASE,
                scope: BASE,
                icons: [
                    { src: 'assets/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
                    { src: 'assets/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
                    {
                        src: 'assets/icons/icon-maskable-512.png',
                        sizes: '512x512',
                        type: 'image/png',
                        purpose: 'maskable'
                    }
                ]
            },
            workbox: {
                globPatterns: ['**/*.{js,css,html,png,ogg,m4a,json,fnt,webmanifest}'],
                maximumFileSizeToCacheInBytes: 3 * 1024 * 1024
            }
        })
    ],
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
