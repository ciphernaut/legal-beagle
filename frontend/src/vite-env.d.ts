/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend base URL for static production builds; defaults to same-origin `/api`. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
