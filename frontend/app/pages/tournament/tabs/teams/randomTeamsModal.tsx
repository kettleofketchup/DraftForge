import { UsersRound } from 'lucide-react';
import React, { useState } from 'react';
import { TeamCard } from '~/components/team/teamCard';
import type { TeamType } from '~/components/tournament/types';
import { Button } from '~/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '~/components/ui/tooltip';

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

import { ScrollArea } from '@radix-ui/react-scroll-area';
import { TEAMS_BUTTONS_WIDTH } from '~/components/constants';
import { DIALOG_CSS, SCROLLAREA_CSS } from '~/components/reusable/modal';
import { CreateTeamsButton } from './createTeamsButton';
interface Props {
  users: UserType[];
  teamSize?: number;
}

interface TeamsViewProps {
  teams: TeamType[];
}

const TeamsView: React.FC<TeamsViewProps> = ({ teams }) => (
  <div
    className="flex grid grid-flow-row-dense grid-auto-rows
        align-middle content-center justify-center
         grid-cols-1 lg:grid-cols-2 2xl:grid-cols-2
         mb-0 mt-0 p-0 bg-base-500 w-full"
  >
    {teams.map((team, idx) => (
      <TeamCard
        team={team}
        key={`team-${idx}-${team.name}`}
        edit={false}
        compact={true}
      />
    ))}
  </div>
);

export const RandomizeTeamsModal: React.FC<Props> = ({
  users,
  teamSize = 5,
}) => {
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
  const dialogButton = () => {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DialogTrigger asChild>
              <Button
                className={`w-[${TEAMS_BUTTONS_WIDTH}] btn btn-primary flex w-200px sm:w-auto`}
                data-testid="createTeamsBtn"
                aria-label="Open create teams modal"
              >
                <UsersRound className="mr-2" />
                Create Teams
              </Button>
            </DialogTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <p>Randomize Teams using Player MMR</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {dialogButton()}
      <DialogContent className={`${DIALOG_CSS}`}>
        <ScrollArea className={`${SCROLLAREA_CSS}`}>
          <DialogHeader>
            <DialogTitle>Auto-created Teams</DialogTitle>
            <DialogDescription>
              Teams are generated based on user MMR. You can regenerate to
              reshuffle.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-row items-center gap-4 mb-4">
            <Button
              className="btn btn-info"
              onClick={handleRegenerate}
              data-testid="regenerateTeamsBtn"
              aria-label="Regenerate teams with new randomization"
            >
              Regenerate Teams
            </Button>
          </div>
          <div className="overflow-y-auto max-h-[70vh] pr-2">
            <TeamsView teams={teams} key={`teams-${tournament.pk}`} />
          </div>
        </ScrollArea>
        <DialogFooter>
          <CreateTeamsButton
            tournament={tournament}
            teams={teams}
            dialogOpen={open}
            setDialogOpen={setOpen}
          />
          <DialogClose asChild>
            <Button variant="outline" data-testid="closeTeamsModalBtn">
              Close
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
