import { useMemo } from 'react';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import type { DraftRoundType, DraftType } from '../types';
import type { TournamentType, TeamType } from '~/components/tournament/types';
import { DraftRoundCard } from './draftRoundCard';
const log = getLogger('CaptainCards');
interface CaptainCardsProps {}

export const CaptainCards: React.FC<CaptainCardsProps> = ({}) => {
  const draft: DraftType = useUserStore((state) => state.draft);
  const draftIndex: number = useUserStore((state) => state.draftIndex);
  const tournament: TournamentType = useUserStore((state) => state.tournament);

  const totalRounds = (tournament?.teams?.length || 0) * 4;

  // Derive current and next draft rounds with fresh team data from tournament
  const { currentRound, nextRound } = useMemo(() => {
    const rawCurrentRound = draft?.draft_rounds?.[draftIndex];
    const rawNextRound = draft?.draft_rounds?.[draftIndex + 1];

    // Enhance draft rounds with fresh team data from tournament
    const enhanceRound = (round: DraftRoundType | undefined): DraftRoundType => {
      if (!round) return {} as DraftRoundType;
      if (!tournament?.teams || !round.captain?.pk) return round;

      const freshTeam = tournament.teams.find(
        (t: TeamType) => t.captain?.pk === round.captain?.pk
      );
      if (freshTeam) {
        return { ...round, team: freshTeam };
      }
      return round;
    };

    return {
      currentRound: enhanceRound(rawCurrentRound),
      nextRound: enhanceRound(rawNextRound),
    };
  }, [draft?.draft_rounds, draftIndex, tournament?.teams]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center">
        <DraftRoundCard
          draftRound={currentRound}
          maxRounds={totalRounds}
          isCur={true}
        />

        {draftIndex < totalRounds - 1 && nextRound?.pk ? (
          <div className="hidden lg:flex lg:w-full lg:pl-8">
            <DraftRoundCard
              draftRound={nextRound}
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
