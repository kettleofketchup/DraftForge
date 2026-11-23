import { Suspense, useState } from 'react';
import { useNavigate } from 'react-router';
import type { TournamentType } from '~/components/tournament/types';
import { Alert, AlertDescription } from '~/components/ui/alert';
import { UserSearchInput } from '~/components/user/search';
import type { User } from '~/components/user/user';
import { UserCard } from '~/components/user/userCard';
import { useFilteredUsers } from '~/hooks/useUserSearch';
export default function PlayersTab({
  tournament,
}: {
  tournament: TournamentType;
}) {
  const [query, setQuery] = useState('');

  const filteredUsers = useFilteredUsers(tournament?.users, query);
  if (!tournament || !tournament.users || tournament.users.length === 0) {
    return (
      <div className="flex justify-center items-center h-screen">
        <Alert className="w-auto">
          <AlertDescription>
            No teams available for this tournament.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const navigate = useNavigate();

  return (
    <Suspense fallback={<div>Loading...</div>}>
      <UserSearchInput
        value={query}
        onChange={setQuery}
        placeholder="Search for users"
        data-testid="userSearchInput"
      />

      <div className="grid gap-2 mt-4 grid-cols-2 xl:grid-cols-3 ">
        {filteredUsers?.map((user) => (
          <UserCard user={user as User} compact={true} />
        ))}
      </div>
    </Suspense>
  );
}
