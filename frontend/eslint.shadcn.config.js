// Design-system gate: @shadcn/lint rules only. Separate from eslint.config.js so
// `npm run lint` (navbar-scoped) and this gate move independently.
// Existing violations live in shadcn-lint-suppressions.json; see the shadcn-lint skill.
import { plugin as shadcn } from '@shadcn/lint';
import tsParser from '@typescript-eslint/parser';
import i18next from 'eslint-plugin-i18next';
import reactHooks from 'eslint-plugin-react-hooks';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';

import draftforge from './eslint-rules/index.js';

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
    processor: draftforge.processors['dedupe-raw-colors'],
    linterOptions: { reportUnusedDisableDirectives: 'off' },
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    // i18next, react-hooks and @typescript-eslint have no rules on; registered so
    // eslint-disable comments for them still resolve.
    plugins: {
      shadcn,
      draftforge,
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

      // People render through the shared helpers so org server nicknames, Discord
      // names and avatar fallbacks stay consistent.
      'draftforge/use-display-name': 'error',
      'draftforge/use-user-avatar': 'error',
      // The org comes from the route and user data from the cache (#600).
      'draftforge/no-display-org-arg': 'error',
      'draftforge/no-user-reshape': 'error',
      'draftforge/no-direct-name-resolver': 'error',
      'draftforge/no-avatar-fallback': 'error',
      // Raw palette classes in strings shadcn/no-raw-colors cannot trace to a
      // className (maps, arrays, returns); the processor drops its duplicates.
      'draftforge/no-raw-color-strings': 'error',
      // Colour literals inside arbitrary values: shadow-[..rgba(..)], bg-[#..].
      'draftforge/no-arbitrary-color-literals': 'error',

      // Off: conflicts with the brand guide or is a design decision, not a lint one.
      'shadcn/no-restyle': 'off',
      'shadcn/no-inline-styles': 'off',
      'shadcn/no-arbitrary-values': 'off',
      'shadcn/require-static-classes': 'off',
    },
  },
  {
    // The helpers themselves, and the shadcn primitives they wrap.
    files: [
      'app/components/user/UserAvatar.tsx',
      'app/components/user/avatar.tsx',
      'app/lib/userDisplayName.ts',
      'app/lib/displayOrg.ts',
      'app/components/ui/**',
    ],
    rules: {
      'draftforge/use-display-name': 'off',
      'draftforge/use-user-avatar': 'off',
      'draftforge/no-display-org-arg': 'off',
      'draftforge/no-user-reshape': 'off',
      'draftforge/no-direct-name-resolver': 'off',
      'draftforge/no-avatar-fallback': 'off',
    },
  },
  {
    // Tests exercise the resolver and the org override directly.
    files: ['app/**/*.test.{ts,tsx}', 'app/**/__tests__/**'],
    rules: {
      'draftforge/no-display-org-arg': 'off',
      'draftforge/no-direct-name-resolver': 'off',
      'draftforge/no-raw-color-strings': 'off',
      'draftforge/no-arbitrary-color-literals': 'off',
    },
  },
]);
