/**
 * Hydration-safe shouldShowTestFeatures().
 *
 * The server cannot see window.playwright, so it always renders false and the
 * client decides after hydration. Calling shouldShowTestFeatures() during
 * render instead would let the server and a Playwright client disagree, which
 * is a hydration mismatch.
 */
import { useSyncExternalStore } from 'react';
import { shouldShowTestFeatures } from '~/lib/test-utils';

const subscribeNoop = () => () => {};

export function useShowTestFeatures(): boolean {
  const hydrated = useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false,
  );
  return hydrated && shouldShowTestFeatures();
}
