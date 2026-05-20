import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import prettier from 'eslint-config-prettier';
import i18next from 'eslint-plugin-i18next';

export default [
  {
    ignores: [
      'build/**',
      'node_modules/**',
      '.react-router/**',
      'public/build/**',
      'tests/playwright/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { react, 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    rules: {
      // Permissive defaults — strictness is ratcheted in a separate cleanup PR.
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      'no-empty': 'off',
      'no-prototype-builtins': 'off',
      'no-undef': 'off',
    },
  },
  // Strict i18n enforcement scoped to navbar
  {
    files: ['app/components/navbar/**/*.{ts,tsx}'],
    plugins: { i18next },
    rules: {
      'i18next/no-literal-string': [
        'error',
        {
          markupOnly: true,
          ignoreAttribute: ['data-testid', 'className', 'href', 'to'],
        },
      ],
    },
  },
  prettier,
];
