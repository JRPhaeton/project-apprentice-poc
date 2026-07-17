/// <reference types="vite/client" />

interface ImportMetaEnv {
    /** Set by `vite build --mode e2e` (.env.e2e); unset in the Pages deploy build (§4). */
    readonly VITE_ENABLE_DEBUG?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
