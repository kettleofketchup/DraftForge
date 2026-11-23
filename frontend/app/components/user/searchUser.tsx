import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import React from 'react';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import { userMatchesQuery } from '~/lib/userDisplayName';
import { useUserStore } from '~/store/userStore';

import { Input } from '~/components/ui/input';
import { getLogger } from '~/lib/logger';
const log = getLogger('searchUser');

interface Props {
  users: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  defaultValue?: string;
}

export const SearchUserDropdown: React.FC<Props> = ({
  users,
  query,
  setQuery,
  defaultValue = 'Search for users',
}) => {
  const user: UserType = useUserStore((state) => state.currentUser);

  const filteredUsers =
    query === ''
      ? users
      : users.filter((person) => userMatchesQuery(person, query));

  const handleSearchUserSelect = (userName: UserType | string | null) => {
    if (userName === null) {
      return;
    }
    let searchName: string;
    if (typeof userName === 'object') {
      log.debug(userName);
      searchName = userName?.username || userName?.nickname || '';
    } else {
      searchName = userName;
    }
    if (searchName === undefined || searchName === '') {
      return;
    }
    log.debug(`Selected user: ${searchName}`, searchName);

    const user: UserType | undefined = users.find(
      (user) =>
        user &&
        (user.username?.toLowerCase() === searchName?.toLowerCase() ||
          user.nickname?.toLowerCase() === searchName?.toLowerCase()),
    );
  };

  return (
    <div className="align-middle w-full">
      {users && (
        <Combobox value={query} onChange={handleSearchUserSelect}>
          <ComboboxInput
            id="search-user-combobox"
            as={Input}
            data-testid="userSearchInput"
            placeholder={defaultValue}
            onChange={(event) => setQuery(event.target.value)}
            onClick={(event) => log.debug(event.target)}
          />
          <ComboboxOptions className="border bg-popover shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
            {filteredUsers &&
            filteredUsers.length > 0 &&
            filteredUsers.length < 20 ? (
              filteredUsers.map((user) => (
                <ComboboxOption
                  key={user.pk}
                  value={user.username}
                  className={({ active }) =>
                    `cursor-pointer select-none p-2 ${
                      active ? 'bg-selection/30 text-selection-foreground' : ''
                    }`
                  }
                >
                  <div className="flex items-center gap-2">
                    <UserAvatar user={user} size="md" />
                    {/* eslint-disable-next-line draftforge/use-display-name -- labelled Username field shows the account handle */}
                    <span>Username: {user.username}</span>
                    {/* eslint-disable-next-line draftforge/use-display-name -- labelled Nick field shows the site nickname itself */}
                    Nick: {user.nickname && <span>{user.nickname}</span>}
                  </div>
                </ComboboxOption>
              ))
            ) : (
              <div className="p-2 text-sm text-muted-foreground">
                No users or too many users found
              </div>
            )}
          </ComboboxOptions>
        </Combobox>
      )}
    </div>
  );
};
