import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import type { TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary

import { Fragment } from 'react';
import GamesTab from './GamesTab';
import TeamsTab from './TeamsTab';
import PlayersTab from './PlayersTab';

export default function TournamentTabs({
  tournament,
}: {
  tournament: TournamentType;
}) {
  const tabClass =
    () => `rounded-full px-3 py-1 text-sm/6 font-semibold text-white
                        focus:not-data-focus:outline-none data-focus:outline data-focus:outline-white
                        data-hover:bg-white/5 data-selected:bg-white/10 data-selected:data-hover:bg-white/10`;
  const tabPanelClass = () => `rounded-xl bg-base-300  p-3"`;

  return (
    <div className="flex w-full justify-center px-4 pt-2">
      <div className="w-full max-w-xxl">
        <TabGroup as={Fragment}>
          <TabList className="flex w-full justify-center gap-2 rounded-full p-1">
            <Tab className={tabClass()}>Games</Tab>
            <Tab className={tabClass()}>Teams</Tab>
            <Tab className={tabClass()}>Players</Tab>
          </TabList>
          <TabPanels className="mt-3">
            <TabPanel className={tabPanelClass()}>
              <GamesTab tournament={tournament} />{' '}
            </TabPanel>
            <TabPanel className={tabPanelClass()}>
              <TeamsTab tournament={tournament} />{' '}
            </TabPanel>
            <TabPanel className={tabPanelClass()}>
              <PlayersTab tournament={tournament} />{' '}
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </div>
  );
}
