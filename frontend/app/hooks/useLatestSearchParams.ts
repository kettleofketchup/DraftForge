import { useCallback, useContext } from 'react';
import {
  UNSAFE_DataRouterContext,
  useSearchParams,
  type SetURLSearchParams,
} from 'react-router';

/**
 * `useSearchParams`, but a functional update receives the params of the
 * router's latest (possibly still loading) navigation instead of the last
 * render, so back-to-back writes from different hooks don't drop each other.
 */
export function useLatestSearchParams(): [URLSearchParams, SetURLSearchParams] {
  const [searchParams, setSearchParams] = useSearchParams();
  const router = useContext(UNSAFE_DataRouterContext)?.router;

  const set = useCallback<SetURLSearchParams>(
    (nextInit, options) => {
      if (typeof nextInit !== 'function' || !router) {
        setSearchParams(nextInit, options);
        return;
      }
      const { location, navigation } = router.state;
      const latest =
        navigation.location?.pathname === location.pathname
          ? navigation.location
          : location;
      setSearchParams(nextInit(new URLSearchParams(latest.search)), options);
    },
    [router, setSearchParams],
  );

  return [searchParams, set];
}
