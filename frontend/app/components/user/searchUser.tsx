import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import React, { useMemo } from 'react';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import {
  matchesUserQueryIn,
  useOrgNicknames,
  withOrgNickname,
} from '~/hooks/useOrgNicknames';
import { resolveDisplayName } from '~/lib/userDisplayName';

import { Input } from '~/components/ui/input';
import { getLogger } from '~/lib/logger';
const log = getLogger('searchUser');

interface Props {
  users: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  defaultValue?: string;
  orgId?: number | null;
  onSelect?: (user: UserType) => void;
}

export const SearchUserDropdown: React.FC<Props> = ({
  users,
  query,
  setQuery,
  defaultValue = 'Search for users',
  orgId = null,
  onSelect,
}) => {
  const nicknames = useOrgNicknames(
    useMemo(() => users.map((u) => u.pk), [users]),
    orgId,
  );

  const filteredUsers = useMemo(
    () =>
      query === ''
        ? users
        : users.filter((person) =>
            matchesUserQueryIn(person, query, orgId, nicknames),
          ),
    [users, query, orgId, nicknames],
  );

  const handleSearchUserSelect = (pk: number | null) => {
    if (pk === null) return;
    const selected = users.find((u) => u.pk === pk);
    if (!selected) return;
    log.debug('Selected user', { pk });
    onSelect?.(selected);
  };

  return (
    <div className="align-middle w-full">
      {users && (
        <Combobox<number | null> value={null} onChange={handleSearchUserSelect}>
          <ComboboxInput
            id="search-user-combobox"
            as={Input}
            data-testid="userSearchInput"
            placeholder={defaultValue}
            displayValue={() => query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <ComboboxOptions className="border bg-gray-900 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
            {filteredUsers &&
            filteredUsers.length > 0 &&
            filteredUsers.length < 20 ? (
              filteredUsers.map((user) => {
                const name = resolveDisplayName(
                  withOrgNickname(user, orgId, nicknames),
                  { orgId },
                );
                return (
                  <ComboboxOption
                    key={user.pk}
                    value={user.pk ?? null}
                    className={({ active }) =>
                      `cursor-pointer select-none p-2 ${
                        active ? 'bg-purple-900 text-primary-content' : ''
                      }`
                    }
                  >
                    <div className="flex items-center gap-2">
                      <UserAvatar user={user} size="md" />
                      <span>{name}</span>
                      {user.username && user.username !== name && (
                        <span className="text-sm text-muted-foreground">
                          @{user.username}
                        </span>
                      )}
                    </div>
                  </ComboboxOption>
                );
              })
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
