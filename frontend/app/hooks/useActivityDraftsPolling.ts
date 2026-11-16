import { useCallback, useEffect, useRef } from 'react';
import { useLeaveGuard } from '~/components/activity/LeaveDraftConfirm';
import { fetchActivityDrafts } from '~/lib/activity-api';
import type { ActivityView, LaunchIntentRef } from '~/lib/activity-types';
import { getLogger } from '~/lib/logger';
import { sameView, useActivityViewStore } from '~/store/activityViewStore';

const log = getLogger('activity');

export const ACTIVITY_DRAFTS_POLL_MS = 30_000;

export function useActivityDraftsPolling(enabled: boolean): {
  refetch(): Promise<void>;
} {
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const guard = useLeaveGuard();
  const prompting = useRef(new Set<string>());

  const applyIntent = useCallback(
    (intent: LaunchIntentRef) => {
      const id = intent.intent_id;
      const store = useActivityViewStore.getState();
      if (store.appliedIntentIds.has(id) || prompting.current.has(id)) return;
      const target: ActivityView = { kind: intent.kind, id: intent.id };
      const apply = () => {
        prompting.current.delete(id);
        useActivityViewStore
          .getState()
          .setView(target, 'launch_intent', { intentId: id });
      };
      if (sameView(store.view, target)) {
        apply();
        return;
      }
      prompting.current.add(id);
      log.info('activity launch intent received', { intentId: id, target });
      guard(apply, () => {
        prompting.current.delete(id);
        useActivityViewStore.getState().declineIntent(id);
      });
    },
    [guard],
  );

  const refetch = useCallback(async () => {
    if (!enabledRef.current) return;
    try {
      const drafts = await fetchActivityDrafts();
      if (!enabledRef.current) return;
      const store = useActivityViewStore.getState();
      store.setDrafts(drafts);
      if (drafts.notice) store.showNotice(drafts.notice);
      if (drafts.launch_intent) applyIntent(drafts.launch_intent);
    } catch (error) {
      log.warn('activity_drafts_fetch_failed', { error });
    }
  }, [applyIntent]);

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
