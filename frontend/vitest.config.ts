import tsconfigPaths from 'vite-tsconfig-paths';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    include: ['app/**/*.test.ts', 'app/**/*.test.tsx', 'tests/unit/**/*.test.ts'],
  },
});
