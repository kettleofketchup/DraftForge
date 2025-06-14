import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import { Button } from '~/components/ui/button';
import type { GameType, TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import { Plus } from 'lucide-react';
import {
  Fragment,
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from 'react';
import type { UserClassType, UserType } from '~/components/user/types';
import DiscordUserDropdown from '~/components/user/DiscordUserDropdown';
import { UsersDropdown } from '~/components/user/UsersDropdown';
import { SearchUserDropdown } from '~/components/user/searchUser';
import { useNavigate } from 'react-router-dom';
import { UserCard } from '~/components/user/userCard';
import { User } from '~/components/user/user';
import { updateTournament } from '~/components/api/api';
import axios from '~/components/api/axios';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import { useUserStore } from '~/store/userStore';
import { Label } from '~/components/ui/label';
import { Input } from '~/components/ui/input';
import { LucidePlus } from 'lucide-react';
import { AddPlayerModal } from './addPlayer/addPlayerModal';
import { toast } from 'sonner';
import TournamentDetailPage from '../TournamentDetailPage';
import { hasErrors } from '../hasErrors';
import { Tournament } from '~/components/tournament/tournament';
export default function PlayersTab() {
  const allUsers = useUserStore((state) => state.users); // Zustand setter

  const tournament = useUserStore((state) => state.tournament);
  const setTournament = useUserStore((state) => state.setTournament); // Zustand settera
  const [tournamentUsers, setTournamentUsers] = useState([] as UserType[]);
  const [query, setQuery] = useState('');
  const [addUserQuery, setAddUserQuery] = useState('');
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
          tournament.users?.push(thisUser);
          //Trigger rerender of tournament users
          setTournamentUsers(tournament.users as UserType[]);
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

  useEffect(() => {
    console.log('Tournament users:', tournament.users);
    getCurrentTournament();
  }, [tournament.users]);
  useEffect(() => {
    console.log('TournamentPageUsers: updated users');
  }, [allUsers]);

  if (!tournament || !tournament.users || tournament.users.length === 0) {
    return (
      <>
        <div className="flex flex-col items-start p-4 h-full">
          <div className="self-end p-5 pb-2 pt-2">
            <AddPlayerModal
              users={allUsers}
              query={query}
              setQuery={setQuery}
              addPlayerCallback={addUserCallback}
            />
          </div>
        </div>
        <div className="flex justify-center items-center h-screen">
          <div className="alert alert-info">
            <span>No teams available for this tournament.</span>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="flex flex-col items-start p-4 h-full">
        {hasErrors(tournament.users)}

        <div className="self-end p-5 pb-2 pt-2">
          {
            <AddPlayerModal
              users={allUsers}
              query={query}
              setQuery={setQuery}
              addPlayerCallback={addUserCallback}
              addedUsers={tournament.users}
            />
          }
        </div>
        <div className="w-full">
          <SearchUserDropdown
            users={tournament.users}
            query={query}
            setQuery={setQuery}
            className="w-full"
          />
        </div>
        <div className="w-full content-center grid gap-2 mt-4 grid-cols-2 xl:grid-cols-3 justify-center ">
          {filteredUsers?.map((user) => (
            <UserCard
              user={user as UserClassType}
              saveFunc={'save'}
              key={`UserCard-${user.pk}`}
              removeCallBack={removeUser}
              removeToolTip={'Delete from tournament'}
              compact={true}
            />
          ))}
        </div>
      </div>
    </>
  );
}
