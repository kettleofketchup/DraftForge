import { useEffect, useRef } from 'react';
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
  interval = 1000,
}: UseAutoRefreshDraftParams) => {
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const refresh = async () => {
    if (!draft) {
      log.error('No draft found');
      return;
    }
    log.debug('Auto-refreshing draft information');
    await refreshDraftHook({ draft, setDraft });
  };

  useEffect(() => {
    if (!enabled || !curDraftRound || !draft) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    // Check if current captain choice is null
    if (curDraftRound.choice === null) {
      log.debug('Captain choice is null, starting auto-refresh');
      intervalRef.current = setInterval(() => {
        refresh();
      }, interval);

      return () => {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      };
    } else {
      // Clear interval if choice is not null
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [
    enabled,
    curDraftRound,
    curDraftRound?.choice,
    draft,
    setDraft,
    interval,
  ]);

  return { refresh };
};
