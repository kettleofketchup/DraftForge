import { useCallback, useEffect, useRef } from 'react';
import { getLogger } from '~/lib/logger';
import { useDraftWebSocketStore, draftWsSelectors } from '~/store/draftWebSocketStore';
import type { DraftRoundType, DraftType } from '../types';
import { refreshDraftHook } from './refreshDraftHook';

const log = getLogger('useAutoRefreshDraft');

type UseAutoRefreshDraftParams = {
  enabled: boolean;
  curDraftRound: DraftRoundType | null;
  draft: DraftType | null;
  setDraft: (draft: DraftType) => void;
  interval?: number;
};

export const useAutoRefreshDraft = ({
  enabled,
  curDraftRound,
  draft,
  setDraft,
  interval = 5000, // Fallback polling interval when WebSocket disconnected
}: UseAutoRefreshDraftParams) => {
  // Read WebSocket connection status from store
  const wsConnected = useDraftWebSocketStore(draftWsSelectors.isConnected);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const draftRef = useRef(draft);
  const setDraftRef = useRef(setDraft);
  const hasCompletedRefreshRef = useRef(false);

  // Keep refs updated without triggering effect
  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    setDraftRef.current = setDraft;
  }, [setDraft]);

  const refresh = useCallback(async () => {
    if (!draftRef.current) {
      log.error('No draft found');
      return;
    }
    log.debug('Auto-refreshing draft information');
    await refreshDraftHook({ draft: draftRef.current, setDraft: setDraftRef.current });
  }, []);

  // Extract primitive values to avoid object reference changes triggering effect
  const choiceIsNull = curDraftRound?.choice === null;
  const hasDraft = !!draft;
  const hasCurDraftRound = !!curDraftRound;
  const usersRemainingCount = draft?.users_remaining?.length ?? -1;
  const isDraftCompleted = usersRemainingCount === 0;

  useEffect(() => {
    // Clear any existing interval first
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!enabled || !hasDraft) {
      return;
    }

    // If draft is completed, do one final refresh to get complete data
    if (isDraftCompleted) {
      if (!hasCompletedRefreshRef.current) {
        log.debug('Draft completed, performing final refresh');
        hasCompletedRefreshRef.current = true;
        refresh();
      }
      return;
    }

    // Reset completed flag when draft is not completed (e.g., after undo)
    hasCompletedRefreshRef.current = false;

    // If WebSocket is connected, let it handle updates - no polling needed
    if (wsConnected) {
      log.debug('WebSocket connected, skipping auto-refresh polling');
      return;
    }

    // Fallback: Poll only when WebSocket is disconnected and draft not complete
    if (!hasCurDraftRound) {
      return;
    }

    // Only start interval if captain choice is null (waiting for pick)
    if (choiceIsNull) {
      log.debug('WebSocket disconnected, starting fallback auto-refresh polling');
      intervalRef.current = setInterval(refresh, interval);

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      };
    }
  }, [enabled, hasCurDraftRound, hasDraft, choiceIsNull, wsConnected, isDraftCompleted, interval, refresh]);

  return { refresh };
};
