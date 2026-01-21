// import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { GamesTab } from './GamesTab';
import { PlayersTab } from './PlayersTab';
import { TeamsTab } from './TeamsTab';

import { useEffect, useMemo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useTournamentStore } from '~/store/tournamentStore';
import { useUserStore } from '~/store/userStore';

export default function TournamentTabs() {
  const users = useUserStore((state) => state.users); // Zustand setter
  const activeTab = useTournamentStore((state) => state.activeTab);
  const setActiveTab = useTournamentStore((state) => state.setActiveTab);

  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter
  useEffect(() => {
    getUsers();
  }, []);

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
      onValueChange={setActiveTab}
      className="flex justify-center rounded-full  align-middle gap-4 sm:-p1 sm:gap-2 sm:w-full"
    >
      <TabsList
        className="container content-center flex w-full justify-center gap-2 rounded-full "
        data-testid="tournamentTabsList"
      >
        <TabsTrigger
          className="w-full active:p-1"
          value="players"
          data-testid="playersTab"
        >
          Players ({playerCount})
        </TabsTrigger>
        <TabsTrigger className="w-full" value="teams" data-testid="teamsTab">
          Teams ({teamCount})
        </TabsTrigger>
        <TabsTrigger value="bracket" data-testid="bracketTab">
          Bracket ({gameCount})
        </TabsTrigger>
      </TabsList>
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
