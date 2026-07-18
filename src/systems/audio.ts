import Phaser from 'phaser';

import { markMusic } from './hooks';
import { getRegistry } from './registry';

/**
 * Audio manager (§6 of docs/PLAN.md + docs/AUDIO_BIBLE.md). Reads
 * src/data/audio-manifest.json (registry-held under defs.audio); every key
 * loads as an [ogg, m4a] URL array relative to the loader base. Music is
 * full-file gapless `sound.play(key, { loop: true, volume })` — NO
 * loopStart/loopEnd. SFX are one-shots at manifest volume.
 *
 * LAZY (§2): nothing here loads in Preload. Callers ensure/play on first
 * need — 'music.overworld' at first Overworld enter, battle+boss music and
 * all SFX inside the Battle scene's existing first-entry loading affordance.
 *
 * Failure-tolerant: missing files (audio lands from the Assets lane in
 * parallel) degrade to silence — no crash, no console.error, at most ONE
 * console.warn per session. Browser autoplay: when the sound manager is
 * locked, playback defers to Phaser's UNLOCKED event (first user input);
 * the data-poc-music hook is set only when a track really starts.
 */

/** Everything the Battle scene needs, loaded in its first-entry batch. */
export const BATTLE_AUDIO_KEYS = [
    'music.battle',
    'music.boss',
    'sfx.attack',
    'sfx.hit',
    'sfx.magic',
    'sfx.victory',
    'sfx.menu',
    'sfx.levelup' // M10: victory-toast level-up jingle
];

type LoadState = 'loading' | 'ready' | 'failed';

const states = new Map<string, LoadState>();
let currentMusic: string | null = null;
let wantedMusic: string | null = null;
let wantedLoop = true;
let warned = false;

function warnOnce(): void {
    if (!warned) {
        warned = true;
        console.warn('[audio] audio asset(s) unavailable - running silent');
    }
}

/** Shared loaderror handler; only flips keys this manager queued. */
function onLoadError(file: Phaser.Loader.File): void {
    if (states.get(file.key) === 'loading') {
        states.set(file.key, 'failed');
        warnOnce();
    }
}

function volumeOf(scene: Phaser.Scene, key: string): number {
    return getRegistry(scene).get('defs').audio[key]?.volume ?? 1;
}

/**
 * Queue any not-yet-loaded manifest keys on the scene's loader. Does NOT
 * start the loader — Battle folds this into its existing load batch; other
 * callers (playMusic/playSfx) start it themselves.
 */
export function ensureAudio(scene: Phaser.Scene, keys: string[]): void {
    const manifest = getRegistry(scene).get('defs').audio;
    const queued: string[] = [];
    for (const key of keys) {
        if (states.has(key) || scene.cache.audio.exists(key)) {
            continue;
        }
        const entry = manifest[key];
        if (!entry) {
            states.set(key, 'failed');
            warnOnce();
            continue;
        }
        states.set(key, 'loading');
        queued.push(key);
        // §6: dual-codec URL array, paths relative to the loader base.
        scene.load.audio(key, [entry.ogg, entry.m4a]);
        scene.load.once(`filecomplete-audio-${key}`, () => {
            states.set(key, 'ready');
            // A music key wanted while it was still loading starts now.
            if (key === wantedMusic) {
                startMusic(scene, key);
            }
        });
    }
    if (queued.length > 0) {
        scene.load.off(Phaser.Loader.Events.FILE_LOAD_ERROR, onLoadError);
        scene.load.on(Phaser.Loader.Events.FILE_LOAD_ERROR, onLoadError);
        // Scene shutdown aborts in-flight loads: revert so a later scene retries.
        scene.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
            for (const key of queued) {
                if (states.get(key) === 'loading') {
                    states.delete(key);
                }
            }
        });
    }
}

function stopCurrent(sound: Phaser.Sound.BaseSoundManager): void {
    if (currentMusic) {
        try {
            sound.removeByKey(currentMusic);
        } catch {
            // NoAudio manager edge; silence is the correct outcome.
        }
    }
    currentMusic = null;
    markMusic(null);
}

function startMusic(scene: Phaser.Scene, key: string): void {
    const sound = scene.sound;
    if (currentMusic === key && sound.get(key)?.isPlaying) {
        markMusic(key); // already on this track (e.g. room switch) — no restart
        return;
    }
    stopCurrent(sound);
    currentMusic = key;
    const begin = (): void => {
        if (wantedMusic !== key || currentMusic !== key) {
            return; // superseded while waiting for load/unlock
        }
        const loop = wantedLoop;
        try {
            // §6: full-file gapless loop — no loopStart/loopEnd, ever. M6
            // adds one-shot tracks (music.sting) via { loop: false }.
            if (sound.play(key, { loop, volume: volumeOf(scene, key) })) {
                markMusic(key);
                if (!loop) {
                    // One-shots clear the pocMusic hook when they end.
                    sound.get(key)?.once(Phaser.Sound.Events.COMPLETE, () => {
                        if (currentMusic === key) {
                            currentMusic = null;
                            markMusic(null);
                        }
                        if (wantedMusic === key) {
                            wantedMusic = null;
                        }
                    });
                }
            }
        } catch {
            warnOnce();
        }
    };
    if (sound.locked) {
        sound.once(Phaser.Sound.Events.UNLOCKED, begin);
    } else {
        begin();
    }
}

/**
 * Route music to `key`: play immediately when loaded, else lazy-load then
 * play. Re-requesting the playing track is a no-op (gapless across rooms).
 * `opts.loop` defaults to true; pass false for one-shot stings.
 */
export function playMusic(scene: Phaser.Scene, key: string, opts?: { loop?: boolean }): void {
    wantedMusic = key;
    wantedLoop = opts?.loop ?? true;
    if (scene.cache.audio.exists(key)) {
        startMusic(scene, key);
        return;
    }
    if (states.get(key) === 'failed') {
        return;
    }
    ensureAudio(scene, [key]);
    scene.load.start(); // no-op when the loader is already running
}

/** Stop whatever music is playing and clear the data-poc-music hook. */
export function stopMusic(scene: Phaser.Scene): void {
    wantedMusic = null;
    stopCurrent(scene.sound);
}

/**
 * One-shot SFX at manifest volume. First-ever call may only kick off the
 * lazy load (that press is silent); locked/missing audio is silently skipped.
 */
export function playSfx(scene: Phaser.Scene, key: string): void {
    if (scene.cache.audio.exists(key)) {
        if (scene.sound.locked) {
            return;
        }
        try {
            scene.sound.play(key, { volume: volumeOf(scene, key) });
        } catch {
            warnOnce();
        }
        return;
    }
    if (states.get(key) === 'failed') {
        return;
    }
    ensureAudio(scene, [key]);
    scene.load.start();
}
