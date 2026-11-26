/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Commit of the dashboard build, set by the Dockerfile (APP_VERSION build arg).
  readonly VITE_APP_VERSION?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
