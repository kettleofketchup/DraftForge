// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { shouldShowTestFeatures } from '~/lib/test-utils';

describe('shouldShowTestFeatures', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('is true in a non-dev build with VITE_PREVIEW_TEST_FEATURES=true', () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('VITE_PREVIEW_TEST_FEATURES', 'true');
    expect(shouldShowTestFeatures()).toBe(true);
  });

  it('is false in a non-dev build with VITE_PREVIEW_TEST_FEATURES=false', () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('VITE_PREVIEW_TEST_FEATURES', 'false');
    expect(shouldShowTestFeatures()).toBe(false);
  });

  it('is false under Playwright even with the preview flag on', () => {
    vi.stubEnv('DEV', false);
    vi.stubEnv('VITE_PREVIEW_TEST_FEATURES', 'true');
    vi.stubGlobal('playwright', true);
    expect(shouldShowTestFeatures()).toBe(false);
  });
});
