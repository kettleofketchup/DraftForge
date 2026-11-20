import { useCallback } from 'react';
import {
  useLocation,
  useSearchParams,
  type NavigateOptions,
} from 'react-router';

type Update = (latest: URLSearchParams) => URLSearchParams;

/** `useSearchParams` whose updater starts from the browser URL while on this route; `prev` lags a navigation not yet rendered. */
export function useLatestSearchParams() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { pathname } = useLocation();

  const setLatest = useCallback(
    (update: Update, options?: NavigateOptions) => {
      setSearchParams((prev) => {
        const live =
          typeof window !== 'undefined' &&
          window.location.pathname === pathname;
        return update(
          new URLSearchParams(live ? window.location.search : prev),
        );
      }, options);
    },
    [setSearchParams, pathname],
  );

  return [searchParams, setLatest] as const;
}
