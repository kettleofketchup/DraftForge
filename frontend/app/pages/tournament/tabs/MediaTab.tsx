import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import type { GameType, TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary

import { Fragment } from 'react';

export default function TeamsTab({
  tournament,
}: {
  tournament: TournamentType;
}) {
  if (!tournament || !tournament.teams || tournament.teams.length === 0) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="alert alert-info">
          <span>No teams available for this tournament.</span>
        </div>
      </div>
    );
  }
  return (
    <ul>
      {tournament.teams.map((game: GameType) => (
        <li
          key={game.pk}
          className="relative rounded-md p-3 text-sm/6 transition hover:bg-white/5"
        >
          <a href="#" className="font-semibold text-white">
            <span className="absolute inset-0" />
            {game.teams}
          </a>
          <ul className="flex gap-2 text-white/50" aria-hidden="true">
            <li>Played on: {game.date_played}</li>
            <li>Winning Team: {game.winning_team}</li>
            <li aria-hidden="true">&middot;</li>
          </ul>
        </li>
      ))}
    </ul>
  );
}
