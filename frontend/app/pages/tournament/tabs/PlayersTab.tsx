import { memo, useState } from 'react';
import { toast } from 'sonner';
import { updateTournament } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import { ScrollArea, ScrollBar } from '~/components/ui/scroll-area';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UserCard } from '~/components/user/userCard';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';
import { hasErrors } from '../hasErrors';
import { AddPlayerModal } from './players/addPlayerModal';

const log = getLogger('PlayersTab');

export const PlayersTab: React.FC = memo(() => {
  const allUsers = useUserStore((state) => state.users);
  const [addPlayerQuery, setAddPlayerQuery] = useState('');
  const query = useUserStore((state) => state.userQuery);
  const setQuery = useUserStore((state) => state.setUserQuery);

  // Tournament data from new store (initialized by parent TournamentDetailPage)
  const tournamentId = useTournamentDataStore((state) => state.tournamentId);
  const tournamentUsers = useTournamentDataStore((state) => state.users);
  const loadAll = useTournamentDataStore((state) => state.loadAll);

  const addUserCallback = async (user: UserType) => {
    log.debug(`Adding user: ${user.username}`);
    // Check if user already in tournament
    const userIds = tournamentUsers.map((u) => u.pk);
    if (user.pk && userIds.includes(user.pk)) {
      log.error('User already exists in the tournament');
      return;
    }

    const thisUser = new User(user as UserType);
    if (!thisUser.pk) {
      thisUser.dbFetch();
    }
    if (userIds.includes(thisUser.pk)) {
      log.error('User in the tournament');
      return;
    }
    const updatedTournament = {
      user_ids: [...userIds, thisUser.pk],
    };

    if (tournamentId === null) {
      log.error('Tournament primary key is missing');
      return;
    }
    toast.promise(
      updateTournament(
        tournamentId,
        updatedTournament as Partial<TournamentType>,
      ),
      {
        loading: `Adding User ${thisUser.username}.`,
        success: () => {
          // Refresh tournament data from server
          loadAll();
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
  const filteredUsers =
    query === ''
      ? tournamentUsers
      : tournamentUsers.filter((person) => {
          const q = query.toLowerCase();
          return (
            person.username?.toLowerCase().includes(q) ||
            person.nickname?.toLowerCase().includes(q)
          );
        });

  const renderNoPlayers = () => {
    return (
      <div className="flex justify-center items-center h-screen">
        <div className="alert alert-info">
          <span>No teams available for this tournament.</span>
        </div>
      </div>
    );
  };
  const renderPlayers = () => {
    return (
      <ScrollArea className=" h-30%  mx-1 p-0 py-4">
        <div
          className="w-full content-center grid gap-2 mt-4 grid-cols-1
        sm:grid-cols-2
        lg:grid-cols-3
         xl:grid-cols-4
         2xl:grid-cols-5
         3xl:grid-cols-6 justify-center [content-visibility: auto] sm:gap-x-4 md:gap-x-6 lg:gap-x-4"
        >
          {filteredUsers?.map((user) => (
            <UserCard
              user={user as UserClassType}
              saveFunc={'save'}
              key={`UserCard-${user.pk}`}
              data-testid={`option-${user.username}`}
              compact={true}
              deleteButtonType="tournament"
            />
          ))}
        </div>
        <ScrollBar id="thisScrollBar" orientation="vertical" />
      </ScrollArea>
    );
  };

  const renderGames = () => {};
  return (
    <div className="py-5 px-3 mx-auto container">
      {hasErrors()}

      <div className="grid grid-cols-2 gap-5 items-start pt-5  ">
        <div className="flex self-center place-self-stretch">
          <SearchUserDropdown
            users={tournamentUsers}
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
            addedUsers={tournamentUsers.length > 0 ? tournamentUsers : undefined}
          />
        </div>
      </div>

      {tournamentUsers.length === 0
        ? renderNoPlayers()
        : renderPlayers()}
    </div>
  );
});
