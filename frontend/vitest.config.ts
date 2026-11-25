import tsconfigPaths from 'vite-tsconfig-paths';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    include: [
      'app/**/*.test.ts',
      'app/**/*.test.tsx',
      'tests/unit/**/*.test.ts',
    ],
    setupFiles: ['./vitest.setup.ts'],
    // Local default is a cap so parallel sessions don't saturate the host; CI keeps Vitest's default.
    maxWorkers: process.env.CI
      ? undefined
      : Number(process.env.VITEST_MAX_WORKERS ?? 4),
  },
});
