import React, { useState, useEffect, useCallback } from 'react';
import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import { get_dtx_members } from '../api/api';
import type { GuildMembers, GuildMember, UsersType } from '../user/types';
import { useUserStore } from '../../store/userStore';
import { Button } from '~/components/ui/button';
import { PlusCircleIcon } from 'lucide-react';

interface Props {
  onSelect: (user: GuildMember) => void;
  discrimUsers?: UsersType;
}

const DiscordUserDropdown: React.FC<Props> = ({ onSelect, discrimUsers }) => {
  const [query, setQuery] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const setDiscordUsers = useUserStore((state) => state.setDiscordUsers); // Zustand setter
  const discordUsers = useUserStore((state) => state.discordUsers); // Zustand setter
  const discordUser = useUserStore((state) => state.selectedDiscordUser); // Zustand setter

  const getDiscordUsers = useCallback(async () => {
    try {
      console.log('User fetching');
      get_dtx_members()
        .then((response) => {
          setDiscordUsers(response);
        })
        .catch((error) => {
          console.error('Error fetching user:', error);

          setDiscordUsers([] as GuildMembers);
        });
    } catch (err) {
      setDiscordUsers([] as GuildMembers);
    } finally {
    }
  }, []);
  useEffect(() => {
    getDiscordUsers();
  }, []);

  const filteredUsers =
    query === ''
      ? discordUsers
      : discordUsers.filter((person: GuildMember) => {
          return person.user.username
            .toLowerCase()
            .includes(query.toLowerCase());
        });

  // Remove users that have a discordId in discrimUsers
  const filteredWithoutDiscrim: GuildMember[] = discrimUsers
    ? filteredUsers.filter(
        (user: GuildMember) =>
          !discrimUsers.some((du) => du?.discordId === user.user.id),
      )
    : filteredUsers;

  const isUserAlreadyAdded = useCallback((user: GuildMember) => {
    return discrimUsers
      ? discrimUsers.some((du) => du?.discordId === user.user.id)
      : false;
  });

  const filteredUserComboOption = (user: GuildMember) => {
    return (
      <ComboboxOption
        key={user.user.id}
        value={user}
        disabled={isUserAlreadyAdded(user)}
        className={({ focus, disabled }) =>
          `cursor-pointer select-none p-2
       ${focus ? 'bg-purple-900 text-primary-content' : ''}
        ${disabled ? 'opacity-50  bg-grey-100 hover:bg-gray-500' : ''}`
        }
      >
        <div className="flex items-center gap-2">
          <img
            src={
              user.user.avatar
                ? `https://cdn.discordapp.com/avatars/${user.user.id}/${user.user.avatar}`
                : `https://ui-avatars.com/api/?rounded=True?name=${user.user.username}`
            }
            alt={user.user.username}
            className="w-8 h-8 rounded-full"
          />

          <span>{user.user.username}</span>

          {isUserAlreadyAdded(user) && (
            <span className="rounded-full text-center bg-gray-900 text-sm text-gray-200">
              Already Added
            </span>
          )}

          {/* TODO add a quickadd button*/}
          {/* {!isUserAlreadyAdded(user) && (
            <Button
              size="sm"
              className="justify-end btn bg-green-500 text-white hover:bg-green-600 disabled:bg-gray-300 disabled:text-gray-500"
            >
              <PlusCircleIcon color="green" />
              <p className="text-sm"> Quick Add</p>
            </Button>
          )} */}
        </div>
      </ComboboxOption>
    );
  };
  return (
    <div className="w-full max-w-md">
      <Combobox value={discordUser} onChange={onSelect}>
        <ComboboxInput
          className="input input-bordered w-full"
          placeholder="Search DTX members..."
          onChange={(event) => setQuery(event.target.value)}
          autoComplete="off"
        />
        <ComboboxOptions className="border bg-base-100 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
          {filteredUsers &&
          filteredUsers.length > 0 &&
          filteredUsers.length < 100 ? (
            filteredUsers.map((user) => {
              return filteredUserComboOption(user);
            })
          ) : (
            <div className="p-2 text-sm text-gray-500">
              {`${filteredUsers.length}`} users found. Results will show when
              less than 100 users are found.
            </div>
          )}
        </ComboboxOptions>
      </Combobox>
    </div>
  );
};

export default DiscordUserDropdown;
