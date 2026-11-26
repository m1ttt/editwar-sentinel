import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The api runs on port 8000 in local development (docker compose or uvicorn).
const API_TARGET = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The browser only talks to the Vite server, which forwards these paths to the api.
    proxy: {
      '/api': API_TARGET,
      '/healthz': API_TARGET,
      '/ws': { target: API_TARGET, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/main.tsx', 'src/types.ts', 'src/vite-env.d.ts'],
      reporter: ['text', 'html', 'lcov', 'cobertura'],
      reportsDirectory: 'coverage',
      // The project proposal requires at least 80 % coverage in the pipeline.
      thresholds: { lines: 80, statements: 80, functions: 80, branches: 80 },
    },
  },
})
