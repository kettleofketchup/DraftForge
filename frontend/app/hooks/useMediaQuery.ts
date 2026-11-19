import { useCallback, useSyncExternalStore } from 'react';

/** SSR-safe `matchMedia` subscription; renders `false` on the server and first hydration pass. */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (notify: () => void) => {
      if (typeof window === 'undefined' || !window.matchMedia) return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener('change', notify);
      return () => mql.removeEventListener('change', notify);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () =>
      typeof window !== 'undefined' && !!window.matchMedia
        ? window.matchMedia(query).matches
        : false,
    () => false,
  );
}
