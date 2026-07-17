import { defineConfig } from '@playwright/test';

import { BASE } from './vite.config';

// §10 of docs/PLAN.md: E2E runs against a built `vite preview` at the
// production Pages base — never against the dev server — so absolute-path
// mistakes 404 in CI instead of shipping.
const ORIGIN = 'http://localhost:8081';

export default defineConfig({
    testDir: 'tests/e2e',
    use: {
        baseURL: ORIGIN
    },
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
