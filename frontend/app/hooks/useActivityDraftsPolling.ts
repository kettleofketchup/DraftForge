import { useCallback, useEffect, useRef } from 'react';
import { fetchActivityDrafts } from '~/lib/activity-api';
import { getLogger } from '~/lib/logger';
import { useActivityViewStore } from '~/store/activityViewStore';

const log = getLogger('activity');

export const ACTIVITY_DRAFTS_POLL_MS = 30_000;

export function useActivityDraftsPolling(enabled: boolean): {
  refetch(): Promise<void>;
} {
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const refetch = useCallback(async () => {
    if (!enabledRef.current) return;
    try {
      const drafts = await fetchActivityDrafts();
      if (!enabledRef.current) return;
      useActivityViewStore.getState().setDrafts(drafts);
    } catch (error) {
      log.warn('activity_drafts_fetch_failed', { error });
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void refetch();
    const interval = setInterval(() => void refetch(), ACTIVITY_DRAFTS_POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refetch();
    };
    const onFocus = () => void refetch();
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
    };
  }, [enabled, refetch]);

  return { refetch };
}
