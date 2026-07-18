import { defineConfig } from '@playwright/test';

import { BASE } from './vite.config';

// §10 of docs/PLAN.md: E2E runs against a built `vite preview` at the
// production Pages base — never against the dev server — so absolute-path
// mistakes 404 in CI instead of shipping.
const ORIGIN = 'http://localhost:8081';

export default defineConfig({
    testDir: 'tests/e2e',
    // M11: cap parallelism — the dead-reckoned walk tests are wall-clock
    // timed, and 4 parallel WebGL browsers on integrated graphics starve
    // frames enough to shorten held-key walks (flaked at 4, solid at 2 —
    // matching CI's 2-core default).
    workers: 2,
    use: {
        baseURL: ORIGIN
    },
    // §3/§10: Chromium on every merge; Firefox/WebKit weekly
    // (.github/workflows/weekly-browsers.yml).
    projects: [
        { name: 'chromium', use: { browserName: 'chromium' } },
        { name: 'firefox', use: { browserName: 'firefox' } },
        { name: 'webkit', use: { browserName: 'webkit' } }
    ],
    webServer: {
        // §10: the artifact under test is the --mode e2e build, which enables
        // the debug hooks via VITE_ENABLE_DEBUG; the Pages deploy build omits
        // the flag and tree-shakes them out.
        command: 'npm run build:e2e && npm run preview',
        url: `${ORIGIN}${BASE}`,
        reuseExistingServer: !process.env.CI,
        timeout: 120000
    }
});
