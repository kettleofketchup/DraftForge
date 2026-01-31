import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UserAvatar } from '~/components/user/UserAvatar';

import { useState, type FormEvent } from 'react';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('addPlayerDropdown');
interface Props {
  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
}

export const AddPlayerDropdown: React.FC<Props> = ({
  addedUsers,
  query,
  setQuery,
  addPlayerCallback,
  removePlayerCallback,
}) => {
  const users = useUserStore((state) => state.users); // Zustand setter
  const [searchedPerson, setSearchedPerson] = useState(
    new User({} as UserClassType),
  );

  const filteredUsers =
    query === ''
      ? users.filter(
          (person) => !addedUsers?.some((added) => added?.pk === person?.pk),
        )
      : users.filter(
          (person) =>
            !addedUsers?.some((added) => added?.pk === person?.pk) &&
            (person?.username?.toLowerCase().includes(query.toLowerCase()) ||
              person?.nickname?.toLowerCase().includes(query.toLowerCase())),
        );

  const handleSearchUserSelect = async (userName: UserType | string | null) => {
    if (!userName || userName === undefined || userName === '') {
      log.debug(userName);

      setSearchedPerson(new User({} as UserClassType));
      return;
    }

    if (typeof userName === 'object') {
      log.debug(userName);

      userName = userName.username || userName.nickname || '';
    }
    if (!userName || userName === undefined || userName === '') {
      log.debug('No user selected, resetting searched person');
      setSearchedPerson(new User({} as UserClassType));
      return;
    }
    log.debug(`Selected user: ${userName}`, userName);

    const user: UserType | undefined = users.find(
      (user) =>
        user &&
        (user?.username?.toLowerCase() === userName?.toLowerCase() ||
          user?.nickname?.toLowerCase() === userName?.toLowerCase()),
    );

    if (user === undefined) {
      log.debug('User not found, resetting searched person');
      setSearchedPerson(new User({} as UserClassType));
      return;
    }
    setSearchedPerson(new User(user as UserClassType));
    if (addPlayerCallback !== undefined) {
      log.debug('Adding player callback with user:', user);
      await addPlayerCallback(user as UserType);
      setQuery(''); // Reset query after selection
    }
  };

  return (
    <div className="justify-self-top content-self-center align-middle ">
      {users && (
        <Combobox value={query} onChange={handleSearchUserSelect}>
          <ComboboxInput
            className="input input-bordered w-full"
            placeholder="Search DTX members..."
            onChange={(event) => setQuery(event.target.value)}
            data-testid="playerSearchInput"
            aria-label="Search for players to add"
          />
          <ComboboxOptions className="border bg-base-500 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
            {filteredUsers &&
            filteredUsers.length > 0 &&
            filteredUsers.length < 20 ? (
              filteredUsers.map((user) => (
                <ComboboxOption
                  key={user?.pk}
                  value={user?.username}
                  className={({ active }) =>
                    `cursor-pointer select-none p-2 ${
                      active ? 'bg-purple-900 text-primary-content' : ''
                    }`
                  }
                  data-testid={`playerOption-${user?.username}`}
                >
                  <div className="flex items-center gap-2">
                    <UserAvatar user={user} size="md" />
                    <span>
                      {user?.username}{' '}
                      {user?.nickname && (
                        <span className="text-sm text-gray-500">
                          ({user?.nickname})
                        </span>
                      )}
                    </span>

                    <div className="flex-1" />
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
