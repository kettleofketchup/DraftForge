import { memo, useMemo, useState } from 'react';
import { DraftModal } from '~/components/draft/draftModal';
import { SearchTeamsDropdown } from '~/components/team/searchTeams';
import { TeamCard } from '~/components/team/teamCard';
import { CaptainSelectionModal } from '~/components/tournament/captains/captainSelectionModal';

import type { UserType } from '~/components/user/types';
import type { TeamType } from '~/index';
import { hasErrors } from '~/pages/tournament/hasErrors';
import { useUserStore } from '~/store/userStore';
import { RandomizeTeamsModal } from './teams/randomTeamsModal';

export const TeamsTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);
  const [query, setQuery] = useState('');

  // Memoize filtered teams to prevent recalculation on every render
  const filteredTeams = useMemo(() => {
    if (!tournament.teams) return [];
    if (query === '') return tournament.teams;

    const q = query.toLowerCase();
    return tournament.teams
      .filter((team: TeamType) => {
        // Check if any user in the team matches the query
        const userMatches = team.members?.some((user: UserType) => {
          const usernameMatch = user.username?.toLowerCase().includes(q);
          const nicknameMatch = user.nickname?.toLowerCase().includes(q);
          return usernameMatch || nicknameMatch;
        });

        // Check if team name matches
        const teamNameMatch = team.name?.toLowerCase().includes(q);

        return userMatches || teamNameMatch;
      })
      .sort((a: TeamType, b: TeamType) => a.name.localeCompare(b.name));
  }, [tournament.teams, query]);
  const teamButtonsView = () => {
    return (
      <div
        className="flex flex-col justify-center items-center gap-y-4 w-full flex-grow sm:flex-row
       sm:gap-y-2 sm:gap-x-8 sm:p-4 sm:pt-2 sm:pb-6 "
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
      {teamButtonsView()}
      <div className="w-full">
        <SearchTeamsDropdown
          teams={tournament?.teams || []}
          query={query}
          setQuery={setQuery}
          data-testid="teamsSearchDropdown"
        />
      </div>
      <div
        className="flex w-full  grid gap-4 md:gap-6 mt-4 grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3
       justify-center content-center "
      >
        {filteredTeams?.map((team: TeamType) => (
          <TeamCard
            team={team}
            compact={true}
            saveFunc={'save'}
            key={`TeamCard-${team.pk}`}
          />
        ))}
      </div>
    </div>
  );
});
