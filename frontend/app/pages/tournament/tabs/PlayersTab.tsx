import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import type { GameType, TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary

import { Fragment, useState } from 'react';
import type { UserType } from '~/components/user/types';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { UsersDropdown } from '~/components/user/UsersDropdown';
import { SearchUserDropdown } from '~/components/user/searchUser';
import { useNavigate } from 'react-router-dom';
import { UserCard } from '~/components/user/userCard';
import type { User } from '~/components/user/user';

export default function PlayersTab({
  tournament,
}: {
  tournament: TournamentType;
}) {
  const [query, setQuery] = useState('');

  const filteredUsers =
    query === ''
      ? tournament.users
      : tournament.users.filter((person) => {
          const q = query.toLowerCase();
          return (
            person.username?.toLowerCase().includes(q) ||
            person.nickname?.toLowerCase().includes(q)
          );
        });
  if (!tournament || !tournament.users || tournament.users.length === 0) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="alert alert-info">
          <span>No teams available for this tournament.</span>
        </div>
      </div>
    );
  }

  let navigate = useNavigate();

  return (
    <>
      <SearchUserDropdown users={tournament.users} query={query} setQuery={setQuery} className="" />
      <div className="grid gap-2 mt-4 grid-cols-2 xl:grid-cols-3 ">
        {filteredUsers?.map((user) => (
          <UserCard user={user as User} compact={true} />
        ))}
      </div>
    </>
  );
}
