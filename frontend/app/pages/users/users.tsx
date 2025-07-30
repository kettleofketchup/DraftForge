import { useEffect, useState } from 'react';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UserCard } from '~/components/user/userCard';
import { UserCreateModal } from '~/components/user/userCard/createModal';
import { useUserStore } from '~/store/userStore';

// Animation for each card
const card = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0 },
};
export function UsersPage() {
  const user: UserType = useUserStore((state) => state.currentUser); // Zustand setter
  const getUsers = useUserStore((state) => state.getUsers); // Zustand setter
  const users = useUserStore((state) => state.users); // Zustand setter
  const getDiscordUsers = useUserStore((state) => state.getDiscordUsers); // Zustand setter
  const discordUsers = useUserStore((state) => state.discordUsers); // Zustand setter

  const [query, setQuery] = useState('');
  const [createModalQuery, setCreateModalQuery] = useState('');

  const [selectedDiscordUser, setSelectedDiscordUser] = useState(
    new User({} as UserClassType),
  );
  const [searchedPerson, setSearchedPerson] = useState(
    new User({} as UserClassType),
  );
  useEffect(() => {
    if (!discordUsers || discordUsers.length === 0) {
      getDiscordUsers();
    }

    getUsers();
  }, []);
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

  return (
    <>
      <div className="flex flex-col items-start p-4 h-full  ">
        <div
          className="grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
       grid-cols-4
         w-full "
        >
          <div className="flex col-span-2 w-full content-center">
            <SearchUserDropdown
              users={users}
              query={query}
              setQuery={setQuery}
            />
          </div>
          <div className="flex col-start-4 align-end content-end justify-end">
            <UserCreateModal
              query={createModalQuery}
              setQuery={setCreateModalQuery}
            />
          </div>
        </div>
        <div
          className="grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
         grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 2xl:grid-cols-4
         mb-0 mt-0 p-0 bg-base-900  w-full gap-2 md:gap-4 lg:gap-6"
        >
          {filteredUsers?.map((u: UserType) => (
            <UserCard
              user={u as UserClassType}
              saveFunc={'save'}
              key={`UserCard-${u.pk}`}
              deleteButtonType="normal"
            />
          ))}
        </div>
      </div>
    </>
  );
}
