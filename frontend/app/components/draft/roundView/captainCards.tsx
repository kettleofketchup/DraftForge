import React, { useEffect, useMemo } from 'react';
import { getLogger } from '~/lib/logger';
import { useTeamDraftStore } from '~/store/teamDraftStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';
import type { DraftRoundType } from '../types';
import { DraftRoundCard } from './draftRoundCard';
const log = getLogger('CaptainCards');
interface CaptainCardsProps {}

export const CaptainCards: React.FC<CaptainCardsProps> = ({}) => {
  // Only subscribe to draft_rounds (not entire draft)
  const draftRounds = useTeamDraftStore((state) => state.draft?.draft_rounds);
  const currentRoundIndex = useTeamDraftStore((state) => state.currentRoundIndex);
  const teams = useTournamentDataStore((state) => state.teams);

  // Derive current round from subscribed state (reactive)
  const curDraftRound = useMemo(() => {
    if (!draftRounds || draftRounds.length === 0) return null;
    return draftRounds[currentRoundIndex] ?? null;
  }, [draftRounds, currentRoundIndex]);

  useEffect(() => {}, [curDraftRound?.pk]);

  const totalRounds = (teams?.length || 0) * 4;

  useEffect(() => {
    log.debug('index changed:');

  }, [currentRoundIndex]);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center">
        <DraftRoundCard
          draftRound={
            draftRounds?.[currentRoundIndex] || ({} as DraftRoundType)
          }
          maxRounds={totalRounds}
          isCur={true}
        />

        {currentRoundIndex < totalRounds - 1 &&
        draftRounds &&
        draftRounds[currentRoundIndex + 1] ? (
          <div className="hidden lg:flex lg:w-full lg:pl-8">
            <DraftRoundCard
              draftRound={draftRounds[currentRoundIndex + 1]}
              maxRounds={totalRounds}
              isCur={false}
            />
          </div>
        ) : (
          <></>
        )}
      </div>
    </div>
  );
};
