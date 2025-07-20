import { memo, useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import { updateTournament } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import { ScrollArea } from '~/components/ui/scroll-area';
import { SearchUserDropdown } from '~/components/user/searchUser';
import type { UserClassType, UserType } from '~/components/user/types';
import { User } from '~/components/user/user';
import { UserCard } from '~/components/user/userCard';
import { useUserStore } from '~/store/userStore';
import { hasErrors } from '../hasErrors';
import { AddPlayerModal } from './players/addPlayerModal';

export const PlayersTab: React.FC = memo(() => {
  const allUsers = useUserStore((state) => state.users); // Zustand setter
  const [addPlayerQuery, setAddPlayerQuery] = useState('');
  const addUserQuery = useUserStore((state) => state.addUserQuery);
  const setAddUserQuery = useUserStore((state) => state.setAddUserQuery); // Zustand setter
  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament); // Zustand settera
  const query = useUserStore((state) => state.userQuery);
  const setQuery = useUserStore((state) => state.setUserQuery); // Zustand setter
  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  ); // Zustand setter

  const removeUser = async (e: FormEvent, user: UserType) => {
    e.preventDefault();
    e.stopPropagation();
    // Implement the logic to remove the user from the tournament
    console.log(`Removing user: ${user.username}`);
    const updatedUsers = tournament.users
      ?.filter((u) => u.username !== user.username)
      .map((u) => u.pk);

    console.log('Updated users:', updatedUsers);

    const updatedTournament = {
      user_ids: updatedUsers,
    };
    if (tournament.pk === undefined) {
      console.error('Tournament primary key is missing');
      return;
    }

    toast.promise(updateTournament(tournament.pk, updatedTournament), {
      loading: `Creating User ${user.username}.`,
      success: (data) => {
        tournament.users = tournament.users?.filter(
          (u) => u.username !== user.username,
        );
        //Trigger rerender of tournament users
        setTournament(data);
        return `${user.username} has been removed`;
      },
      error: (err: any) => {
        console.error('Failed to update tournament', err);
        return `${user.username} has been removed`;
      },
    });
    await getCurrentTournament();

    setQuery(''); // Reset query after adding user
  };

  const addUserCallback = async (user: UserType) => {
    console.log(`Adding user: ${user.username}`);
    // Implement the logic to remove the user from the tournament
    if (user.pk && tournament.user_ids && user.pk in tournament.user_ids) {
      console.error('User already exists in the tournament');
      return;
    }
    const updatedUsers = tournament.users?.map((u) => u.pk);

    const thisUser = new User(user as UserType);
    if (!thisUser.pk) {
      thisUser.dbFetch();
    }
    if (updatedUsers?.includes(thisUser.pk)) {
      console.log();
      console.error('User in the  tournament');
      return;
    }
    const updatedTournament = {
      user_ids: [...(updatedUsers || []), thisUser.pk],
    };

    if (tournament.pk === undefined) {
      console.error('Tournament primary key is missing');
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
          console.error('Failed to update tournament', err);
          return `${thisUser.username} could not be added`;
        },
      },
    );

    setQuery(''); // Reset query after adding user
  };
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
      <ScrollArea className=" h-30%  [content-visibility: auto] whitespace-nowrap p-5">
        <div className="w-full content-center grid gap-2 mt-4 grid-cols-2 xl:grid-cols-3 justify-center [content-visibility: auto]">
          {filteredUsers?.map((user) => (
            <UserCard
              user={user as UserClassType}
              saveFunc={'save'}
              key={`UserCard-${user.pk}`}
              compact={true}
              deleteButtonType="tournament"
            />
          ))}
        </div>
      </ScrollArea>
    );
  };

  return (
    <div className="p-5 container bg-base-300 rounded-lg shadow-lg hover:bg-base-400 transition-shadow duration-300 ease-in-out">
      {hasErrors()}

      <div className="grid grid-cols-2 gap-5 items-start pt-5 ">
        <div className="flex self-center place-self-stretch">
          <SearchUserDropdown
            users={tournament.users}
            query={query}
            setQuery={setQuery}
          />
        </div>
        <div className="flex pr-5 place-self-end">
          <AddPlayerModal
            users={allUsers}
            query={addPlayerQuery}
            setQuery={setAddPlayerQuery}
            addPlayerCallback={addUserCallback}
            addedUsers={tournament.users}
          />
        </div>
      </div>

      {!tournament || !tournament.users || tournament.users.length === 0
        ? renderNoPlayers()
        : renderPlayers()}
    </div>
  );
});
