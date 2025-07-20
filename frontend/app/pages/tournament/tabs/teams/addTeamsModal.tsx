import React, { useState } from 'react';
import { TeamCard } from '~/components/team/teamCard';
import type { TeamType } from '~/components/tournament/types';
import { Button } from '~/components/ui/button';

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
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { createTeams } from './createTeams';
import { CreateTeamsButton } from './createTeamsButton';
interface Props {
  users: UserType[];
  teamSize?: number;
}

interface TeamsViewProps {
  teams: TeamType[];
}

interface TeamViewProps {
  users: UserType[][];
}
const TeamsView: React.FC<TeamsViewProps> = ({ teams }) => (
  <div
    className="flex grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
         grid-cols-1 lg:grid-cols-2 2xl:grid-cols-2
         mb-0 mt-0 p-0 bg-base-900  w-full"
  >
    {teams.map((team, idx) => (
      <>
        <TeamCard
          team={team}
          key={`team-${idx}-${team.name}`}
          edit={false}
          compact={true}
        />
      </>
    ))}
  </div>
);

const createErrorMessage = (val: Partial<Record<keyof TeamType, string>>) => {
  if (!val || Object.keys(val).length === 0)
    return <h5>Error creating team:</h5>;

  return (
    <div className="text-error">
      <ul>
        {Object.entries(val).map(([field, message]) => (
          <li key={field}>{message}</li>
        ))}
      </ul>
    </div>
  );
};

export const AddTeamsModal: React.FC<Props> = ({ users, teamSize = 5 }) => {
  const getCurrentTournament = useUserStore(
    (state) => state.getCurrentTournament,
  );
  const tournament = useUserStore((state) => state.tournament);

  const [teams, setTeams] = useState<TeamType[]>(() =>
    createTeams(users, teamSize),
  );
  const [open, setOpen] = useState(false);

  // Regenerate teams when users or teamSize changes
  React.useEffect(() => {
    setTeams(createTeams(users, teamSize));
  }, []);

  const handleRegenerate = () => {
    setTeams(createTeams(users, teamSize));
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="btn btn-primary">Create Teams</Button>
      </DialogTrigger>
      <DialogContent className=" xl:min-w-6xl l:min-w-5xl md:min-w-4xl sm:min-w-2xl min-w-l ">
        <DialogHeader>
          <DialogTitle>Auto-created Teams</DialogTitle>
          <DialogDescription>
            Teams are generated based on user MMR. You can regenerate to
            reshuffle.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-row items-center gap-4 mb-4">
          <Button className="btn btn-info" onClick={handleRegenerate}>
            Regenerate Teams
          </Button>
        </div>
        <div className="overflow-y-auto max-h-[70vh] pr-2">
          <TeamsView teams={teams} />
        </div>
        <DialogFooter>
          <CreateTeamsButton
            tournament={tournament}
            teams={teams}
            dialogOpen={open}
            setDialogOpen={setOpen}
          />
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
