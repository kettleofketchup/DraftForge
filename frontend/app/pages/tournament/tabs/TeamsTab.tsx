import { memo, useMemo, useState } from 'react';
import { TeamLeadershipAlert } from '~/components/team/manage/TeamLeadershipAlert';
import { useCanEditCurrentTournament } from '~/components/team/manage/useTeamManagement';
import { SearchTeamsDropdown } from '~/components/team/searchTeams';
import { TeamCard } from '~/components/teamdraft/CompletedTeamDraftView';
import { DraftModal } from '~/components/teamdraft/draftModal';
import { CaptainSelectionModal } from '~/components/tournament/captains/captainSelectionModal';
import { useSharedPopoverActions } from '~/components/ui/shared-popover-context';
import { userMatchesQuery } from '~/lib/userSearch';

import type { UserType } from '~/components/user/types';
import type { TeamType } from '~/index';
import { hasErrors } from '~/pages/tournament/hasErrors';
import { useUserStore } from '~/store/userStore';
import { RandomizeTeamsModal } from './teams/randomTeamsModal';

export const TeamsTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const [query, setQuery] = useState('');
  const canEdit = useCanEditCurrentTournament();
  const { openTeamModal } = useSharedPopoverActions();

  // Memoize filtered teams to prevent recalculation on every render
  const filteredTeams = useMemo(() => {
    if (!tournament.teams) return [];
    if (query === '') return tournament.teams;

    const q = query.toLowerCase();
    return tournament.teams
      .filter((team: TeamType) => {
        // Check if any user in the team matches the query
        const userMatches = team.members?.some((user: UserType) =>
          userMatchesQuery(user, q),
        );

        // Check if team name matches
        const teamNameMatch = team.name?.toLowerCase().includes(q);

        return userMatches || teamNameMatch;
      })
      .sort((a: TeamType, b: TeamType) => a.name.localeCompare(b.name));
  }, [tournament.teams, query]);
  const teamButtonsView = () => {
    return (
      <div
        className="flex flex-row justify-center items-center gap-2 w-full px-2 py-3 sm:gap-4 sm:p-4 sm:pt-2 sm:pb-6"
        data-testid="teams-tab-actions"
      >
        <RandomizeTeamsModal users={tournament?.users || []} teamSize={5} />
        <CaptainSelectionModal />
        <DraftModal />
      </div>
    );
  };

  return (
    <div className="p-5 container">
      {hasErrors()}
      <TeamLeadershipAlert
        teams={tournament?.teams ?? []}
        canEdit={canEdit}
        onReview={openTeamModal}
      />
      {teamButtonsView()}
      <div className="w-full">
        <SearchTeamsDropdown
          teams={tournament?.teams || []}
          query={query}
          setQuery={setQuery}
          data-testid="teamsSearchDropdown"
        />
      </div>
      <div className="grid gap-4 md:gap-6 mt-4 grid-cols-1 lg:grid-cols-2 w-full">
        {filteredTeams?.map((team: TeamType, index: number) => (
          <TeamCard
            team={team}
            rank={index + 1}
            key={`TeamCard-${team.pk}`}
            organizationId={tournament?.organization_pk ?? undefined}
            leaguePk={tournament?.league_pk ?? null}
            canEdit={canEdit}
            tournamentUsers={tournament?.users}
          />
        ))}
      </div>
    </div>
  );
});
