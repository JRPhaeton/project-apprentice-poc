import { expect, test } from '@playwright/test';

import { BASE } from '../../vite.config';

// M7 PWA coverage (§10): the installable-app surface vite-plugin-pwa emits
// into dist — manifest + icons, the generated service worker, the iOS
// home-screen icon — and a live in-page registration check. vite preview
// serves the production-shaped build at the Pages base, so every URL here is
// exactly what the deployed origin serves.

// §10 hard cap: every E2E test ≤ 45 s.
test.describe.configure({ timeout: 45_000 });

interface ManifestIcon {
    src: string;
    sizes: string;
    type: string;
    purpose?: string;
}

interface WebManifest {
    name: string;
    icons: ManifestIcon[];
    start_url: string;
    scope: string;
}

// (a) manifest.webmanifest: 200, correct identity, and every icon URL in it
// resolves (src paths are relative to the manifest URL at the Pages base).
test('manifest.webmanifest serves with the app identity and resolvable icons', async ({
    request,
    baseURL
}) => {
    const response = await request.get(`${BASE}manifest.webmanifest`);
    expect(response.status()).toBe(200);

    const manifest = JSON.parse(await response.text()) as WebManifest;
    expect(manifest.name).toBe('Trial of the Apprentice');
    expect(manifest.start_url).toBe(BASE);
    expect(manifest.scope).toBe(BASE);
    expect(Array.isArray(manifest.icons)).toBe(true);
    expect(manifest.icons.length).toBeGreaterThanOrEqual(3);
    // The maskable variant must be declared (Android adaptive icons).
    expect(manifest.icons.some((icon) => icon.purpose === 'maskable')).toBe(true);

    for (const icon of manifest.icons) {
        // Resolve relative srcs against the manifest's own URL, like the
        // browser does; absolute srcs pass through new URL untouched.
        const iconUrl = new URL(icon.src, new URL(BASE, baseURL)).toString();
        const iconResponse = await request.get(iconUrl);
        expect(iconResponse.status(), `icon ${icon.src}`).toBe(200);
        expect(iconResponse.headers()['content-type'], `icon ${icon.src}`).toContain('image/png');
    }
});

// (b) The generated service worker is served as JavaScript at the base.
test('sw.js serves with a JavaScript content-type', async ({ request }) => {
    const response = await request.get(`${BASE}sw.js`);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toMatch(/javascript/);
});

// (c) Live registration: registerSW runs on window load (after the title is
// interactive — §2/§10: the initial-load budget window closes at pocReady
// first), so poll for the registration up to 10 s after pocReady. HARD
// assertion: verified stable under vite preview at the subpath.
test('service worker registers against the Pages scope after load', async ({ page }) => {
    await page.goto(BASE);
    await expect(page.locator('body[data-poc-ready="1"]')).toBeAttached({ timeout: 15_000 });

    const registration = await page.evaluate(async () => {
        const deadline = Date.now() + 10_000;
        for (;;) {
            const reg = await navigator.serviceWorker.getRegistration();
            const worker = reg && (reg.active ?? reg.waiting ?? reg.installing);
            if (reg && worker) {
                return { scope: reg.scope, state: worker.state };
            }
            if (Date.now() >= deadline) {
                return null;
            }
            await new Promise((resolve) => setTimeout(resolve, 250));
        }
    });

    expect(registration).not.toBeNull();
    expect(registration!.scope.endsWith(BASE)).toBe(true);
    expect(['installing', 'installed', 'activating', 'activated']).toContain(registration!.state);
});

// (d) iOS has no manifest-icon support: the apple-touch-icon must exist at
// the path index.html points to (public/apple-touch-icon.png → dist root).
test('apple-touch-icon.png resolves at the Pages base', async ({ request }) => {
    const response = await request.get(`${BASE}apple-touch-icon.png`);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('image/png');
});
