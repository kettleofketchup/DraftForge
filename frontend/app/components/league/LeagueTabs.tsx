import { Users } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { useLeagueStore } from '~/store/leagueStore';
import { InfoTab } from './tabs/InfoTab';
import { TournamentsTab } from './tabs/TournamentsTab';
import { MatchesTab } from './tabs/MatchesTab';
import { UsersTab } from './tabs/UsersTab';
import type { LeagueType } from './schemas';
import type { TournamentType } from '~/components/tournament/types';

interface Props {
  league: LeagueType;
  tournaments: TournamentType[];
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export const LeagueTabs: React.FC<Props> = ({
  league,
  tournaments,
  activeTab,
  onTabChange,
}) => {
  const leagueUsers = useLeagueStore((state) => state.leagueUsers);
  const leagueUsersLoading = useLeagueStore((state) => state.leagueUsersLoading);
  const leagueUsersLeagueId = useLeagueStore((state) => state.leagueUsersLeagueId);

  // Show "..." if loading or if we haven't fetched for this league yet
  const userCountDisplay = leagueUsersLoading || leagueUsersLeagueId !== league.pk
    ? '...'
    : leagueUsers.length;

  return (
    <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
      <TabsList className="hidden md:grid w-full grid-cols-4">
        <TabsTrigger value="info" data-testid="league-tab-info">
          Info
        </TabsTrigger>
        <TabsTrigger value="tournaments" data-testid="league-tab-tournaments">
          Tournaments ({tournaments.length})
        </TabsTrigger>
        <TabsTrigger value="users" data-testid="league-tab-users">
          <Users className="w-4 h-4 mr-2" />
          Users ({userCountDisplay})
        </TabsTrigger>
        <TabsTrigger value="matches" data-testid="league-tab-matches">
          Matches
        </TabsTrigger>
      </TabsList>

      <TabsContent value="info" className="mt-6">
        <InfoTab league={league} />
      </TabsContent>

      <TabsContent value="tournaments" className="mt-6">
        <TournamentsTab league={league} tournaments={tournaments} />
      </TabsContent>

      <TabsContent value="users" className="mt-6">
        {league.pk && <UsersTab leaguePk={league.pk} />}
      </TabsContent>

      <TabsContent value="matches" className="mt-6">
        {league.pk && <MatchesTab leaguePk={league.pk} />}
      </TabsContent>
    </Tabs>
  );
};
