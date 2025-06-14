import React, { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  GuildMember,
  UserType,
  UserClassType,
} from '~/components/user/types';
import { UserCard } from '~/components/user/userCard';
import axios from '~/components/api/axios';
import { useUserStore } from '~/store/userStore';
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import Footer from '~/components/footer';
import { User } from '~/components/user/user';
interface Props {
  teams: TeamType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
}

export const SearchTeamsDropdown: React.FC<Props> = ({
  teams,
  query,
  setQuery,
}) => {
  const user: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter

  const [selectedDiscordUser, setSelectedDiscordUser] = useState(
    new User({} as UserClassType),
  );
  const [searchedPerson, setSearchedPerson] = useState(
    new User({} as UserClassType),
  );
  const filterTeams =
    query === ''
      ? users
      : users.filter((person) => {
          const q = query.toLowerCase();
          return (
            person.username?.toLowerCase().includes(q) ||
            person.nickname?.toLowerCase().includes(q)
          );
        });

  const handleSearchUserSelect = (userName: UserType | string) => {
    if (typeof userName === 'object') {
      userName = userName.username || userName.nickname || '';
    }
    if (userName === undefined || userName === '') {
      setSearchedPerson(new User({} as UserClassType));
      return;
    }
    console.log(`Selected user: ${userName}`, userName);

    const user: UserType | undefined = users.find(
      (user) =>
        user &&
        (user.username?.toLowerCase() === userName?.toLowerCase() ||
          user.nickname?.toLowerCase() === userName?.toLowerCase()),
    );

    setSearchedPerson(new User(user as UserClassType));
  };

  return (
    <div className="justify-self-top content-self-center align-middle ">
      {users && (
        <Combobox value={query} onChange={handleSearchUserSelect}>
          <ComboboxInput
            className="input input-bordered w-full"
            placeholder="Search DTX members..."
            onChange={(event) => setQuery(event.target.value)}
            onClick={(event) => console.log(event.target)}
          />
          <ComboboxOptions className="border bg-gray-900 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
            {filterTeams &&
            filterTeams.length > 0 &&
            filterTeams.length < 20 ? (
              filterTeams.map((user) => (
                <ComboboxOption
                  key={user.pk}
                  value={user.username}
                  className={({ active }) =>
                    `cursor-pointer select-none p-2 ${
                      active ? 'bg-purple-100 text-primary-content' : ''
                    }`
                  }
                >
                  <div className="flex items-center gap-2">
                    <img
                      src={
                        user.avatar
                          ? `https://cdn.discordapp.com/avatars/${user.discordId}/${user.avatar}`
                          : 'https://via.placeholder.com/32'
                      }
                      alt={user.username}
                      className="w-8 h-8 rounded-full"
                    />
                    <span>{user.username}</span>
                  </div>
                </ComboboxOption>
              ))
            ) : (
              <div className="p-2 text-sm text-gray-500">
                No users or too many users found
              </div>
            )}
          </ComboboxOptions>
        </Combobox>
      )}
    </div>
  );
};
