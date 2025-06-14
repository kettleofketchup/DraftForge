import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import type { TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary

import { Fragment } from 'react';
import GamesTab from './GamesTab';
import TeamsTab from './TeamsTab';
import PlayersTab from './PlayersTab';
import { useUserStore } from '~/store/userStore';

export default function TournamentTabs() {
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const tabClass =
    () => `rounded-full px-3 py-1 bg-gray-900 text-sm/6 font-semibold text-white
                        focus:not-data-focus:outline-none data-focus:outline data-focus:outline-white
                        data-hover:bg-cyan/5 data-selected:bg-purple-950 data-selected:data-hover:bg-cyan/10`;
  const tabPanelClass = () => `rounded-xl bg-base-300  p-3"`;

  return (
    <div className="flex w-full justify-center px-4 pt-2">
      <div className="w-full max-w-xxl">
        <TabGroup as={Fragment}>
          <TabList className="flex w-full justify-center gap-2 rounded-full p-1">
            <Tab className={tabClass()}>Games</Tab>
            <Tab className={tabClass()}>
              Teams ({tournament?.teams?.length})
            </Tab>
            <Tab className={tabClass()}>
              Players ({tournament?.users?.length})
            </Tab>
          </TabList>
          <TabPanels className="mt-3">
            <TabPanel className={tabPanelClass()}>
              <GamesTab  />
            </TabPanel>
            <TabPanel className={tabPanelClass()}>
              <TeamsTab  />
            </TabPanel>
            <TabPanel className={tabPanelClass()}>
              <PlayersTab />
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </div>
  );
}
