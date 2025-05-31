import { useEffect, useState } from 'react';
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
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { User } from '~/components/user/user';

export function SearchUserDropdown() {
  const user: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter
  const users = useUserStore((state) => state.users); // Zustand setter

  const [createModal, setCreateModal] = useState<boolean>(false);

  const [query, setQuery] = useState('');
  const [selectedDiscordUser, setSelectedDiscordUser] = useState(
    new User({} as UserClassType),
  );
  const [searchedPerson, setSearchedPerson] = useState(
    new User({} as UserClassType),
  );

  const filteredUsers =
    query === ''
      ? users
      : users.filter((person) => {
          const q = query.toLowerCase();
          return (
            person.username?.toLowerCase().includes(q) ||
            person.nickname?.toLowerCase().includes(q)
          );
        });

  const handleSearchUserSelect = (user: User) => {
    setSearchedPerson(new User(user));
  };

  return (
    <div className="justify-self-top content-self-center align-middle ">
      {users && (
        <Combobox value={query} onChange={handleSearchUserSelect}>
          <ComboboxInput
            className="input input-bordered w-full"
            placeholder="Search DTX members..."
            onChange={(event) => setQuery(event.target.value)}
          />
          <ComboboxOptions className="border bg-base-100 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
            {filteredUsers &&
            filteredUsers.length > 0 &&
            filteredUsers.length < 20 ? (
              filteredUsers.map((user) => (
                <ComboboxOption
                  key={user.discordId}
                  value={user}
                  className={({ active }) =>
                    `cursor-pointer select-none p-2 ${
                      active ? 'bg-primary text-primary-content' : ''
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
}
