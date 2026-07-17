import Phaser from 'phaser';

export class Boot extends Phaser.Scene {
    constructor() {
        super('Boot');
    }

    preload(): void {
        // §3/§4 of docs/PLAN.md: Vite's `base` only rewrites URLs Vite itself
        // processes, not Phaser's runtime string loader paths. Anchoring the
        // loader to BASE_URL makes leading-slash-free keys resolve on both
        // localhost and the GitHub Pages subpath.
        this.load.setBaseURL(import.meta.env.BASE_URL);
    }

    create(): void {
        this.add
            .text(128, 104, 'PROJECT APPRENTICE', {
                fontFamily: 'monospace',
                fontSize: '16px',
                color: '#e0e0e0'
            })
            .setOrigin(0.5);
        this.add
            .text(128, 124, 'M0 walking skeleton', {
                fontFamily: 'monospace',
                fontSize: '8px',
                color: '#808080'
            })
            .setOrigin(0.5);

        // E2E readiness signal (§10): Playwright waits for this attribute.
        document.body.dataset.pocReady = '1';
    }
}
