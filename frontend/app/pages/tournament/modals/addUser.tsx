import { Suspense, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { User } from '~/components/user/user';
import { UserCard } from '~/components/user/userCard';
export default function PlayersTab({
  tournament,
}: {
  tournament: TournamentType;
}) {
  const [query, setQuery] = useState('');

  const filteredUsers =
    query === ''
      ? tournament.users
      : tournament.users?.filter((person) => {
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
    <Suspense fallback={<div>Loading...</div>}>
      <SearchUserDropdown
        users={tournament.users}
        query={query}
        setQuery={setQuery}
      />

      <div className="grid gap-2 mt-4 grid-cols-2 xl:grid-cols-3 ">
        {filteredUsers?.map((user) => (
          <UserCard user={user as User} compact={true} />
        ))}
      </div>
    </Suspense>
  );
}
