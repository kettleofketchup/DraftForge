import { useEffect, useState } from 'react';
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
 * Hook to check if the current user has an active draft turn.
 *
 * Polls the backend every 5 seconds to check if the user is a captain
 * with a pending pick in any active tournament.
 *
 * @returns {Object} Active draft state
 * @returns {ActiveDraftInfo | null} activeDraft - Draft info if user has active turn
 * @returns {boolean} hasActiveTurn - True if user needs to make a pick
 * @returns {boolean} loading - True while initial check is in progress
 * @returns {() => void} refresh - Function to manually trigger a refresh
 *
 * @example
 * const { activeDraft, hasActiveTurn, loading } = useActiveDraft();
 *
 * if (hasActiveTurn) {
 *   // Show notification badge, floating indicator, etc.
 * }
 */
export const useActiveDraft = () => {
  const currentUser = useUserStore((state) => state.currentUser);
  const [activeDraft, setActiveDraft] = useState<ActiveDraftInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const checkActiveDraft = async () => {
    if (!currentUser?.pk) {
      setActiveDraft(null);
      setLoading(false);
      return;
    }

    try {
      const response = await axios.get<ActiveDraftInfo>(
        '/active-draft-for-user/',
      );
      const data = response.data;

      if (data.has_active_turn) {
        log.debug('User has active draft turn:', data);
        setActiveDraft(data);
      } else {
        setActiveDraft(null);
      }
    } catch (err) {
      log.debug('Error checking active draft:', err);
      setActiveDraft(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Initial check
    checkActiveDraft();

    // Poll every 5 seconds
    const interval = setInterval(checkActiveDraft, 5000);

    return () => clearInterval(interval);
  }, [currentUser?.pk]);

  return {
    activeDraft,
    hasActiveTurn: !!activeDraft?.has_active_turn,
    loading,
    refresh: checkActiveDraft,
  };
};
