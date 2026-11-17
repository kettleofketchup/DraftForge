import {
  Combobox,
  ComboboxInput,
  ComboboxOption,
  ComboboxOptions,
} from '@headlessui/react';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';

import { useMemo, type FormEvent } from 'react';
import { Input } from '~/components/ui/input';
import {
  matchesUserQueryIn,
  useOrgNicknames,
  withOrgNickname,
} from '~/hooks/useOrgNicknames';
import { getLogger } from '~/lib/logger';
import { resolveDisplayName } from '~/lib/userDisplayName';

const log = getLogger('addPlayerDropdown');
interface Props {
  users: UserType[];
  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
  placeholder?: string;
  orgId?: number | null;
}

export const AddPlayerDropdown: React.FC<Props> = ({
  users,
  addedUsers,
  query,
  setQuery,
  addPlayerCallback,
  placeholder = 'Search organization members...',
  orgId = null,
}) => {
  const nicknames = useOrgNicknames(
    useMemo(() => users.map((u) => u?.pk), [users]),
    orgId,
  );

  const filteredUsers = useMemo(
    () =>
      users.filter(
        (person) =>
          !addedUsers?.some((added) => added?.pk === person?.pk) &&
          (query === '' || matchesUserQueryIn(person, query, orgId, nicknames)),
      ),
    [users, addedUsers, query, orgId, nicknames],
  );

  const handleSearchUserSelect = async (pk: number | null) => {
    const user = pk === null ? undefined : users.find((u) => u?.pk === pk);
    if (user === undefined) {
      log.debug('No user selected');
      return;
    }
    if (addPlayerCallback !== undefined) {
      log.debug('Adding player', { pk });
      await addPlayerCallback(user);
      setQuery('');
    }
  };

  return (
    <div className="align-middle">
      {users && (
        <Combobox<number | null> value={null} onChange={handleSearchUserSelect}>
          <ComboboxInput
            as={Input}
            placeholder={placeholder}
            displayValue={() => query}
            onChange={(event) => setQuery(event.target.value)}
            data-testid="playerSearchInput"
            aria-label="Search for players to add"
          />
          <ComboboxOptions className="border bg-base-500 shadow-lg rounded-lg max-h-60 overflow-y-auto mt-2">
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
                    key={user?.pk}
                    value={user?.pk ?? null}
                    className={({ active }) =>
                      `cursor-pointer select-none p-2 ${
                        active ? 'bg-purple-900 text-primary-content' : ''
                      }`
                    }
                    data-testid={`playerOption-${user?.username}`}
                  >
                    <div className="flex items-center gap-2">
                      <UserAvatar user={user} size="md" />
                      <span>{name}</span>
                      {user?.username && user.username !== name && (
                        <span className="text-sm text-gray-500">
                          @{user.username}
                        </span>
                      )}
                      <div className="flex-1" />
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
