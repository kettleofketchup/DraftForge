import { memo, useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { updateTournament } from '~/components/api/api';
import { SearchTeamsDropdown } from '~/components/team/searchTeams';
import { TeamCard } from '~/components/team/teamCard';
import type { TournamentType } from '~/components/tournament/types'; // Adjust the import path as necessary
import type { UserType } from '~/components/user/types';
import { hasErrors } from '~/pages/tournament/hasErrors';
import { useUserStore } from '~/store/userStore';
import { AddTeamsModal } from './teams/addTeamsModal';

export const TeamsTab: React.FC = memo(() => {
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
      : tournament.teams
          .sort()
          ?.filter((team) => {
            const q = query.toLowerCase();
            return (
              team.name?.toLowerCase().includes(q) ||
              team.users?.some(
                (user: UserType) =>
                  user.username?.toLowerCase().includes(q) ||
                  user.nickname?.toLowerCase().includes(q),
              )
            );
          })
          .sort((a, b) => {
            return a.name.localeCompare(b.name);
          });

  useEffect(() => {
    console.log('Tournament users:', tournament.users);
  }, [tournament, filteredTeams]);
  if (!tournament || !tournament.users || tournament.users.length === 0) {
    return (
      <>
        <div className="flex flex-col items-start p-4 h-full w-full">
          <div className="self-end p-5 pb-2 pt-2">
            <AddTeamsModal users={allUsers} />
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

  return (
    <>
      <div className="p-5 container bg-base-300 rounded-lg shadow-lg hover:bg-base-400 transition-shadow duration-300 ease-in-out">
        {hasErrors()}
        <div className="self-end p-5 pb-2 pt-2">
          {<AddTeamsModal users={tournament.users} teamSize={5} />}
        </div>
        <div className="w-full">
          <SearchTeamsDropdown
            teams={tournament.teams}
            query={query}
            setQuery={setQuery}
            className="w-full"
            defaultValue="search for users or team names"
          />
        </div>
        <div className="w-full content-center grid gap-2 mt-4 grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 justify-center ">
          {filteredTeams?.map((team) => (
            <TeamCard
              team={team}
              compact={true}
              saveFunc={'save'}
              key={`TeamCard-${team.pk}`}
              removeCallBack={removeUser}
              removeToolTip={'Delete from tournament'}
            />
          ))}
        </div>
      </div>
    </>
  );
});
