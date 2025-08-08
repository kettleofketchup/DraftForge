import { useCallback, useEffect, useRef } from 'react';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('useDraftLive');

interface UseDraftLiveOptions {
  enabled?: boolean;
  interval?: number; // in milliseconds
  onUpdate?: () => void;
}

export const useDraftLive = ({
  enabled = true,
  interval = 3000, // 3 seconds default
  onUpdate,
}: UseDraftLiveOptions = {}) => {
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const isPollingRef = useRef(false);
  const onUpdateRef = useRef(onUpdate);

  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  );
  const getCurrentDraftRound = useUserStore(
    (state) => state.getCurrentDraftRound,
  );
  const getDraft = useUserStore((state) => state.getDraft);
  const tournament = useUserStore((state) => state.tournament);
  const draft = useUserStore((state) => state.draft);
  const setCurDraftRound = useUserStore((state) => state.setCurDraftRound);

  // Keep onUpdate ref current
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  const fetchLatestData = useCallback(async () => {
    if (isPollingRef.current) {
      log.debug('Already polling, skipping fetch');
      return;
    }

    try {
      isPollingRef.current = true;
      log.debug('Fetching latest draft data...');

      // Fetch both tournament and draft data
      await Promise.all([getDraft(), getCurrentDraftRound()]);

      onUpdateRef.current?.();
      log.debug('Draft data updated successfully');
    } catch (error) {
      log.error('Failed to fetch latest draft data:', error);
    } finally {
      isPollingRef.current = false;
    }
  }, [getCurrentTournament, getDraft]);

  const startPolling = useCallback(() => {
    if (!enabled || intervalRef.current) return;

    log.debug(`Starting draft live polling with ${interval}ms interval`);
    intervalRef.current = setInterval(() => {
      fetchLatestData();
    }, interval);
  }, [enabled, interval]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      log.debug('Stopping draft live polling');
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const forceRefresh = useCallback(() => {
    log.debug('Force refreshing draft data');
    fetchLatestData();
  }, []);

  // Start/stop polling based on enabled state and interval changes
  useEffect(() => {
    if (enabled) {
      stopPolling(); // Stop any existing polling first
      startPolling();
    } else {
      stopPolling();
    }

    return stopPolling;
  }, [enabled, interval]); // Remove startPolling and stopPolling from deps

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  return {
    isPolling: intervalRef.current !== null,
    forceRefresh,
    startPolling,
    stopPolling,
    tournament,
    draft,
  };
};
