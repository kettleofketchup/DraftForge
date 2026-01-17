import { useEffect, useRef, useSyncExternalStore } from 'react';
import axios from '~/components/api/axios';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('useActiveDraft');

/**
 * Information about an active draft where the user is captain with a pending pick.
 */
export interface ActiveDraftInfo {
  has_active_turn: boolean;
  tournament_pk?: number;
  tournament_name?: string;
  draft_round_pk?: number;
  pick_number?: number;
}

/**
 * Singleton state manager for active draft polling.
 * Ensures only ONE polling interval exists regardless of how many components use the hook.
 */
class ActiveDraftManager {
  private static instance: ActiveDraftManager;
  private subscribers = new Set<() => void>();
  private state: ActiveDraftInfo | null = null;
  private loading = true;
  private intervalRef: NodeJS.Timeout | null = null;
  private currentUserPk: number | null = null;
  // Memoized snapshot to prevent infinite re-renders with useSyncExternalStore
  private snapshot: { state: ActiveDraftInfo | null; loading: boolean } = {
    state: null,
    loading: true,
  };

  private constructor() {}

  static getInstance(): ActiveDraftManager {
    if (!ActiveDraftManager.instance) {
      ActiveDraftManager.instance = new ActiveDraftManager();
    }
    return ActiveDraftManager.instance;
  }

  subscribe = (callback: () => void): (() => void) => {
    this.subscribers.add(callback);
    // Start polling when first subscriber joins
    if (this.subscribers.size === 1 && this.currentUserPk) {
      this.startPolling();
    }
    return () => {
      this.subscribers.delete(callback);
      // Stop polling when last subscriber leaves
      if (this.subscribers.size === 0) {
        this.stopPolling();
      }
    };
  };

  private notify = () => {
    this.subscribers.forEach((callback) => callback());
  };

  // Update the memoized snapshot - call this before notify()
  private updateSnapshot = () => {
    this.snapshot = { state: this.state, loading: this.loading };
  };

  getSnapshot = (): { state: ActiveDraftInfo | null; loading: boolean } => {
    // Return the memoized snapshot to prevent infinite re-renders
    return this.snapshot;
  };

  setCurrentUser = (userPk: number | null) => {
    if (this.currentUserPk === userPk) return;

    this.currentUserPk = userPk;

    if (!userPk) {
      this.state = null;
      this.loading = false;
      this.stopPolling();
      this.updateSnapshot();
      this.notify();
      return;
    }

    // Only start polling if we have subscribers
    if (this.subscribers.size > 0) {
      this.startPolling();
    }
  };

  private startPolling = () => {
    if (this.intervalRef) return;

    // Immediate check
    this.checkActiveDraft();

    // Poll every 5 seconds
    this.intervalRef = setInterval(this.checkActiveDraft, 5000);
    log.debug('Started active draft polling');
  };

  private stopPolling = () => {
    if (this.intervalRef) {
      clearInterval(this.intervalRef);
      this.intervalRef = null;
      log.debug('Stopped active draft polling');
    }
  };

  private checkActiveDraft = async () => {
    if (!this.currentUserPk) {
      this.state = null;
      this.loading = false;
      this.updateSnapshot();
      this.notify();
      return;
    }

    try {
      const response = await axios.get<ActiveDraftInfo>(
        '/active-draft-for-user/',
      );
      const data = response.data;

      if (data.has_active_turn) {
        log.debug('User has active draft turn:', data);
        this.state = data;
      } else {
        this.state = null;
      }
    } catch (err) {
      log.debug('Error checking active draft:', err);
      this.state = null;
    } finally {
      this.loading = false;
      this.updateSnapshot();
      this.notify();
    }
  };

  refresh = () => {
    this.checkActiveDraft();
  };
}

const manager = ActiveDraftManager.getInstance();

/**
 * Hook to check if the current user has an active draft turn.
 *
 * Uses a singleton manager to ensure only ONE polling interval exists
 * regardless of how many components use this hook.
 *
 * @returns {Object} Active draft state
 * @returns {ActiveDraftInfo | null} activeDraft - Draft info if user has active turn
 * @returns {boolean} hasActiveTurn - True if user needs to make a pick
 * @returns {boolean} loading - True while initial check is in progress
 * @returns {() => void} refresh - Function to manually trigger a refresh
 */
export const useActiveDraft = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const currentUserPkRef = useRef<number | null>(null);

  // Update manager when user changes
  useEffect(() => {
    const userPk = currentUser?.pk ?? null;
    if (currentUserPkRef.current !== userPk) {
      currentUserPkRef.current = userPk;
      manager.setCurrentUser(userPk);
    }
  }, [currentUser?.pk]);

  // Subscribe to manager state changes
  const { state: activeDraft, loading } = useSyncExternalStore(
    manager.subscribe,
    manager.getSnapshot,
    manager.getSnapshot, // Server snapshot (same as client for this use case)
  );

  return {
    activeDraft,
    hasActiveTurn: !!activeDraft?.has_active_turn,
    loading,
    refresh: manager.refresh,
  };
};
