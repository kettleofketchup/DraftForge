import React, { useEffect, useMemo } from 'react';
import type { UserClassType } from '~/index';
import { getLogger } from '~/lib/logger';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { UserCard } from '../../user';
import { DoublePickThreshold } from '../shuffle/DoublePickThreshold';
import { DraftTable } from './draftTable';
const log = getLogger('choiceCard');
interface PlayerChoiceViewProps {}
export const PlayerChoiceView: React.FC<PlayerChoiceViewProps> = ({}) => {
  // Only subscribe to draft_rounds (not entire draft)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);
  // Subscribe to users_remaining length for debugging (separate subscription)
  const usersRemainingLength = useTeamDraftStore((state) => state.draft?.users_remaining?.length);

  // Derive current round from subscribed state (reactive)
  const curRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);
  useEffect(() => {
    log.debug('rerender: Current choice updated:', curRound?.choice);
  }, [curRound?.choice]);
  useEffect(() => {
    log.debug(
      'rerender: draft users remaining updated:',
      usersRemainingLength,
    );
  }, [usersRemainingLength]);

  if (!curRound || !curRound?.choice)
    return (
      <div>
        <DoublePickThreshold />
        <DraftTable />
      </div>
    );

  return (
    <div className="mb-4">
      <h3 className="text-xl font-bold">Current Choice</h3>
      <div className="flex flex-col items-center justify-center">
        <UserCard user={curRound?.choice as UserClassType} compact={true} />
      </div>
    </div>
  );
};
