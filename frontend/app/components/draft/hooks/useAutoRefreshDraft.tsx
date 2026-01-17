import { useCallback, useEffect, useRef } from 'react';
import { getLogger } from '~/lib/logger';
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
  interval = 3000, // Increased from 1000ms to reduce API calls
}: UseAutoRefreshDraftParams) => {
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const draftRef = useRef(draft);
  const setDraftRef = useRef(setDraft);

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

  useEffect(() => {
    // Clear any existing interval first
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!enabled || !hasCurDraftRound || !hasDraft) {
      return;
    }

    // Only start interval if captain choice is null
    if (choiceIsNull) {
      log.debug('Captain choice is null, starting auto-refresh');
      intervalRef.current = setInterval(refresh, interval);

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      };
    }
  }, [enabled, hasCurDraftRound, hasDraft, choiceIsNull, interval, refresh]);

  return { refresh };
};
