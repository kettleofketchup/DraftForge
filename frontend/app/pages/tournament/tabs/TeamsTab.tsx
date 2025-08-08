import { memo, useEffect, useState } from 'react';
import { DraftModal } from '~/components/draft/draftModal';
import { SearchTeamsDropdown } from '~/components/team/searchTeams';
import { TeamCard } from '~/components/team/teamCard';
import { CaptainSelectionModal } from '~/components/tournament/captains/captainSelectionModal';

import type { UserType } from '~/components/user/types';
import { getLogger } from '~/lib/logger';
import { hasErrors } from '~/pages/tournament/hasErrors';
import { useUserStore } from '~/store/userStore';
import { RandomizeTeamsModal } from './teams/randomTeamsModal.tsx';
const log = getLogger('TeamsTab');
export const TeamsTab: React.FC = memo(() => {
  const tournament = useUserStore((state) => state.tournament);

  const allUsers = useUserStore((state) => state.users); // Zustand setter

  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  ); // Zustand setter
  const [query, setQuery] = useState('');

  useEffect(() => {
    getCurrentTournament();
  }, [allUsers, tournament.users?.length]);

  const filteredTeams =
    query === ''
      ? tournament.teams
      : tournament.teams
          ?.filter((team) => {
            const q = query.toLowerCase();

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
          .sort((a, b) => a.name.localeCompare(b.name));

  useEffect(() => {
    log.debug('Tournament users:', tournament.users);
  }, [tournament.users]);

  useEffect(() => {
    log.debug('Filtered teams:', filteredTeams);
  }, [tournament.teams?.length, filteredTeams?.length]);

  const teamButtonsView = () => {
    return (
      <div
        className="flex flex-col justify-center items-center  gap-y-4 w-full flex-grow sm:flex-row
       sm:gap-y-2 sm:gap-x-8 sm:p-4 sm:pt-2 sm:pb-6 "
      >
        <RandomizeTeamsModal users={tournament?.users || []} teamSize={5} />
        <CaptainSelectionModal />
        <DraftModal />
      </div>
    );
  };

  return (
    <div className="p-5 container bg-base-300 rounded-lg shadow-lg hover:bg-base-400 transition-shadow duration-300 ease-in-out">
      {hasErrors()}
      {teamButtonsView()}
      <div className="w-full">
        <SearchTeamsDropdown
          teams={tournament?.teams || []}
          query={query}
          setQuery={setQuery}
        />
      </div>
      <div className="w-full content-center grid gap-2 mt-4 grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 justify-center ">
        {filteredTeams?.map((team) => (
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
