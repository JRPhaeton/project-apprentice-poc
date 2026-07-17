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
        command: 'npm run preview',
        url: `${ORIGIN}${BASE}`,
        reuseExistingServer: !process.env.CI
    }
});
