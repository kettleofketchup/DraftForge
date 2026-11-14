// Design-system gate: @shadcn/lint rules only. Separate from eslint.config.js so
// `npm run lint` (navbar-scoped) and this gate move independently.
// Existing violations live in shadcn-lint-suppressions.json; see the shadcn-lint skill.
import { plugin as shadcn } from '@shadcn/lint';
import tsParser from '@typescript-eslint/parser';
import i18next from 'eslint-plugin-i18next';
import reactHooks from 'eslint-plugin-react-hooks';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';

export default defineConfig([
  {
    ignores: [
      'build/**',
      'node_modules/**',
      '.react-router/**',
      'public/build/**',
    ],
  },
  {
    files: ['app/**/*.{js,jsx,ts,tsx}'],
    linterOptions: { reportUnusedDisableDirectives: 'off' },
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    // Registered with no rules on, so eslint-disable comments for them still resolve.
    plugins: {
      shadcn,
      i18next,
      'react-hooks': reactHooks,
      '@typescript-eslint': tseslint.plugin,
    },
    settings: {
      shadcn: {
        note: 'Brand tokens and components: docs/THEMING-GUIDE.md.',
      },
    },
    rules: {
      // Raw palette classes and hex values instead of brand tokens.
      'shadcn/no-raw-colors': 'error',
      // Classes Tailwind generates no CSS for: typos, v3 names, missing plugins.
      // allow: runtime hook classes, not Tailwind utilities. nodrag/nopan are read by
      // React Flow, toaster by sonner, spinner by node-status-indicator's inline <style>.
      'shadcn/no-unknown-classes': [
        'error',
        { allow: ['nodrag', 'nopan', 'toaster', 'spinner'] },
      ],

      // Off: conflicts with the brand guide or is a design decision, not a lint one.
      'shadcn/no-restyle': 'off',
      'shadcn/no-inline-styles': 'off',
      'shadcn/no-arbitrary-values': 'off',
      'shadcn/require-static-classes': 'off',
    },
  },
]);
