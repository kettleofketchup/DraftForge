import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import { GamesTab } from './GamesTab';
import { PlayersTab } from './PlayersTab';
import { TeamsTab } from './TeamsTab';

import { useCallback, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

export default function TournamentTabs() {
  const { pk } = useParams<{ pk: string }>();
  const navigate = useNavigate();
  const activeTab = useTournamentStore((state) => state.activeTab);

  // Tournament data from new store (initialized by parent TournamentDetailPage)
  const tournamentUsers = useTournamentDataStore((state) => state.users);
  const tournamentTeams = useTournamentDataStore((state) => state.teams);
  const tournamentGames = useTournamentDataStore((state) => state.games);

  const handleTabChange = useCallback((tab: string) => {
    // Navigate using URL path, which will update the store via TournamentDetailPage
    navigate(`/tournament/${pk}/${tab}`, { replace: true });
  }, [pk, navigate]);

  // Load all users for the add player modal
  const getUsers = useUserStore((state) => state.getUsers);
  useEffect(() => {
    getUsers();
  }, []);

  const playerCount = tournamentUsers.length;
  const teamCount = tournamentTeams.length;
  const gameCount = tournamentGames.length;
  return (
    <Tabs
      value={activeTab}
      onValueChange={handleTabChange}
      className="w-full"
    >
      <ScrollArea className="w-full whitespace-nowrap pb-2">
        <TabsList
          className="inline-flex w-full min-w-max gap-1 sm:gap-2 p-1"
          data-testid="tournamentTabsList"
        >
          <TabsTrigger
            className="flex-1 min-w-[100px] min-h-11"
            value="players"
            data-testid="playersTab"
          >
            Players ({playerCount})
          </TabsTrigger>
          <TabsTrigger
            className="flex-1 min-w-[100px] min-h-11"
            value="teams"
            data-testid="teamsTab"
          >
            Teams ({teamCount})
          </TabsTrigger>
          <TabsTrigger
            className="flex-1 min-w-[100px] min-h-11"
            value="bracket"
            data-testid="bracketTab"
          >
            Bracket ({gameCount})
          </TabsTrigger>
        </TabsList>
        <ScrollBar orientation="horizontal" className="h-1.5" />
      </ScrollArea>
      <TabsContent value="players" data-testid="playersTabContent">
        {' '}
        <PlayersTab />
      </TabsContent>
      <TabsContent value="teams" data-testid="teamsTabContent">
        {' '}
        <TeamsTab />
      </TabsContent>
      <TabsContent value="bracket" data-testid="bracketTabContent">
        {' '}
        <GamesTab />
      </TabsContent>
    </Tabs>
  );
}
