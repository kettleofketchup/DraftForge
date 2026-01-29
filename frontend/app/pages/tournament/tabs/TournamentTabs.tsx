import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import { GamesTab } from './GamesTab';
import { PlayersTab } from './PlayersTab';
import { TeamsTab } from './TeamsTab';

import { useCallback, useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useShallow } from 'zustand/react/shallow';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';

export default function TournamentTabs() {
  const { pk } = useParams<{ pk: string }>();
  const navigate = useNavigate();
  const users = useUserStore((state) => state.users);
  const activeTab = useTournamentStore((state) => state.activeTab);

  const handleTabChange = useCallback((tab: string) => {
    // Navigate using URL path, which will update the store via TournamentDetailPage
    navigate(`/tournament/${pk}/${tab}`, { replace: true });
  }, [pk, navigate]);


  const tournament = useUserStore(useShallow((state) => state.tournament)); // Zustand setter

  const playerCount = useMemo(() => {
    // Assuming you have a way to get the players array, e.g., from props or context
    if (!tournament || !tournament.users) {
      return 0; // Return 0 if tournament or users is not defined
    }
    return tournament.users.length;
  }, [tournament.users]);

  const teamCount = useMemo(() => {
    // Assuming you have a way to get the players array, e.g., from props or context
    if (!tournament || !tournament.teams) {
      return 0; // Return 0 if tournament or users is not defined
    }
    return tournament.teams.length;
  }, [tournament.teams]);

  const gameCount = useMemo(() => {
    // Assuming you have a way to get the players array, e.g., from props or context
    if (!tournament || !tournament.games) {
      return 0; // Return 0 if tournament or users is not defined
    }
    return tournament.games.length;
  }, [tournament.games]);
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
