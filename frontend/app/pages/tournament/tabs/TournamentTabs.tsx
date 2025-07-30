// import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '~/components/ui/tabs';
import { GamesTab } from './GamesTab';
import { PlayersTab } from './PlayersTab';
import { TeamsTab } from './TeamsTab';

import { useEffect, useMemo } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useUserStore } from '~/store/userStore';

export default function TournamentTabs() {
  const users = useUserStore((state) => state.users); // Zustand setter

  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter
  useEffect(() => {
    getUsers();
  }, []);

  const tabClass =
    () => `rounded-full px-3 py-1 bg-gray-900 text-sm/6 font-semibold text-white
                        focus:not-data-focus:outline-none data-focus:outline data-focus:outline-white
                        data-hover:bg-cyan/5 data-selected:bg-purple-950 data-selected:data-hover:bg-cyan/10`;
  const tabPanelClass = () => `rounded-xl bg-base-300  p-3"`;
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
    <div className="@container flex w-full justify-center px-4 pt-2">
      <div className=" w-full ">
        <Tabs
          defaultValue="players"
          className="flex w-full justify-center gap-2 rounded-full p-1 align-middle"
        >
          <TabsList className="container content-center flex w-full justify-center gap-2 rounded-full p-1 align-middle mx-auto">
            <TabsTrigger value="players">Players ({playerCount})</TabsTrigger>
            <TabsTrigger value="teams">Teams ({teamCount})</TabsTrigger>
            <TabsTrigger value="games">Games ({gameCount})</TabsTrigger>
          </TabsList>
          <TabsContent value="players">
            {' '}
            <PlayersTab />
          </TabsContent>
          <TabsContent value="teams">
            {' '}
            <TeamsTab />
          </TabsContent>
          <TabsContent value="games">
            {' '}
            <GamesTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
