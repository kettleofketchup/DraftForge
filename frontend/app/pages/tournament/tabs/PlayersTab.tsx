import { memo, useState } from 'react';
import { toast } from 'sonner';
import { updateTournament } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UserList } from '~/components/user';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { hasErrors } from '../hasErrors';
import { AddPlayerModal } from './players/addPlayerModal';

const log = getLogger('PlayersTab');

export const PlayersTab: React.FC = memo(() => {
  const allUsers = useUserStore((state) => state.users);
  const [addPlayerQuery, setAddPlayerQuery] = useState('');
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament);
  const query = useUserStore((state) => state.userQuery);
  const setQuery = useUserStore((state) => state.setUserQuery);

  // Get the organization ID from the tournament
  const orgId = tournament?.organization_pk ?? undefined;
  const addUserCallback = async (user: UserType) => {
    log.debug(`Adding user: ${user.username}`);
    // Implement the logic to remove the user from the tournament
    if (user.pk && tournament.user_ids && user.pk in tournament.user_ids) {
      log.error('User already exists in the tournament');
      return;
    }
    const updatedUsers = tournament.users?.map((u) => u.pk);

    const thisUser = new User(user as UserType);
    if (!thisUser.pk) {
      thisUser.dbFetch();
    }
    if (updatedUsers?.includes(thisUser.pk)) {
      log.error('User in the  tournament');
      return;
    }
    const updatedTournament = {
      user_ids: [...(updatedUsers || []), thisUser.pk],
    };

    if (tournament.pk === undefined || tournament.pk === null) {
      log.error('Tournament primary key is missing');
      return;
    }
    toast.promise(
      updateTournament(
        tournament.pk,
        updatedTournament as Partial<TournamentType>,
      ),
      {
        loading: `Adding User ${thisUser.username}.`,
        success: (data) => {
          setTournament(data);
          return `${thisUser.username} has been added`;
        },
        error: (err: any) => {
          log.error('Failed to update tournament', err);
          return `${thisUser.username} could not be added`;
        },
      },
    );

    setQuery(''); // Reset query after adding user
  };
  // Grid columns for tournament players
  const gridCols = 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5';
  return (
    <div className="py-5 px-3 mx-auto container">
      {hasErrors()}

      <div className="grid grid-cols-2 gap-5 items-start pt-5  ">
        <div className="flex self-center place-self-stretch">
          <SearchUserDropdown
            users={tournament?.users || []}
            query={query}
            setQuery={(val) => typeof val === 'string' ? setQuery(val) : setQuery(val(''))}
            data-testid="playerSearchDropdown"
          />
        </div>
        <div className="flex px-5 place-self-end">
          <AddPlayerModal
            users={allUsers}
            query={addPlayerQuery}
            setQuery={setAddPlayerQuery}
            addPlayerCallback={addUserCallback}
            addedUsers={tournament.users ?? undefined}
            orgId={orgId}
          />
        </div>
      </div>

      <div className="mt-4">
        <UserList
          users={tournament?.users ?? []}
          searchQuery={query}
          compact={true}
          deleteButtonType="tournament"
          gridCols={gridCols}
          emptyMessage="No players in this tournament"
        />
      </div>
    </div>
  );
});
