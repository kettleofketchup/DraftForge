import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import { Button } from '~/components/ui/button';
import type { GameType, TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import { Plus, Users } from 'lucide-react';
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
import type { User } from '~/components/user/user';
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
import { TeamCard } from '~/components/team/teamCard';
import type { TeamType } from '~/components/tournament/types';
import { hasErrors } from '~/pages/tournament/hasErrors';
import { Tournament } from '~/components/tournament/tournament';

export default function TeamsTab() {
  const tournament = useUserStore((state) => state.tournament);

  const setTournament = useUserStore((state) => state.setTournament);

  const allUsers = useUserStore((state) => state.users); // Zustand setter
  const [tournamentUsers, setTournamentUsers] = useState(
    tournament.users as UserType[],
  );
  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  ); // Zustand setter
  const [query, setQuery] = useState('');
  const [addUserQuery, setAddUserQuery] = useState('');

  useEffect(() => {
    getCurrentTournament();
  }, [allUsers, tournament.users]);

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
      success: () => {
        tournament.users = tournament.users?.filter(
          (u) => u.username !== user.username,
        );
        setTournamentUsers(tournament.users as UserType[]);
        return `${user.username} has been removed`;
      },
      error: (err: any) => {
        console.error('Failed to update tournament', err);
        return `${user.username} has been removed`;
      },
    });
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

    if (updatedUsers?.includes(user)) {
      console.log();
      console.error('User in the  tournament');
      return;
    }
    const updatedTournament = {
      user_ids: [...(updatedUsers || []), user.pk],
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
        loading: `Creating User ${user.username}.`,
        success: () => {
          tournament.users?.push(user);
          setTournamentUsers(tournament.users as UserType[]);
          return `${user.username} has been added`;
        },
        error: (err: any) => {
          console.error('Failed to update tournament', err);
        },
      },
    );

    setQuery(''); // Reset query after adding user
  };

  const filteredTeams =
    query === ''
      ? tournament.teams
      : tournament.teams?.filter((team) => {
          const q = query.toLowerCase();
          return (
            team.name?.toLowerCase().includes(q) ||
            team.users?.some(
              (user: UserType) =>
                user.username?.toLowerCase().includes(q) ||
                user.nickname?.toLowerCase().includes(q),
            )
          );
        });

  useEffect(() => {
    console.log('Tournament users:', tournament.users);
  }, [tournament, filteredTeams]);
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

  let navigate = useNavigate();
  useEffect(() => {
    if (!allUsers || allUsers.length === 0) {
      useUserStore.getState().getUsers();
    }
  }, [allUsers]);
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
          {filteredTeams?.map((team) => (
            <TeamCard
              team={team}
              saveFunc={'save'}
              key={`TeamCard-${team.pk}`}
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
